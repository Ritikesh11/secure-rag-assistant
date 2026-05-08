import re
from dataclasses import dataclass
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from app.audit import append_audit_event, make_audit_event
from app.config import Settings, get_settings
from app.guardrails import check_question_scope, normalize_domain_term, redact_pii
from app.ingest import SUPPORTED_SUFFIXES, parse_metadata, read_document_text
from app.llm import LlmAnswer, generate_answer
from app.rbac import (
    UserProfile,
    build_chroma_filter,
    can_access_department,
    can_access_document,
    requested_departments,
)


@dataclass(frozen=True)
class RetrievedSource:
    text: str
    source: str
    department: str
    classification: str
    title: str = ""
    distance: float | None = None


@dataclass(frozen=True)
class RagResponse:
    answer: str
    sources: list[RetrievedSource]
    blocked_reason: str | None
    usage: LlmAnswer | None
    denied_source_count: int = 0


@dataclass(frozen=True)
class RetrievalResult:
    sources: list[RetrievedSource]
    denied_source_count: int


DOCUMENT_LIST_TERMS = r"(?:documents?|files?|pdfs?|sources?)"
DOCUMENT_LIST_ACTIONS = r"(?:fetch|find|get|list|show|open)"


STOPWORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "northstar",
    "can",
    "do",
    "does",
    "for",
    "give",
    "i",
    "in",
    "is",
    "it",
    "me",
    "of",
    "on",
    "please",
    "show",
    "tell",
    "the",
    "to",
    "what",
    "whats",
    "with",
}


def is_document_listing_request(question: str) -> bool:
    normalized = " ".join(re.findall(r"[a-zA-Z0-9]+", question.lower()))
    if not normalized:
        return False

    explicit_patterns = [
        rf"\b{DOCUMENT_LIST_ACTIONS}\b.*\b{DOCUMENT_LIST_TERMS}\b",
        rf"\b{DOCUMENT_LIST_TERMS}\b.*\b{DOCUMENT_LIST_ACTIONS}\b",
        rf"\bwhat\b.*\b{DOCUMENT_LIST_TERMS}\b.*\b(?:can i access|do i have|are available)\b",
        rf"\bwhich\b.*\b{DOCUMENT_LIST_TERMS}\b.*\b(?:can i access|do i have|are available)\b",
        rf"\b{DOCUMENT_LIST_TERMS}\b.*\b(?:can i access|do i have|are available)\b",
    ]
    if not any(re.search(pattern, normalized) for pattern in explicit_patterns):
        return False

    content_question_patterns = [
        rf"\bwhat\b.*\b(?:in|inside|from)\b.*\b{DOCUMENT_LIST_TERMS}\b",
        rf"\b(?:summarize|explain|answer)\b.*\b{DOCUMENT_LIST_TERMS}\b",
        rf"\b{DOCUMENT_LIST_TERMS}\b.*\b(?:say|says|contain|contains|mentions?)\b",
    ]
    return not any(re.search(pattern, normalized) for pattern in content_question_patterns)


def _terms(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z0-9]+", text.lower())
    terms = set()
    for word in words:
        if len(word) < 3 or word in STOPWORDS:
            continue
        terms.add(normalize_domain_term(word))
    return terms


def _relevance_score(question: str, source: RetrievedSource) -> int:
    question_terms = _terms(question)
    source_terms = _terms(f"{source.source} {source.department} {source.text}")
    return len(question_terms & source_terms)


def _split_context_sentences(text: str) -> list[str]:
    cleaned = re.sub(r"(?m)^\s*#{1,6}\s+.+$", "", text)
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", cleaned)
        if sentence.strip()
    ]


def _compress_source_text(question: str, text: str, max_sentences: int = 2) -> str:
    question_terms = _terms(question)
    if not question_terms:
        return text

    ranked: list[tuple[int, str]] = []
    for sentence in _split_context_sentences(text):
        score = len(question_terms & _terms(sentence))
        if score:
            ranked.append((score, sentence))

    if not ranked:
        return text

    ranked.sort(key=lambda item: item[0], reverse=True)
    return " ".join(sentence for _, sentence in ranked[:max_sentences])


def build_llm_context(question: str, sources: list[RetrievedSource]) -> str:
    return "\n\n".join(
        "\n".join(
            [
                f"Source: {source.source}",
                f"Title: {source.title}",
                f"Department: {source.department}",
                _compress_source_text(question, source.text),
            ]
        )
        for source in sources
    )


def _is_catalog_source(source: RetrievedSource) -> bool:
    title = source.title.lower()
    path = Path(source.source)
    return "document catalog" in title or path.stem == "document-catalog"


def _asks_for_catalog(question: str) -> bool:
    terms = _terms(question)
    return "catalog" in terms or "document" in terms or is_document_listing_request(question)


def filter_relevant_sources(question: str, sources: list[RetrievedSource]) -> list[RetrievedSource]:
    if not sources:
        return []

    if not _asks_for_catalog(question):
        non_catalog_sources = [source for source in sources if not _is_catalog_source(source)]
        if non_catalog_sources:
            sources = non_catalog_sources

    scored = [(source, _relevance_score(question, source)) for source in sources]
    positive = [(source, score) for source, score in scored if score > 0]
    if not positive:
        return sources[:1]

    best_score = max(score for _, score in positive)
    return [source for source, score in positive if score >= best_score]


def format_document_list(sources: list[RetrievedSource]) -> str:
    if not sources:
        return "I could not find any authorized documents matching that request."

    lines = ["I found these authorized documents. Use the download buttons below to open them:"]
    for source in sources:
        title = source.title or Path(source.source).stem.replace("-", " ").replace("_", " ").title()
        lines.append(f"- {title} ({source.department} / {source.classification})")
    return "\n".join(lines)


def _dedupe_sources(sources: list[RetrievedSource]) -> list[RetrievedSource]:
    deduped: dict[str, RetrievedSource] = {}
    for source in sources:
        deduped.setdefault(source.source, source)
    return sorted(deduped.values(), key=lambda source: source.source)


class RagService:
    max_retrieval_distance = 1.2

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._collection = None
        self._metadata_collection = None

    @property
    def collection(self):
        if self._collection is not None:
            return self._collection

        embedding_function = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        client = chromadb.PersistentClient(path=str(self.settings.chroma_dir))
        self._collection = client.get_or_create_collection(
            name=self.settings.collection_name,
            embedding_function=embedding_function,
            metadata={"hnsw:space": "cosine"},
        )
        return self._collection

    @property
    def metadata_collection(self):
        if self._metadata_collection is not None:
            return self._metadata_collection

        client = chromadb.PersistentClient(path=str(self.settings.chroma_dir))
        self._metadata_collection = client.get_or_create_collection(
            name=self.settings.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        return self._metadata_collection

    def collection_count(self) -> int | None:
        try:
            return int(self.metadata_collection.count())
        except Exception:
            return None

    def retrieve(self, question: str, user: UserProfile, k: int = 4) -> RetrievalResult:
        chroma_filter = build_chroma_filter(user)
        denied_departments = {
            department
            for department in requested_departments(question)
            if not can_access_department(user, department)
        }
        query_args = {
            "query_texts": [question],
            "n_results": k,
            "include": ["documents", "metadatas", "distances"],
        }
        if chroma_filter:
            query_args["where"] = chroma_filter

        results = self.collection.query(**query_args)
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        sources: list[RetrievedSource] = []
        denied_source_count = len(denied_departments)
        for document, metadata, distance in zip(documents, metadatas, distances, strict=False):
            if not can_access_document(user, metadata):
                denied_source_count += 1
                continue
            if distance is not None and float(distance) > self.max_retrieval_distance:
                continue
            sources.append(
                RetrievedSource(
                    text=redact_pii(document),
                    source=str(metadata.get("source", "unknown")),
                    department=str(metadata.get("department", "unknown")),
                    classification=str(metadata.get("classification", "internal")),
                    title=str(metadata.get("title", "")),
                    distance=float(distance) if distance is not None else None,
                )
            )
        return RetrievalResult(
            sources=filter_relevant_sources(question, sources),
            denied_source_count=denied_source_count,
        )

    def list_documents(self, question: str, user: UserProfile) -> RetrievalResult:
        requested = requested_departments(question)
        allowed_requested = {
            department for department in requested if can_access_department(user, department)
        }
        denied_source_count = len(requested - allowed_requested)

        sources = self._list_filesystem_documents(user, allowed_requested, requested)
        if not sources:
            sources = self._list_indexed_documents(user, allowed_requested, requested)

        return RetrievalResult(
            sources=_dedupe_sources(sources),
            denied_source_count=denied_source_count,
        )

    def _list_indexed_documents(
        self,
        user: UserProfile,
        allowed_requested: set[str],
        requested: set[str],
    ) -> list[RetrievedSource]:
        try:
            results = self.metadata_collection.get(include=["documents", "metadatas"])
        except Exception:
            return []

        sources_by_path: dict[str, RetrievedSource] = {}
        for document, metadata in zip(
            results.get("documents", []),
            results.get("metadatas", []),
            strict=False,
        ):
            source = self._source_from_metadata(user, document, metadata, allowed_requested, requested)
            if not source:
                continue
            sources_by_path.setdefault(source.source, source)
        return sorted(sources_by_path.values(), key=lambda source: source.source)

    def _list_filesystem_documents(
        self,
        user: UserProfile,
        allowed_requested: set[str],
        requested: set[str],
    ) -> list[RetrievedSource]:
        sources: list[RetrievedSource] = []
        for directory in [self.settings.sample_docs_dir, self.settings.upload_dir]:
            if not directory.exists():
                continue
            for path in sorted(directory.rglob("*")):
                if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                    continue
                metadata = parse_metadata(path)
                try:
                    document = read_document_text(path)
                except Exception:
                    document = path.name
                source = self._source_from_metadata(
                    user,
                    document,
                    metadata,
                    allowed_requested,
                    requested,
                )
                if source:
                    sources.append(source)
        return sources

    def _source_from_metadata(
        self,
        user: UserProfile,
        document: str,
        metadata: dict,
        allowed_requested: set[str],
        requested: set[str],
    ) -> RetrievedSource | None:
        if not can_access_document(user, metadata):
            return None

        department = str(metadata.get("department", "unknown"))
        if allowed_requested and department not in allowed_requested:
            return None
        if requested and not allowed_requested:
            return None

        return RetrievedSource(
            text=redact_pii(document),
            source=str(metadata.get("source", "unknown")),
            department=department,
            classification=str(metadata.get("classification", "internal")),
            title=str(metadata.get("title", "")),
        )

    def ask(self, question: str, user: UserProfile) -> RagResponse:
        scope = check_question_scope(question)
        if scope.intent == "smalltalk":
            append_audit_event(
                self.settings.audit_log_path,
                make_audit_event(
                    user=user,
                    question=question,
                    status="smalltalk",
                    source_count=0,
                ),
            )
            return RagResponse(
                answer=scope.response or "How can I help with Northstar Analytics company data?",
                sources=[],
                blocked_reason=None,
                usage=None,
            )

        if not scope.allowed:
            append_audit_event(
                self.settings.audit_log_path,
                make_audit_event(
                    user=user,
                    question=question,
                    status="blocked",
                    source_count=0,
                    blocked_reason=scope.reason,
                ),
            )
            return RagResponse(
                answer=scope.reason or "Question blocked by guardrails.",
                sources=[],
                blocked_reason=scope.reason,
                usage=None,
            )

        if is_document_listing_request(question):
            retrieval = self.list_documents(question, user)
            answer = format_document_list(retrieval.sources)
            append_audit_event(
                self.settings.audit_log_path,
                make_audit_event(
                    user=user,
                    question=question,
                    status="document_list",
                    source_count=len(retrieval.sources),
                    denied_source_count=retrieval.denied_source_count,
                    sources=[source.source for source in retrieval.sources],
                ),
            )
            return RagResponse(
                answer=answer,
                sources=retrieval.sources,
                blocked_reason=None,
                usage=None,
                denied_source_count=retrieval.denied_source_count,
            )

        retrieval = self.retrieve(question, user)
        sources = retrieval.sources
        if not sources:
            answer = "I do not have enough authorized company information to answer that."
            append_audit_event(
                self.settings.audit_log_path,
                make_audit_event(
                    user=user,
                    question=question,
                    status="no_authorized_context",
                    source_count=0,
                    denied_source_count=retrieval.denied_source_count,
                ),
            )
            return RagResponse(
                answer=answer,
                sources=[],
                blocked_reason=None,
                usage=None,
                denied_source_count=retrieval.denied_source_count,
            )
        context = build_llm_context(question, sources)
        llm_answer = generate_answer(question, context, user, self.settings)
        append_audit_event(
            self.settings.audit_log_path,
            make_audit_event(
                user=user,
                question=question,
                status="answered",
                source_count=len(sources),
                denied_source_count=retrieval.denied_source_count,
                sources=[source.source for source in sources],
            ),
        )
        return RagResponse(
            answer=llm_answer.answer,
            sources=sources,
            blocked_reason=None,
            usage=llm_answer,
            denied_source_count=retrieval.denied_source_count,
        )

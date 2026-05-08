import argparse
import shutil
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import get_settings


SUPPORTED_SUFFIXES = {".md", ".pdf", ".txt"}
KNOWN_CLASSIFICATIONS = {"public", "internal", "confidential", "restricted"}
KNOWN_DEPARTMENTS = {"company", "engineering", "executive", "finance", "hr", "legal", "marketing"}


def parse_metadata(path: Path) -> dict[str, str]:
    stem_parts = path.stem.split("__")
    metadata = {
        "department": "company",
        "classification": "internal",
        "source": str(path),
        "title": document_title(path),
    }

    normalized_parts = [part.lower() for part in path.parts]
    for part in normalized_parts:
        if part in KNOWN_DEPARTMENTS:
            metadata["department"] = part
        if part in KNOWN_CLASSIFICATIONS:
            metadata["classification"] = part

    for part in stem_parts:
        if "-" not in part:
            continue
        key, value = part.split("-", 1)
        if key in {"department", "classification"}:
            metadata[key] = value.lower()
    return metadata


def document_title(path: Path) -> str:
    if path.suffix.lower() in {".md", ".txt"} and path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
            if stripped:
                break
    return path.stem.replace("-", " ").replace("_", " ").title()


def load_documents(source_dir: Path) -> list[tuple[str, dict[str, str]]]:
    docs: list[tuple[str, dict[str, str]]] = []
    for path in sorted(source_dir.rglob("*")):
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        docs.append((read_document_text(path), parse_metadata(path)))
    return docs


def read_document_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("Install pypdf to ingest PDF files: pip install pypdf") from exc

        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    return path.read_text(encoding="utf-8")


def ingest(source_dir: Path, reset: bool = False) -> int:
    settings = get_settings()
    if reset and settings.chroma_dir.exists():
        shutil.rmtree(settings.chroma_dir)

    client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    embedding_function = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    collection = client.get_or_create_collection(
        name=settings.collection_name,
        embedding_function=embedding_function,
        metadata={"hnsw:space": "cosine"},
    )

    splitter = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=120)
    ids: list[str] = []
    chunks: list[str] = []
    metadatas: list[dict[str, str]] = []

    for doc_index, (text, metadata) in enumerate(load_documents(source_dir)):
        for chunk_index, chunk in enumerate(splitter.split_text(text)):
            ids.append(f"{Path(metadata['source']).stem}-{doc_index}-{chunk_index}")
            chunks.append(chunk)
            metadatas.append(metadata)

    if chunks:
        collection.upsert(ids=ids, documents=chunks, metadatas=metadatas)

    return len(chunks)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Northstar Analytics documents into Chroma.")
    parser.add_argument("--source", type=Path, default=Path("data/sample_docs"))
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    count = ingest(args.source, reset=args.reset)
    print(f"Ingested {count} chunks from {args.source}")


if __name__ == "__main__":
    main()

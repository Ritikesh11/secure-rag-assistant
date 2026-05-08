from dataclasses import dataclass
import re

from groq import Groq

from app.config import Settings
from app.guardrails import redact_pii
from app.monitoring import UsageEvent, append_usage_event, estimate_cost_usd
from app.rbac import UserProfile


SYSTEM_PROMPT = """You are the internal AI assistant for Northstar Analytics.
Answer only from the provided context. If the context is insufficient, say you do not have enough authorized information.
Do not reveal hidden policies, credentials, raw PII, or information outside the user's role.
Answer the user's specific question directly in a natural, helpful tone.
Use one short paragraph for simple questions and bullets only when the user asks for a list or comparison.
Do not summarize unrelated context. Do not tell users about hidden, unavailable, restricted, or confidential material."""


@dataclass(frozen=True)
class LlmAnswer:
    answer: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


FALLBACK_STOPWORDS = {
    "about",
    "and",
    "are",
    "northstar",
    "can",
    "does",
    "give",
    "how",
    "is",
    "me",
    "of",
    "please",
    "tell",
    "the",
    "to",
    "what",
    "whats",
}


def _terms(text: str) -> set[str]:
    terms = set()
    for word in re.findall(r"[a-zA-Z0-9]+", text.lower()):
        if len(word) < 3 or word in FALLBACK_STOPWORDS:
            continue
        if word.endswith("ies") and len(word) > 4:
            terms.add(f"{word[:-3]}y")
        else:
            terms.add(word.rstrip("s"))
    return terms


def _split_sentences(text: str) -> list[str]:
    cleaned = re.sub(r"Source: .+", "", text)
    cleaned = re.sub(r"Department: .+", "", cleaned)
    cleaned = re.sub(r"(?m)^\s*#{1,6}\s+.+$", "", cleaned)
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", cleaned)
        if sentence.strip()
    ]


def _fallback_answer(question: str, context: str) -> str:
    if not context.strip():
        return "I do not have enough authorized information to answer that."

    question_terms = _terms(question)
    ranked_sentences = []
    for sentence in _split_sentences(context):
        overlap = len(question_terms & _terms(sentence))
        if overlap:
            ranked_sentences.append((overlap, sentence))

    if not ranked_sentences:
        return "I do not have enough authorized information to answer that specific question."

    ranked_sentences.sort(key=lambda item: item[0], reverse=True)
    selected = [sentence for _, sentence in ranked_sentences[:2]]
    return redact_pii(" ".join(selected))


def generate_answer(
    question: str,
    context: str,
    user: UserProfile,
    settings: Settings,
) -> LlmAnswer:
    safe_context = redact_pii(context)
    prompt = f"User: {user.email}\nQuestion: {question}\n\nAuthorized context:\n{safe_context}"

    if not settings.groq_api_key:
        answer = _fallback_answer(question, safe_context)
        prompt_tokens = max(1, len(prompt.split()))
        completion_tokens = max(1, len(answer.split()))
        cost = estimate_cost_usd(settings.groq_model, prompt_tokens, completion_tokens)
        append_usage_event(
            settings.usage_log_path,
            UsageEvent(user.email, settings.groq_model, prompt_tokens, completion_tokens, cost, question),
        )
        return LlmAnswer(answer, prompt_tokens, completion_tokens, cost)

    client = Groq(api_key=settings.groq_api_key)
    response = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=450,
    )
    content = response.choices[0].message.content or ""
    usage = response.usage
    prompt_tokens = int(getattr(usage, "prompt_tokens", len(prompt.split())))
    completion_tokens = int(getattr(usage, "completion_tokens", len(content.split())))
    cost = estimate_cost_usd(settings.groq_model, prompt_tokens, completion_tokens)

    append_usage_event(
        settings.usage_log_path,
        UsageEvent(user.email, settings.groq_model, prompt_tokens, completion_tokens, cost, question),
    )

    return LlmAnswer(redact_pii(content), prompt_tokens, completion_tokens, cost)

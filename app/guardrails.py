import re
from dataclasses import dataclass
from difflib import get_close_matches


PII_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED_SSN]"),
    (re.compile(r"\b(?:\d[ -]*?){13,16}\b"), "[REDACTED_CARD]"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[REDACTED_EMAIL]"),
    (re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"), "[REDACTED_PHONE]"),
)

COMPANY_TERMS = {
    "northstar",
    "benefits",
    "board",
    "brand",
    "backup",
    "campaign",
    "calendar",
    "cloud",
    "company",
    "contract",
    "correction",
    "disaster",
    "document",
    "employee",
    "engineering",
    "expense",
    "file",
    "finance",
    "financial",
    "forecast",
    "guideline",
    "headcount",
    "hr",
    "incident",
    "infrastructure",
    "leave",
    "legal",
    "marketing",
    "margin",
    "pipeline",
    "platform",
    "pay",
    "pdf",
    "payroll",
    "policy",
    "priorities",
    "q4",
    "reliability",
    "recovery",
    "remote",
    "report",
    "retention",
    "revenue",
    "saas",
    "salary",
    "security",
    "spend",
    "tax",
    "target",
    "timeout",
    "uae",
    "uptime",
    "vendor",
    "webinar",
    "budget",
    "work",
}

TERM_ALIASES = {
    "benefit": "benefits",
    "buget": "budget",
    "budgets": "budget",
    "campain": "campaign",
    "campains": "campaign",
    "expences": "expense",
    "expens": "expense",
    "finace": "finance",
    "financ": "finance",
    "marketng": "marketing",
    "markting": "marketing",
    "marketting": "marketing",
    "payrol": "payroll",
    "polcy": "policy",
    "policies": "policy",
    "revenuee": "revenue",
    "remotely": "remote",
    "securty": "security",
}

OUT_OF_SCOPE_HINTS = {
    "weather",
    "movie",
    "recipe",
    "sports",
    "medical",
    "diagnose",
    "lawsuit",
    "homework",
    "astrology",
    "stock tip",
}

PROMPT_INJECTION_HINTS = {
    "ignore previous",
    "ignore all previous",
    "forget previous",
    "system prompt",
    "developer message",
    "hidden instructions",
    "jailbreak",
    "bypass rbac",
    "bypass access",
    "show me everything",
    "reveal secrets",
    "api key",
    "password",
}

SHORT_ALLOWED_QUESTIONS = {
    "good afternoon",
    "good evening",
    "good morning",
    "hello",
    "hey",
    "hi",
    "thanks",
    "thank you",
}

HELP_PATTERNS = {
    "help",
    "what can you do",
    "what do you do",
    "how can you help",
    "how do i use this",
    "who are you",
}


@dataclass(frozen=True)
class GuardrailResult:
    allowed: bool
    reason: str | None = None
    intent: str = "rag"
    response: str | None = None


def redact_pii(text: str) -> str:
    redacted = text
    for pattern, replacement in PII_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def normalize_domain_term(word: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]", "", word.lower())
    if not cleaned:
        return ""
    if cleaned in TERM_ALIASES:
        return TERM_ALIASES[cleaned]
    if cleaned.endswith("ies") and len(cleaned) > 4:
        cleaned = f"{cleaned[:-3]}y"
    else:
        cleaned = cleaned.rstrip("s")
    if cleaned in COMPANY_TERMS:
        return cleaned
    match = get_close_matches(cleaned, COMPANY_TERMS, n=1, cutoff=0.82)
    return match[0] if match else cleaned


def contains_company_term(text: str) -> bool:
    words = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return any(normalize_domain_term(word) in COMPANY_TERMS for word in words)


def check_question_scope(question: str) -> GuardrailResult:
    normalized = question.strip().lower()
    normalized = re.sub(r"[^\w\s]", "", normalized)
    if not normalized:
        return GuardrailResult(
            allowed=False,
            reason="Ask a question about Northstar Analytics company data.",
            intent="blocked",
        )

    if any(hint in normalized for hint in PROMPT_INJECTION_HINTS):
        return GuardrailResult(
            allowed=False,
            reason="This request looks like an attempt to bypass instructions or access controls.",
            intent="blocked",
        )

    if any(hint in normalized for hint in OUT_OF_SCOPE_HINTS):
        return GuardrailResult(
            allowed=False,
            reason="This question appears outside the internal company knowledge base.",
            intent="blocked",
        )

    if normalized in SHORT_ALLOWED_QUESTIONS:
        return GuardrailResult(
            allowed=True,
            intent="smalltalk",
            response=(
                "Hi. I can answer Northstar Analytics company questions using the documents your role is "
                "allowed to access."
            ),
        )

    if any(pattern in normalized for pattern in HELP_PATTERNS):
        return GuardrailResult(
            allowed=True,
            intent="smalltalk",
            response=(
                "I can help with Northstar Analytics policies, finance reports, HR/payroll information, "
                "marketing expenses, and executive documents based on your login permissions."
            ),
        )

    if contains_company_term(normalized):
        return GuardrailResult(allowed=True, intent="rag")

    return GuardrailResult(
        allowed=False,
        reason="Ask about Northstar Analytics company policies, departmental reports, budgets, employees, or operations.",
        intent="blocked",
    )

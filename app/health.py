from dataclasses import dataclass

from app.config import Settings


@dataclass(frozen=True)
class HealthCheck:
    name: str
    ok: bool
    detail: str


def collect_health_checks(settings: Settings, collection_count: int | None) -> list[HealthCheck]:
    return [
        HealthCheck(
            "Vector index",
            bool(collection_count),
            f"{collection_count or 0} chunks indexed",
        ),
        HealthCheck(
            "LLM credentials",
            bool(settings.groq_api_key),
            "Groq API key configured" if settings.groq_api_key else "Using local fallback answers",
        ),
        HealthCheck(
            "Usage logging",
            True,
            str(settings.usage_log_path),
        ),
        HealthCheck(
            "Audit logging",
            True,
            str(settings.audit_log_path),
        ),
    ]

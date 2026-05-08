import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.rbac import UserProfile


@dataclass(frozen=True)
class AuditEvent:
    user_email: str
    role: str
    departments: str
    question: str
    status: str
    source_count: int
    denied_source_count: int
    blocked_reason: str | None
    sources: str


@dataclass(frozen=True)
class FeedbackEvent:
    user_email: str
    question: str
    answer: str
    rating: str


def append_audit_event(path: Path, event: AuditEvent) -> None:
    _append_row(
        path,
        [
            "timestamp",
            "user_email",
            "role",
            "departments",
            "question",
            "status",
            "source_count",
            "denied_source_count",
            "blocked_reason",
            "sources",
        ],
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "user_email": event.user_email,
            "role": event.role,
            "departments": event.departments,
            "question": event.question[:500],
            "status": event.status,
            "source_count": event.source_count,
            "denied_source_count": event.denied_source_count,
            "blocked_reason": event.blocked_reason or "",
            "sources": event.sources[:1000],
        },
    )


def append_feedback_event(path: Path, event: FeedbackEvent) -> None:
    _append_row(
        path,
        ["timestamp", "user_email", "question", "answer", "rating"],
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "user_email": event.user_email,
            "question": event.question[:500],
            "answer": event.answer[:1000],
            "rating": event.rating,
        },
    )


def make_audit_event(
    user: UserProfile,
    question: str,
    status: str,
    source_count: int,
    denied_source_count: int = 0,
    blocked_reason: str | None = None,
    sources: list[str] | None = None,
) -> AuditEvent:
    return AuditEvent(
        user_email=user.email,
        role=user.role,
        departments=",".join(user.departments),
        question=question,
        status=status,
        source_count=source_count,
        denied_source_count=denied_source_count,
        blocked_reason=blocked_reason,
        sources="; ".join(sources or []),
    )


def _append_row(path: Path, fieldnames: list[str], row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow(row)

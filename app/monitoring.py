import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


MODEL_PRICES_PER_1K_TOKENS = {
    "llama-3.1-8b-instant": {"input": 0.00005, "output": 0.00008},
    "llama-3.3-70b-versatile": {"input": 0.00059, "output": 0.00079},
}


@dataclass(frozen=True)
class UsageEvent:
    user_email: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_cost_usd: float
    question: str


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    prices = MODEL_PRICES_PER_1K_TOKENS.get(
        model,
        {"input": 0.0001, "output": 0.0001},
    )
    return round(
        (prompt_tokens / 1000 * prices["input"])
        + (completion_tokens / 1000 * prices["output"]),
        6,
    )


def append_usage_event(path: Path, event: UsageEvent) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "timestamp",
                "user_email",
                "model",
                "prompt_tokens",
                "completion_tokens",
                "total_cost_usd",
                "question",
            ],
        )
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "user_email": event.user_email,
                "model": event.model,
                "prompt_tokens": event.prompt_tokens,
                "completion_tokens": event.completion_tokens,
                "total_cost_usd": event.total_cost_usd,
                "question": event.question[:500],
            }
        )


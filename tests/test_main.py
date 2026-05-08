from app.main import _normalize_chat_answer, _source_title
from app.rag import RetrievedSource


def test_normalize_chat_answer_removes_markdown_heading_size() -> None:
    answer = "# Marketing Campaign Expenses\n\nThe campaign spend was USD 420K."

    normalized = _normalize_chat_answer(answer)

    assert normalized == "Marketing Campaign Expenses\n\nThe campaign spend was USD 420K."


def test_source_title_uses_friendly_title() -> None:
    source = RetrievedSource(
        text="",
        source="data/sample_docs/marketing/confidential/campaign-expenses.md",
        department="marketing",
        classification="confidential",
        title="Marketing Campaign Expenses",
    )

    assert _source_title(source) == "Marketing Campaign Expenses"

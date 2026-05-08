from app.llm import _fallback_answer


def test_fallback_answers_specific_question_without_dumping_context() -> None:
    context = """
    Source: finance.md
    Department: finance
    Northstar Analytics closed Q4 with revenue of USD 18.4M and operating margin of 22%.
    The finance team approved a USD 850K cloud infrastructure budget.
    Source: remote.md
    Department: company
    Northstar Analytics employees may work remotely up to three days per week with manager approval.
    """

    answer = _fallback_answer("What was Q4 revenue?", context)

    assert "USD 18.4M" in answer
    assert "remote" not in answer.lower()


def test_fallback_returns_insufficient_when_no_sentence_matches() -> None:
    context = "Northstar Analytics employees may work remotely up to three days per week."

    answer = _fallback_answer("What was Q4 revenue?", context)

    assert "not have enough" in answer


def test_fallback_does_not_answer_with_markdown_heading() -> None:
    context = """
    Source: remote-work-policy.md
    Department: company
    # Remote Work Policy

    Northstar Analytics employees may work remotely up to three days per week with manager approval.
    """

    answer = _fallback_answer("What is the remote work policy?", context)

    assert answer == "Northstar Analytics employees may work remotely up to three days per week with manager approval."

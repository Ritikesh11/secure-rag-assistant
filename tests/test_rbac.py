from app.rbac import (
    DEMO_USERS,
    build_chroma_filter,
    can_access_department,
    can_access_document,
    requested_departments,
)


def test_finance_user_can_access_finance_confidential_doc() -> None:
    user = DEMO_USERS["priya.finance@northstar.local"]
    metadata = {"department": "finance", "classification": "confidential"}

    assert can_access_document(user, metadata)


def test_finance_user_cannot_access_hr_restricted_doc() -> None:
    user = DEMO_USERS["priya.finance@northstar.local"]
    metadata = {"department": "hr", "classification": "restricted"}

    assert not can_access_document(user, metadata)


def test_executive_can_access_all_docs() -> None:
    user = DEMO_USERS["nisha.ceo@northstar.local"]
    metadata = {"department": "hr", "classification": "restricted"}

    assert can_access_document(user, metadata)


def test_executive_filter_is_empty() -> None:
    user = DEMO_USERS["nisha.ceo@northstar.local"]

    assert build_chroma_filter(user) == {}


def test_detects_requested_department_from_payroll_question() -> None:
    assert requested_departments("What is the payroll correction window?") == {"hr"}


def test_detects_requested_department_with_marketing_typo() -> None:
    assert requested_departments("What are the markting expenses?") == {"marketing"}


def test_department_access_check() -> None:
    user = DEMO_USERS["maya.marketing@northstar.local"]

    assert can_access_department(user, "marketing")
    assert not can_access_department(user, "finance")


def test_only_executive_can_view_monitoring() -> None:
    assert DEMO_USERS["nisha.ceo@northstar.local"].can_view_monitoring
    assert DEMO_USERS["arjun.admin@northstar.local"].can_view_monitoring
    assert not DEMO_USERS["priya.finance@northstar.local"].can_view_monitoring

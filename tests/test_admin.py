from app.admin import parse_departments


def test_parse_departments() -> None:
    assert parse_departments("finance, HR, marketing") == ["finance", "hr", "marketing"]

from app.auth import authenticate


def test_authenticate_valid_finance_user() -> None:
    user = authenticate("priya.finance@northstar.local", "finance123")

    assert user is not None
    assert user.departments == ("finance",)


def test_authenticate_rejects_wrong_password() -> None:
    user = authenticate("priya.finance@northstar.local", "wrong")

    assert user is None


def test_demo_credentials_do_not_expose_plain_password_field() -> None:
    from app.auth import list_demo_credentials

    credential = list_demo_credentials()[0]

    assert not hasattr(credential, "password")
    assert hasattr(credential, "password_hash")


def test_authenticate_valid_admin_user() -> None:
    user = authenticate("arjun.admin@northstar.local", "admin123")

    assert user is not None
    assert user.can_manage_users


def test_authenticate_engineering_and_legal_users() -> None:
    engineering = authenticate("dev.engineering@northstar.local", "eng123")
    legal = authenticate("leena.legal@northstar.local", "legal123")

    assert engineering is not None
    assert engineering.departments == ("engineering",)
    assert legal is not None
    assert legal.departments == ("legal",)

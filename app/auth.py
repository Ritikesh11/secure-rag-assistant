import hashlib
import hmac
from dataclasses import dataclass

from app.config import get_settings
from app.rbac import UserProfile, load_user_records, load_users


@dataclass(frozen=True)
class DemoCredential:
    email: str
    password_hint: str
    password_hash: str


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def authenticate(email: str, password: str) -> UserProfile | None:
    normalized_email = email.strip().lower()
    settings = get_settings()
    records = load_user_records(settings.user_store_path)
    record = records.get(normalized_email)
    if not record or not record.get("active", True):
        return None

    if not hmac.compare_digest(hash_password(password), str(record["password_hash"])):
        return None

    return load_users(settings.user_store_path).get(normalized_email)


def list_demo_credentials() -> list[DemoCredential]:
    records = load_user_records(get_settings().user_store_path)
    return [
        DemoCredential(
            email=str(record["email"]),
            password_hint=str(record.get("password_hint", "")),
            password_hash=str(record["password_hash"]),
        )
        for record in records.values()
        if record.get("active", True) and record.get("password_hint")
    ]


def get_user_by_email(email: str) -> UserProfile | None:
    return load_users(get_settings().user_store_path).get(email.strip().lower())

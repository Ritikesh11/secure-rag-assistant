import re
from pathlib import Path

from app.auth import hash_password
from app.rbac import load_user_records, save_user_records


ALLOWED_UPLOAD_SUFFIXES = {".md", ".pdf", ".txt"}


def normalize_email(email: str) -> str:
    return email.strip().lower()


def parse_departments(value: str) -> list[str]:
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def upsert_user(
    store_path: Path,
    email: str,
    display_name: str,
    title: str,
    role: str,
    departments: list[str],
    active: bool,
    password: str | None = None,
) -> None:
    records = load_user_records(store_path)
    normalized_email = normalize_email(email)
    existing = records.get(normalized_email, {})
    password_hash = existing.get("password_hash")
    password_hint = existing.get("password_hint", "")

    if password:
        password_hash = hash_password(password)
        password_hint = password

    if not password_hash:
        raise ValueError("Password is required for new users.")

    records[normalized_email] = {
        "email": normalized_email,
        "display_name": display_name.strip() or normalized_email,
        "title": title.strip(),
        "role": role.strip().lower(),
        "departments": departments,
        "active": active,
        "password_hint": password_hint,
        "password_hash": password_hash,
    }
    save_user_records(store_path, records)


def deactivate_user(store_path: Path, email: str) -> None:
    records = load_user_records(store_path)
    normalized_email = normalize_email(email)
    if normalized_email in records:
        records[normalized_email]["active"] = False
        save_user_records(store_path, records)


def save_uploaded_document(
    upload_dir: Path,
    uploaded_file,
    department: str,
    classification: str,
) -> Path:
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise ValueError("Only .txt, .md, and .pdf files are supported.")

    target_dir = upload_dir / department / classification
    target_dir.mkdir(parents=True, exist_ok=True)
    original = Path(uploaded_file.name)
    safe_stem = re.sub(r"[^a-zA-Z0-9]+", "-", original.stem).strip("-").lower()
    target = target_dir / f"{safe_stem}{suffix}"
    target.write_bytes(uploaded_file.getbuffer())
    return target

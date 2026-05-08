import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from app.guardrails import normalize_domain_term


class Classification(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


@dataclass(frozen=True)
class UserProfile:
    email: str
    role: str
    departments: tuple[str, ...]
    display_name: str = ""
    title: str = ""
    active: bool = True

    @property
    def is_executive(self) -> bool:
        return self.role == "executive" or "all" in self.departments

    @property
    def can_view_monitoring(self) -> bool:
        return self.role in {"admin", "executive"} or self.is_executive

    @property
    def can_manage_users(self) -> bool:
        return self.role in {"admin", "executive"} or self.is_executive

    @property
    def can_manage_documents(self) -> bool:
        return self.role in {"admin", "executive"} or self.is_executive


DEFAULT_USER_RECORDS = {
    "priya.finance@northstar.local": {
        "email": "priya.finance@northstar.local",
        "display_name": "Priya Shah",
        "title": "Finance Analyst",
        "role": "employee",
        "departments": ["finance"],
        "active": True,
        "password_hint": "finance123",
        "password_hash": "48f7312924d74358e75294e3b3613f2319d99e944184b69550f528577ca082fb",
    },
    "omar.hr@northstar.local": {
        "email": "omar.hr@northstar.local",
        "display_name": "Omar Khan",
        "title": "HR Operations",
        "role": "employee",
        "departments": ["hr"],
        "active": True,
        "password_hint": "hr123",
        "password_hash": "070a3b5e8d4bd5c46acccb91c9c54614c0cd649e78c4c4719e3a64270bae5ddf",
    },
    "maya.marketing@northstar.local": {
        "email": "maya.marketing@northstar.local",
        "display_name": "Maya Patel",
        "title": "Marketing Manager",
        "role": "employee",
        "departments": ["marketing"],
        "active": True,
        "password_hint": "marketing123",
        "password_hash": "7d50137f0395e9a47a5daf16959dd68abef6370d3b837ec3be4fe9d869db46a3",
    },
    "dev.engineering@northstar.local": {
        "email": "dev.engineering@northstar.local",
        "display_name": "Dev Iyer",
        "title": "Platform Engineer",
        "role": "employee",
        "departments": ["engineering"],
        "active": True,
        "password_hint": "eng123",
        "password_hash": "f63248efa4a61efc9f4c9f6e5de25b34b6f2b827717cd4c6b3905481c3bd483b",
    },
    "leena.legal@northstar.local": {
        "email": "leena.legal@northstar.local",
        "display_name": "Leena Desai",
        "title": "Legal Counsel",
        "role": "employee",
        "departments": ["legal"],
        "active": True,
        "password_hint": "legal123",
        "password_hash": "bce14beaddab2ebc3e8e214509404b8d3d2b43b3968bf214ececb8a746cbe4f4",
    },
    "nisha.ceo@northstar.local": {
        "email": "nisha.ceo@northstar.local",
        "display_name": "Nisha Rao",
        "title": "Chief Executive Officer",
        "role": "executive",
        "departments": ["all"],
        "active": True,
        "password_hint": "ceo123",
        "password_hash": "36ca949d1f95aff0c68dbca6dffa4386de2366ca367854294c6377432bca85f0",
    },
    "arjun.admin@northstar.local": {
        "email": "arjun.admin@northstar.local",
        "display_name": "Arjun Mehta",
        "title": "AI Platform Admin",
        "role": "admin",
        "departments": ["all"],
        "active": True,
        "password_hint": "admin123",
        "password_hash": "240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9",
    },
}

DEMO_USERS: dict[str, UserProfile] = {}

KNOWN_DEPARTMENTS = {"finance", "hr", "marketing", "engineering", "legal", "executive"}


def records_to_profiles(records: dict[str, dict]) -> dict[str, UserProfile]:
    return {
        email: UserProfile(
            email=str(record["email"]),
            role=str(record["role"]),
            departments=tuple(record.get("departments", [])),
            display_name=str(record.get("display_name", "")),
            title=str(record.get("title", "")),
            active=bool(record.get("active", True)),
        )
        for email, record in records.items()
    }


def load_user_records(path: Path | None = None) -> dict[str, dict]:
    if path and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return dict(DEFAULT_USER_RECORDS)


def save_user_records(path: Path, records: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2, sort_keys=True), encoding="utf-8")


def load_users(path: Path | None = None) -> dict[str, UserProfile]:
    return records_to_profiles(load_user_records(path))


DEMO_USERS.update(load_users())


def requested_departments(question: str) -> set[str]:
    normalized = question.lower()
    normalized_terms = {normalize_domain_term(word) for word in normalized.split()}
    found = {department for department in KNOWN_DEPARTMENTS if department in normalized_terms}
    if "payroll" in normalized or "salary" in normalized or "employee data" in normalized:
        found.add("hr")
    if "revenue" in normalized or "financial" in normalized or "budget" in normalized:
        found.add("finance")
    if "campaign" in normalized or "webinar" in normalized:
        found.add("marketing")
    return found


def can_access_document(user: UserProfile, metadata: dict) -> bool:
    department = str(metadata.get("department", "")).lower()
    classification = str(metadata.get("classification", "internal")).lower()

    if user.is_executive:
        return True
    if classification == Classification.PUBLIC.value:
        return True
    if classification == Classification.INTERNAL.value and department == "company":
        return True
    return department in user.departments


def can_access_department(user: UserProfile, department: str) -> bool:
    if user.is_executive:
        return True
    if department == "company":
        return True
    return department in user.departments


def build_chroma_filter(user: UserProfile) -> dict:
    if user.is_executive:
        return {}

    departments = list(user.departments)
    return {
        "$or": [
            {"classification": {"$eq": Classification.PUBLIC.value}},
            {
                "$and": [
                    {"classification": {"$eq": Classification.INTERNAL.value}},
                    {"department": {"$eq": "company"}},
                ]
            },
            {"department": {"$in": departments}},
        ]
    }

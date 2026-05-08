from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


load_dotenv()


class Settings(BaseSettings):
    app_env: str = "local"
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    chroma_dir: Path = Path("./chroma_db")
    collection_name: str = "northstar_internal_docs"
    sample_docs_dir: Path = Path("./data/sample_docs")
    user_store_path: Path = Path("./data/users.json")
    upload_dir: Path = Path("./data/uploads")
    usage_log_path: Path = Path("./logs/usage.csv")
    audit_log_path: Path = Path("./logs/audit.csv")
    feedback_log_path: Path = Path("./logs/feedback.csv")
    cost_alert_daily_usd: float = Field(default=5.0, ge=0)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()

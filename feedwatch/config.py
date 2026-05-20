from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = f"sqlite+aiosqlite:///{BASE_DIR}/feedwatch.db"
    chroma_path: str = str(BASE_DIR / "chroma_db")
    embed_model: str = "all-MiniLM-L6-v2"
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"
    fetch_timeout: int = 30
    scheduler_interval_minutes: int = 60
    api_host: str = "0.0.0.0"
    api_port: int = 8000


settings = Settings()

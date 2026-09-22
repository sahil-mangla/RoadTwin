"""Typed application settings.

Two separate database URLs are mandatory (01-RESEARCH.md Pitfall 3):
`asyncpg` drives the FastAPI app's async engine; `psycopg` (sync) drives
Alembic, which cannot run migrations through an async-only driver.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://roadtwin:roadtwin_dev@localhost:5432/roadtwin"
    database_url_sync: str = "postgresql+psycopg://roadtwin:roadtwin_dev@localhost:5432/roadtwin"
    skeleton_routes_enabled: bool = True

    model_config = SettingsConfigDict(
        env_file="backend/.env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()

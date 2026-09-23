from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    meta_verify_token: str
    meta_access_token: str
    meta_app_secret: str
    meta_ig_user_id: str
    meta_graph_api_version: str = "v26.0"
    meta_auto_reply_enabled: bool = False
    meta_auto_reply_message: str = ""
    meta_reply_keywords: Annotated[list[str], NoDecode] = Field(default_factory=list)
    database_url: str = "sqlite+aiosqlite:///./data/webhook.db"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("meta_reply_keywords", mode="before")
    @classmethod
    def parse_keywords(cls, value: object) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value if isinstance(value, list) else []


@lru_cache
def get_settings() -> Settings:
    return Settings()

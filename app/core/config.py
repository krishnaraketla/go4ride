import json
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "production", "test"] = "development"
    database_url: str = "postgresql+asyncpg://go4ride:go4ride@localhost:5433/go4ride"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 15
    jwt_refresh_expire_days: int = 7

    otp_provider: Literal["console", "twilio", "msg91"] = "console"
    otp_expire_minutes: int = 10
    otp_debug: bool = True
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    msg91_auth_key: str = ""
    msg91_template_id: str = ""

    maps_provider: Literal["mock", "google", "mapbox"] = "mock"
    maps_api_key: str = ""

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, v: object) -> list[str]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [origin.strip() for origin in v.split(",")]
        return v  # type: ignore[return-value]


@lru_cache
def get_settings() -> Settings:
    return Settings()

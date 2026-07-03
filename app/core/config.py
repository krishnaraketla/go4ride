import json
from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "production", "test"] = "development"
    log_level: str | None = None
    log_format: Literal["json", "text"] | None = None
    db_slow_query_ms: int = 500
    sqlalchemy_echo: bool | None = None
    database_url: str = "postgresql+asyncpg://go4ride:go4ride@localhost:5433/go4ride"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 15
    jwt_refresh_expire_days: int = 7

    otp_provider: Literal["console", "twilio", "msg91"] = "console"
    otp_expire_minutes: int = 10
    otp_debug: bool = True
    # Fixed-code OTP bypass for pre-seeded test phones (production smoke testing).
    # request-otp skips SMS; verify-otp accepts otp_bypass_code for these numbers only.
    # NoDecode: allow comma-separated env values (pydantic-settings would otherwise require JSON).
    otp_bypass_phones: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "+15555551001",
            "+15555551002",
            "+15555552001",
            "+15555552002",
        ]
    )
    otp_bypass_code: str = "123456"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    msg91_auth_key: str = ""
    msg91_template_id: str = ""

    maps_provider: Literal["mock", "google", "mapbox"] = "mock"
    maps_api_key: str = ""

    mock_driver_enabled: bool | None = None
    mock_driver_auto_advance: bool = True
    mock_driver_assign_delay_sec: int = 2
    mock_driver_step_delay_sec: int = 5
    mock_driver_eta_min: int = 5

    driver_search_default_radius_km: float = 5.0
    driver_search_max_radius_km: float = 50.0
    driver_eta_cache_ttl_sec: int = 30
    driver_location_publish_interval_sec: int = 10
    # False (default): deliver WebSocket events in-process (single Render instance).
    # True: fan out via Redis pub/sub for multiple app instances.
    websocket_redis_fanout: bool = False

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    public_base_url: str | None = None
    render_external_url: str | None = None

    default_currency: str = "USD"
    email_verify_bonus: Decimal = Field(default=Decimal("5.00"))
    referral_bonus: Decimal = Field(default=Decimal("5.00"))
    max_saved_addresses_per_user: int = 10

    admin_api_key: str = ""
    clear_rides_on_startup: bool = True
    clear_otp_limits_on_startup: bool = False
    # Defaults include mock driver + placeholder test users (aligned with otp_bypass_phones).
    clear_otp_limits_phones: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "+15555550001",
            "+15555551001",
            "+15555551002",
            "+15555552001",
            "+15555552002",
        ]
    )
    # Pre-seeded riders/drivers for initial production testing. Override via SEED_TEST_USERS JSON.
    seed_test_users: Annotated[list[dict[str, str]], NoDecode] = Field(
        default_factory=lambda: [
            {"phone": "+15555551001", "name": "Test Rider 1", "role": "rider"},
            {"phone": "+15555551002", "name": "Test Rider 2", "role": "rider"},
            {"phone": "+15555552001", "name": "Test Driver 1", "role": "driver"},
            {"phone": "+15555552002", "name": "Test Driver 2", "role": "driver"},
        ]
    )
    aws_region: str = "ap-south-1"
    s3_bucket: str = "go4ride-kyc"
    max_upload_size_mb: int = 10

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, v: object) -> object:
        # Managed Postgres providers (Render, Heroku, etc.) hand out URLs in
        # the form `postgres://...` or `postgresql://...`. The async SQLAlchemy
        # engine requires the `postgresql+asyncpg://` driver prefix, so we
        # rewrite it here once at config load time.
        if isinstance(v, str):
            if v.startswith("postgres://"):
                return "postgresql+asyncpg://" + v[len("postgres://") :]
            if v.startswith("postgresql://"):
                return "postgresql+asyncpg://" + v[len("postgresql://") :]
        return v

    @model_validator(mode="after")
    def default_mock_driver_enabled(self) -> "Settings":
        if self.mock_driver_enabled is None:
            object.__setattr__(self, "mock_driver_enabled", False)
        if self.sqlalchemy_echo is None:
            object.__setattr__(self, "sqlalchemy_echo", self.app_env == "development")
        if self.log_level is None:
            object.__setattr__(
                self,
                "log_level",
                "DEBUG" if self.app_env in ("development", "test") else "INFO",
            )
        if self.log_format is None:
            object.__setattr__(
                self,
                "log_format",
                "text" if self.app_env in ("development", "test") else "json",
            )
        return self

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, v: object) -> list[str]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [origin.strip() for origin in v.split(",")]
        return v  # type: ignore[return-value]

    @field_validator("clear_otp_limits_phones", "otp_bypass_phones", mode="before")
    @classmethod
    def parse_phone_list(cls, v: object) -> list[str]:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
            except json.JSONDecodeError:
                return [phone.strip() for phone in v.split(",") if phone.strip()]
            if isinstance(parsed, list):
                return [str(phone) for phone in parsed]
        return v  # type: ignore[return-value]

    @field_validator("seed_test_users", mode="before")
    @classmethod
    def parse_seed_test_users(cls, v: object) -> list[dict[str, str]]:
        if isinstance(v, str):
            parsed = json.loads(v)
            if not isinstance(parsed, list):
                raise ValueError("SEED_TEST_USERS must be a JSON array")
            return [
                {str(k): str(val) for k, val in entry.items()}
                for entry in parsed
                if isinstance(entry, dict)
            ]
        return v  # type: ignore[return-value]


@lru_cache
def get_settings() -> Settings:
    return Settings()

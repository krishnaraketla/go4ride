from pydantic import BaseModel, Field


class SettingsResponse(BaseModel):
    notifications_enabled: bool
    language: str


class SettingsUpdateRequest(BaseModel):
    notifications_enabled: bool | None = None
    language: str | None = Field(None, min_length=2, max_length=8)

from pydantic import BaseModel, Field


class EmailVerifyRequest(BaseModel):
    code: str = Field(..., min_length=4, max_length=64)


class EmailVerificationSentResponse(BaseModel):
    message: str
    debug_code: str | None = None

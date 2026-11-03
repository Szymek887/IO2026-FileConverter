from typing import Literal

from pydantic import BaseModel, Field


class RequestOtpRequest(BaseModel):
    # Plain `str` (not EmailStr) so an invalid address returns our own INVALID_EMAIL code
    # instead of a generic VALIDATION_ERROR.
    email: str


class RequestOtpResponse(BaseModel):
    status: Literal["ok"] = "ok"
    message: str
    otp_expires: int
    resend_available_in: int


class VerifyOtpRequest(BaseModel):
    email: str
    code: str = Field(pattern=r"^[0-9]{6}$")


class SessionInfo(BaseModel):
    email: str
    session_expires: int

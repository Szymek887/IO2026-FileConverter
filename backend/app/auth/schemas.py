from typing import Literal

from pydantic import BaseModel


class RequestOtpRequest(BaseModel):
    # Plain `str` (not EmailStr) so an invalid address returns our own INVALID_EMAIL code
    # instead of a generic VALIDATION_ERROR.
    email: str


class RequestOtpResponse(BaseModel):
    status: Literal["ok"] = "ok"
    message: str
    otp_expires: int
    resend_available_in: int

from __future__ import annotations

import uuid
from datetime import datetime

import email_validator
from pydantic import BaseModel, ConfigDict, Field, field_validator


def _validate_and_normalize_email(v: str, check_mx: bool = True) -> str:
    if not v or not isinstance(v, str):
        raise ValueError("Email address cannot be empty")
    clean = v.strip().lower()
    # Permit .demo domain for local seeded fixtures
    if clean.endswith(".demo"):
        try:
            info = email_validator.validate_email(clean, check_deliverability=False)
            return info.normalized
        except Exception as exc:
            raise ValueError(f"Invalid email syntax: {exc}") from exc
    try:
        info = email_validator.validate_email(clean, check_deliverability=check_mx)
        return info.normalized
    except email_validator.EmailSyntaxError as exc:
        raise ValueError(f"Invalid email syntax: {exc}") from exc
    except email_validator.EmailUndeliverableError as exc:
        raise ValueError(f"Domain does not exist or has no valid MX records: {exc}") from exc
    except Exception as exc:
        raise ValueError(f"Email validation failed: {exc}") from exc


class SignupRequest(BaseModel):
    email: str = Field(description="User email address")
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=10, max_length=200)

    @field_validator("email")
    @classmethod
    def validate_signup_email(cls, v: str) -> str:
        return _validate_and_normalize_email(v, check_mx=True)


class LoginRequest(BaseModel):
    email: str = Field(description="User email address")
    password: str

    @field_validator("email")
    @classmethod
    def validate_login_email(cls, v: str) -> str:
        return _validate_and_normalize_email(v, check_mx=True)


class VerifyOtpRequest(BaseModel):
    email: str = Field(description="User email address")
    purpose: str = Field(pattern=r"^(signup|login)$")
    code: str = Field(pattern=r"^\d{6}$", description="6-digit verification code")

    @field_validator("email")
    @classmethod
    def validate_verify_email(cls, v: str) -> str:
        return _validate_and_normalize_email(v, check_mx=False)


class ResendOtpRequest(BaseModel):
    email: str = Field(description="User email address")
    purpose: str = Field(pattern=r"^(signup|login)$")

    @field_validator("email")
    @classmethod
    def validate_resend_email(cls, v: str) -> str:
        return _validate_and_normalize_email(v, check_mx=False)


class OtpRequiredResponse(BaseModel):
    status: str = "otp_required"
    email: str
    purpose: str
    message: str


class OtpResentResponse(BaseModel):
    status: str = "otp_sent"
    email: str
    message: str



class WorkspaceMembershipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    workspace_id: uuid.UUID
    workspace_name: str
    workspace_slug: str
    role_key: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    is_platform_super_admin: bool
    created_at: datetime


class MeResponse(BaseModel):
    user: UserOut
    memberships: list[WorkspaceMembershipOut]
    active_workspace_id: uuid.UUID | None
    google_oauth_enabled: bool


class GoogleOAuthUrlResponse(BaseModel):
    url: str
    enabled: bool


class GoogleOAuthCallbackRequest(BaseModel):
    code: str | None = None
    id_token: str | None = None
    redirect_uri: str | None = None


class FirebaseAuthRequest(BaseModel):
    id_token: str

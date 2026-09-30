import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class _EmailBody(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class RegisterRequest(_EmailBody):
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(_EmailBody):
    # No min length here: a policy change must never turn a wrong-password 401 into a 422.
    password: str = Field(min_length=1, max_length=128)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str

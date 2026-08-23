"""Esquemas pydantic de entrada de secrets (docs/freya-api-contract.md §9)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SecretType = Literal[
    "rsa_private", "rsa_public", "api_key", "db_credentials", "certificate",
    "token", "generic", "ca_key", "ca_cert",
]


class SecretCreate(BaseModel):
    key: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1)
    type: SecretType = "generic"
    expires_at: str | None = None
    description: str = ""
    overwrite: bool = False


class SecretUpdate(BaseModel):
    value: str = Field(min_length=1)
    expires_at: str | None = None


class SecretRotate(BaseModel):
    new_value: str = Field(min_length=1)

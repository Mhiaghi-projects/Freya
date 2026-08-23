"""Esquemas pydantic de entrada de storage (docs/freya-api-contract.md §5)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BucketCreate(BaseModel):
    versioning: bool = False
    encryption: bool = False
    max_versions: int = Field(default=5, ge=1, le=100)
    quota_bytes: int | None = None

"""Esquemas de petición (docs/freya-api-contract.md §6)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RepoCreate(BaseModel):
    repo_name: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,99}$")
    description: str = ""
    default_branch: str = "main"
    visibility: str = "private"
    sensitive: bool = False
    github_mirror_url: str | None = None
    github_sync_enabled: bool = False
    secret_validation_enabled: bool = True


class BranchCreate(BaseModel):
    name: str
    from_commit: str


class TagCreate(BaseModel):
    name: str
    target_commit: str
    message: str = ""

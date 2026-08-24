"""Esquemas de petición."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PageCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    parent_id: str | None = None


class BlockCreate(BaseModel):
    block_type: str
    content: str = ""


class AttachmentCreate(BaseModel):
    bucket: str = Field(min_length=1, max_length=100)
    object_key: str = Field(min_length=1, max_length=1024)
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = "application/octet-stream"

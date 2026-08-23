"""Esquemas de petición (docs/freya-api-contract.md §8, recortado)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PipelineCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    service: str = Field(min_length=1, max_length=64)
    pipeline_type: str = "standard-tests"


class TriggerRequest(BaseModel):
    triggered_by: str = "manual"
    trigger_ref: str | None = None


class DeploymentCreate(BaseModel):
    service: str = Field(min_length=1, max_length=64)
    version_ref: str = Field(min_length=1, max_length=200)
    pipeline_run_id: str

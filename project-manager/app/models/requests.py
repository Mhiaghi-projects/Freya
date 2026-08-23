"""Esquemas de petición (docs/freya-api-contract.md §7)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    project_name: str = Field(min_length=1, max_length=200)
    description: str = ""
    project_type: str
    visibility: str = "private"
    difficulty: int | None = None
    linked_git_repo: str | None = None
    ci_cd_enabled: bool = False
    team_members: list[str] = Field(default_factory=list)


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    acceptance_criteria: str = ""
    status: str = "backlog"
    priority: str = "medium"
    difficulty: int = 3
    story_points: int | None = None
    estimated_hours: float | None = None
    assigned_to: str | None = None
    milestone_id: str | None = None
    sprint_id: str | None = None
    labels: list[str] = Field(default_factory=list)
    start_date: str | None = None
    due_date: str | None = None
    depends_on: list[str] = Field(default_factory=list)


class TaskUpdate(BaseModel):
    status: str | None = None
    priority: str | None = None
    assigned_to: str | None = None
    actual_hours: float | None = None
    position: int | None = None


class MilestoneCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    target_date: str | None = None


class SprintCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    goal: str = ""
    start_date: str | None = None
    end_date: str | None = None
    task_ids: list[str] = Field(default_factory=list)


class SprintUpdate(BaseModel):
    status: str | None = None


class CommitLink(BaseModel):
    repo_id: str
    commit_hash: str

"""Validaciones puras de app/domain/{projects,tasks}.py, sin red ni base."""

from __future__ import annotations

import pytest
from freya_common import FreyaError

from app.domain.projects import validate_project_rules
from app.domain.tasks import (
    HOURS_BY_DIFFICULTY,
    validate_difficulty,
    validate_priority,
    validate_story_points,
)


def test_project_type_valido_no_lanza() -> None:
    validate_project_rules(
        project_type="programming", ci_cd_enabled=True, linked_git_repo="repo_x"
    )
    validate_project_rules(
        project_type="general", ci_cd_enabled=False, linked_git_repo=None
    )


def test_project_type_invalido_lanza_422() -> None:
    with pytest.raises(FreyaError) as exc_info:
        validate_project_rules(
            project_type="woodworking", ci_cd_enabled=False, linked_git_repo=None
        )
    assert exc_info.value.status_code == 422


def test_ci_cd_solo_para_programming() -> None:
    with pytest.raises(FreyaError) as exc_info:
        validate_project_rules(
            project_type="electronics", ci_cd_enabled=True, linked_git_repo=None
        )
    assert exc_info.value.status_code == 422


def test_linked_git_repo_no_valido_en_general() -> None:
    with pytest.raises(FreyaError) as exc_info:
        validate_project_rules(
            project_type="general", ci_cd_enabled=False, linked_git_repo="repo_x"
        )
    assert exc_info.value.status_code == 422


@pytest.mark.parametrize("difficulty", [1, 2, 3, 4, 5])
def test_difficulty_valida_no_lanza(difficulty: int) -> None:
    validate_difficulty(difficulty)


@pytest.mark.parametrize("difficulty", [0, 6, -1, 10])
def test_difficulty_invalida_lanza_422(difficulty: int) -> None:
    with pytest.raises(FreyaError) as exc_info:
        validate_difficulty(difficulty)
    assert exc_info.value.status_code == 422


def test_hours_by_difficulty_cubre_1_a_5_y_crece() -> None:
    assert set(HOURS_BY_DIFFICULTY) == {1, 2, 3, 4, 5}
    values = [HOURS_BY_DIFFICULTY[d] for d in sorted(HOURS_BY_DIFFICULTY)]
    assert values == sorted(values)  # monótona: más dificultad, más horas


def test_priority_valida_no_lanza() -> None:
    for priority in ("low", "medium", "high", "critical"):
        validate_priority(priority)


def test_priority_invalida_lanza_422() -> None:
    with pytest.raises(FreyaError) as exc_info:
        validate_priority("urgentissimo")
    assert exc_info.value.status_code == 422


def test_story_points_fibonacci_valido_no_lanza() -> None:
    for points in (1, 2, 3, 5, 8, 13, 21):
        validate_story_points(points)
    validate_story_points(None)


def test_story_points_no_fibonacci_lanza_422() -> None:
    with pytest.raises(FreyaError) as exc_info:
        validate_story_points(4)
    assert exc_info.value.status_code == 422

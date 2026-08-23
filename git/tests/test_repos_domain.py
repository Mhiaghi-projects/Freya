"""Validaciones puras de app/domain/repos.py, sin red."""

from __future__ import annotations

import pytest
from freya_common import FreyaError

from app.domain.repos import validate_repo_name


def test_nombre_valido_no_lanza() -> None:
    validate_repo_name("fortuna-api")
    validate_repo_name("a1")
    validate_repo_name("my.repo_name")


@pytest.mark.parametrize("name", ["", "A", "Fortuna", "-leading-dash", "x" * 200])
def test_nombre_invalido_lanza_422(name: str) -> None:
    with pytest.raises(FreyaError) as exc_info:
        validate_repo_name(name)
    assert exc_info.value.status_code == 422

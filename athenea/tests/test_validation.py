"""Validaciones puras de app/domain/blocks.py, sin red ni base."""

from __future__ import annotations

import pytest
from freya_common import FreyaError

from app.domain.blocks import validate_block_type


@pytest.mark.parametrize("block_type", ["text", "heading", "todo"])
def test_block_type_valido_no_lanza(block_type: str) -> None:
    validate_block_type(block_type)


def test_block_type_invalido_lanza_422() -> None:
    with pytest.raises(FreyaError) as exc_info:
        validate_block_type("video")
    assert exc_info.value.status_code == 422

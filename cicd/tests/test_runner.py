"""Pruebas de app/domain/runner.py, sobre todo la barrera de seguridad de
validate_service_name -- es la única puerta entre lo que alguien manda en
el body de una petición HTTP y un subprocess `docker build`/`docker run`.
Sin red, sin Docker real: un workspace de mentira en tmp_path.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from freya_common import UnprocessableEntity

from app.domain.runner import (
    InvalidPipelineSpecError,
    InvalidServiceError,
    load_pipeline_steps,
    validate_service_name,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    # Cada servicio es su propio proyecto en la raíz del workspace, no un
    # subdirectorio de services/ (services/ sólo aloja ya backends de
    # terceros sin código propio, sin Dockerfile ni pipeline).
    (tmp_path / "storage").mkdir(parents=True)
    (tmp_path / "storage" / "Dockerfile").write_text("FROM scratch\n")
    (tmp_path / "no-dockerfile").mkdir(parents=True)
    return tmp_path


def test_servicio_real_devuelve_la_ruta_del_dockerfile(workspace: Path) -> None:
    result = validate_service_name("storage", workspace=workspace)
    assert result == (workspace / "storage" / "Dockerfile").resolve()


def test_servicio_sin_dockerfile_lanza(workspace: Path) -> None:
    with pytest.raises(InvalidServiceError):
        validate_service_name("no-dockerfile", workspace=workspace)


def test_servicio_inexistente_lanza(workspace: Path) -> None:
    with pytest.raises(InvalidServiceError):
        validate_service_name("no-existe-este-servicio", workspace=workspace)


@pytest.mark.parametrize(
    "malicious",
    [
        "../../etc",
        "../secrets",
        "storage/../../../etc",
        "storage/../auth",
        "..",
        "./storage",
        "storage;rm -rf /",
        "storage && echo pwned",
        "storage$(whoami)",
        "storage`whoami`",
        "STORAGE",
        "",
        " storage",
        "storage ",
        "/etc/passwd",
        "storage\nauth",
    ],
)
def test_nombre_malicioso_o_invalido_lanza(malicious: str, workspace: Path) -> None:
    with pytest.raises(InvalidServiceError):
        validate_service_name(malicious, workspace=workspace)


def test_nombre_que_pasa_el_regex_pero_no_existe_igual_lanza(workspace: Path) -> None:
    # El regex por sí solo no basta como prueba de "válido": un nombre bien
    # formado que no corresponda a un Dockerfile real también se rechaza.
    with pytest.raises(InvalidServiceError):
        validate_service_name("nonexistent-service", workspace=workspace)


def test_sin_pipeline_yaml_usa_lint_y_test_por_defecto(workspace: Path) -> None:
    assert load_pipeline_steps("storage", workspace=workspace) == ["lint", "test"]


def test_pipeline_yaml_elige_los_pasos_y_el_orden(workspace: Path) -> None:
    freya_dir = workspace / "storage" / ".freya"
    freya_dir.mkdir()
    (freya_dir / "pipeline.yaml").write_text(
        "steps:\n  - security_scan\n  - lint\n", encoding="utf-8"
    )
    assert load_pipeline_steps("storage", workspace=workspace) == [
        "security_scan",
        "lint",
    ]


def test_pipeline_yaml_con_paso_desconocido_lanza(workspace: Path) -> None:
    freya_dir = workspace / "storage" / ".freya"
    freya_dir.mkdir()
    (freya_dir / "pipeline.yaml").write_text(
        "steps:\n  - lint\n  - deploy_a_produccion\n", encoding="utf-8"
    )
    with pytest.raises(InvalidPipelineSpecError):
        load_pipeline_steps("storage", workspace=workspace)


def test_pipeline_yaml_sin_steps_lanza(workspace: Path) -> None:
    freya_dir = workspace / "storage" / ".freya"
    freya_dir.mkdir()
    (freya_dir / "pipeline.yaml").write_text("version: 1\n", encoding="utf-8")
    with pytest.raises(InvalidPipelineSpecError):
        load_pipeline_steps("storage", workspace=workspace)


def test_pipeline_yaml_invalido_lanza(workspace: Path) -> None:
    freya_dir = workspace / "storage" / ".freya"
    freya_dir.mkdir()
    (freya_dir / "pipeline.yaml").write_text("steps: [lint\n", encoding="utf-8")
    with pytest.raises(InvalidPipelineSpecError):
        load_pipeline_steps("storage", workspace=workspace)


async def test_pipeline_type_no_soportado_lanza_422_sin_tocar_la_base() -> None:
    from app.domain.pipelines import create_pipeline

    with pytest.raises(UnprocessableEntity):
        # client=None: la validación del tipo pasa ANTES de cualquier
        # llamada a gestor-db -- si esto tocara la base, fallaría con otro
        # error antes de llegar al UnprocessableEntity esperado.
        await create_pipeline(
            None,  # type: ignore[arg-type]
            "freya",
            name="x",
            service="storage",
            pipeline_type="custom-yaml-pipeline",
        )

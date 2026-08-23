"""Runner de pipelines, deliberadamente estrecho (decidido en vivo con el
usuario, ver cicd/README.md): nunca ejecuta código arbitrario de
un pipeline definido por YAML. Lo que SÍ admite -- pedido explícitamente
después ("todo esté en yaml", ver README) -- es que cada servicio traiga un
`.freya/pipeline.yaml` que elija QUÉ pasos de una lista cerrada correr y en
qué orden, nunca QUÉ COMANDO ejecuta cada uno: los tres pasos posibles
siguen fijos en este fichero, reproduciendo exactamente `Invoke-FreyaTest`
de infra/powershell/FreyaServices.psm1 más un escaneo de seguridad:

    docker build --target dev --tag freya/<servicio>:test \\
        --file <servicio>/Dockerfile .
    docker run --rm --network none freya/<servicio>:test ruff check /srv/app
    docker run --rm --network none freya/<servicio>:test pytest -q /srv/tests
    docker run --rm freya/<servicio>:test pip-audit   # necesita red: consulta
                                                        # la base de CVEs, ver
                                                        # docs/ARCHITECTURE.md §4

`<servicio>` se valida contra un patrón estricto Y contra la existencia
real de `<servicio>/Dockerfile` dentro del workspace ANTES de
construir cualquier ruta o lanzar cualquier subproceso -- ninguna entrada
de usuario llega a una shell (subprocess siempre con lista de argumentos,
nunca `shell=True`), pero la validación de nombre existe igual como
segunda barrera contra recorrido de rutas. `.freya/pipeline.yaml` se lee
del mismo workspace de sólo lectura, nunca del cuerpo de una petición HTTP.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.config import get_settings

_SERVICE_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}$")

# (comando, necesita_red). lint/test corren con --network none (aislamiento
# real: no deben poder llamar a nada); security_scan necesita salir a
# consultar la base de vulnerabilidades de pip-audit, la misma excepción ya
# documentada para cicd en docs/ARCHITECTURE.md §4 ("cicd los registros de
# paquetes").
_STEP_COMMANDS: dict[str, tuple[list[str], bool]] = {
    "lint": (["ruff", "check", "/srv/app"], False),
    # -v, no -q: cada función de test queda nombrada en el log
    # ("tests/test_x.py::test_y PASSED"), visible sin abrir el fichero --
    # nunca un "run:" arbitrario por YAML (ver cicd/README.md).
    "test": (["pytest", "-v", "/srv/tests"], False),
    "security_scan": (["pip-audit"], True),
    # Construye un wheel real de /srv/app (necesita su pyproject.toml ahí
    # mismo -- ver freya-common/Dockerfile) y lo imprime en
    # base64 por stdout: es el único modo de sacar un fichero de un
    # `docker run` efímero sin montar rutas del host (runs.py decodifica
    # y sube el resultado a storage, nunca este módulo -- aquí sólo se
    # ejecutan subprocesos). --no-build-isolation/--no-deps: las
    # dependencias ya están instaladas en la imagen, así que no necesita
    # red pese a compartir el catálogo con security_scan.
    "build_artifact": (
        [
            "sh",
            "-c",
            "cd /srv/app && pip wheel . --no-deps --no-build-isolation -q "
            "-w /tmp/wheelhouse && base64 -w0 /tmp/wheelhouse/*.whl",
        ],
        False,
    ),
}
_DEFAULT_STEPS = ["lint", "test"]


class InvalidServiceError(ValueError):
    pass


class InvalidPipelineSpecError(ValueError):
    pass


def load_pipeline_steps(service: str, *, workspace: Path | None = None) -> list[str]:
    """Lee <servicio>/.freya/pipeline.yaml si existe. Sólo admite
    `steps: [...]` con valores de _STEP_COMMANDS -- cualquier otra clave o
    paso desconocido falla cerrado (fail closed), nunca se ignora en
    silencio. Sin fichero, el pipeline por defecto es lint+test (igual que
    antes de que existiera este mecanismo)."""
    if workspace is None:
        workspace = Path(get_settings().workspace_dir)
    spec_path = workspace.resolve() / service / ".freya" / "pipeline.yaml"
    if not spec_path.is_file():
        return list(_DEFAULT_STEPS)

    try:
        spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise InvalidPipelineSpecError(f"{spec_path} no es YAML válido: {exc}") from exc

    if not isinstance(spec, dict) or "steps" not in spec:
        raise InvalidPipelineSpecError(f"{spec_path} necesita una clave 'steps'")
    steps = spec["steps"]
    if not isinstance(steps, list) or not steps:
        raise InvalidPipelineSpecError(
            f"{spec_path}: 'steps' debe ser una lista no vacía"
        )

    unknown = [s for s in steps if s not in _STEP_COMMANDS]
    if unknown:
        raise InvalidPipelineSpecError(
            f"{spec_path}: paso(s) no soportado(s) {unknown} -- "
            f"sólo se admite {sorted(_STEP_COMMANDS)}"
        )
    return list(steps)


@dataclass
class JobResult:
    name: str
    exit_code: int
    log: str


@dataclass
class RunResult:
    success: bool
    jobs: list[JobResult] = field(default_factory=list)


def validate_service_name(service: str, *, workspace: Path | None = None) -> Path:
    """Devuelve la ruta del Dockerfile si `service` es un nombre de
    servicio real dentro del workspace. Lanza InvalidServiceError si no.

    Cada servicio propio es su propio proyecto en la raíz del repo (su
    propio git, su propio pipeline), no un subdirectorio de services/ --
    ahí sólo quedan los backends de terceros sin código propio (database,
    metrics, logs, dashboards), que nunca tienen pipeline."""
    if not _SERVICE_NAME_RE.match(service):
        raise InvalidServiceError(f"'{service}' no es un nombre de servicio válido")

    if workspace is None:
        workspace = Path(get_settings().workspace_dir)
    workspace = workspace.resolve()
    dockerfile = (workspace / service / "Dockerfile").resolve()

    # Segunda barrera: aunque el regex ya lo impide, confirma que la ruta
    # resuelta sigue dentro del workspace -- nunca fiarse de un solo control.
    if workspace not in dockerfile.parents:
        raise InvalidServiceError(f"'{service}' resuelve fuera del workspace")
    if not dockerfile.is_file():
        raise InvalidServiceError(f"No existe {service}/Dockerfile")
    return dockerfile


async def _run(
    args: list[str], *, timeout: float, cwd: str | None = None
) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return -1, f"tiempo agotado tras {timeout}s"
    return proc.returncode or 0, stdout.decode("utf-8", errors="replace")


async def run_standard_tests(service: str) -> RunResult:
    """Construye la imagen de test del servicio y corre los pasos de su
    .freya/pipeline.yaml (o lint+test por defecto si no lo tiene), cada uno
    reproduciendo exactamente lo que ya hacía `.\\freya.ps1 lint`/`test`/el
    nuevo escaneo de seguridad. Nunca acepta un Dockerfile, comando o
    imagen que no sea uno de los tres caminos fijos de _STEP_COMMANDS."""
    settings = get_settings()
    dockerfile = validate_service_name(service)
    steps = load_pipeline_steps(service)
    image = f"freya/{service}:test"

    build_code, build_log = await _run(
        [
            settings.docker_binary,
            "build",
            "--quiet",
            "--target",
            "dev",
            "--tag",
            image,
            "--file",
            str(dockerfile),
            settings.workspace_dir,
        ],
        timeout=settings.build_timeout_seconds,
    )
    if build_code != 0:
        return RunResult(
            success=False,
            jobs=[JobResult(name="build", exit_code=build_code, log=build_log)],
        )

    jobs = [JobResult(name="build", exit_code=0, log=build_log)]
    success = True
    for job_name in steps:
        command, needs_network = _STEP_COMMANDS[job_name]
        run_args = [settings.docker_binary, "run", "--rm"]
        if not needs_network:
            run_args += ["--network", "none"]
        # El usuario "freya" de la imagen no tiene home real (-M en el
        # Dockerfile): sin esto, pip-audit no puede crear su caché en
        # ~/.cache y falla con PermissionError antes de escanear nada.
        run_args += ["--env", "HOME=/tmp"]
        run_args += [image, *command]

        code, log = await _run(run_args, timeout=settings.run_timeout_seconds)
        jobs.append(JobResult(name=job_name, exit_code=code, log=log))
        if code != 0:
            success = False

    return RunResult(success=success, jobs=jobs)

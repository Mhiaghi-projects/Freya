<#
.SYNOPSIS
    Control de la plataforma Freya desde PowerShell.

.DESCRIPTION
    Unico punto de entrada en Windows. El host solo necesita Docker Desktop:
    ni Python, ni openssl, ni WSL, ni Git Bash. Todo lo que este script hace
    ocurre dentro de contenedores.

.EXAMPLE
    .\freya.ps1 init
    Crea las redes de Docker, construye el toolbox y emite los certificados.

.EXAMPLE
    .\freya.ps1 phase 1
    Levanta todos los servicios de la fase 1 (database y gestor-db).

.EXAMPLE
    .\freya.ps1 logs gestor-db -Follow
    Sigue los logs de un servicio.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet(
        'init', 'up', 'down', 'restart', 'logs', 'status', 'phase',
        'new', 'test', 'lint', 'secret', 'validate', 'import-backlog', 'doctor',
        'fix-eol', 'shell', 'backup', 'restore-check', 'signing-key',
        'init-internal-ca', 'renew-cert', 'import-bootstrap-secrets',
        'rotate-signing-key', 'help'
    )]
    [string]$Command = 'help',

    [Parameter(Position = 1)]
    [string]$Target,

    [Parameter(Position = 2)]
    [string]$Extra,

    [int]$Port = 0,
    [int]$Tail = 200,
    [switch]$Follow,
    [switch]$NoBuild,
    [switch]$Volumes,
    # Sólo para 'secret': dueño no estándar (uid:gid) del fichero generado,
    # para backends de terceros que no corren como el UID 10001 "freya" de
    # los servicios propios -- p.ej. Grafana (472:472).
    [string]$Owner = '10001:10001'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Windows PowerShell 5.1 basta. Se evita a proposito cualquier sintaxis de
# PowerShell 7 para no obligar a instalarlo.
if ($PSVersionTable.PSVersion.Major -lt 5) {
    Write-Host 'Se necesita PowerShell 5.1 o superior.' -ForegroundColor Red
    exit 1
}

Import-Module (Join-Path $PSScriptRoot 'infra\powershell\FreyaCore.psm1') -Force -DisableNameChecking
Import-Module (Join-Path $PSScriptRoot 'infra\powershell\FreyaServices.psm1') -Force -DisableNameChecking

function Show-FreyaHelp {
    @'
Freya - control de la plataforma

USO
  .\freya.ps1 <comando> [destino] [opciones]

PUESTA EN MARCHA
  init                     crea redes, construye el toolbox y emite certificados
  doctor                   diagnostica el entorno cuando algo no arranca
  fix-eol                  convierte los .sh y .py a LF (tras un clon con CRLF)

SERVICIOS
  up <servicio>            construye y levanta un servicio
  down <servicio>          lo para       (-Volumes borra tambien sus datos)
  restart <servicio>       lo reinicia
  logs <servicio>          muestra sus logs (-Follow para seguirlos)
  status                   estado de los 11 servicios
  phase <n>                levanta todos los servicios de la fase n

DESARROLLO
  new <servicio> [-Port n] crea un servicio desde la plantilla
  test <servicio>          ejecuta sus tests dentro de su contenedor
  lint <servicio>          pasa ruff sobre su codigo, en contenedor
  secret <servicio> <nombre>  genera un secreto aleatorio (-Owner uid:gid si no es 10001:10001)
  validate                 valida el backlog de projects\
  import-backlog           importa projects\*.yaml a project-manager (pm-08)
  shell                    abre una shell en el toolbox
  backup <servicio>        vuelca sus datos y los sube a storage (hoy: database)
  restore-check <servicio> <clave-storage>  verifica un volcado en base temporal
  signing-key <servicio>   genera un par de claves Ed25519 (hoy: auth)
  init-internal-ca         importa infra\certs\ca a secrets (una sola vez)
  renew-cert <servicio>    pide un certificado nuevo a la CA interna de secrets
  import-bootstrap-secrets echa infra\secrets\* al vault de secrets (auditoria)
  rotate-signing-key <servicio>  sube una clave de firma nueva a secrets (hoy: auth)

OPCIONES
  -Follow      sigue los logs en vivo
  -NoBuild     levanta sin reconstruir la imagen
  -Volumes     con "down", elimina tambien los volumenes
  -Tail <n>    lineas de log a mostrar (por defecto 200)
  -Port <n>    puerto al crear un servicio fuera del registro

EJEMPLOS
  .\freya.ps1 init
  .\freya.ps1 new gestor-db
  .\freya.ps1 phase 1
  .\freya.ps1 logs gestor-db -Follow
  .\freya.ps1 down database -Volumes

Nada de esto se ejecuta en el host: solo se habla con Docker.
'@ | Write-Host
}

function Assert-Target {
    param([string]$Value, [string]$What)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "Falta $What. Ejecuta '.\freya.ps1 help' para ver el uso."
    }
}

function Invoke-FreyaInit {
    Assert-Docker
    Write-FreyaOk 'Docker responde'

    Initialize-FreyaNetworks
    Build-Toolbox
    New-FreyaCertificates

    Write-Host ''
    Write-FreyaOk 'Freya inicializada'
    Write-Host '  Siguiente paso: .\freya.ps1 new gestor-db' -ForegroundColor DarkGray
}

function Invoke-FreyaShell {
    Build-Toolbox
    $mount = ConvertTo-DockerPath (Get-FreyaRoot)
    Write-FreyaInfo 'toolbox: el repositorio esta montado en /workspace. Escribe exit para salir.'
    docker run --rm -it --volume "${mount}:/workspace" --workdir /workspace --network none freya/toolbox:dev bash
}

try {
    switch ($Command) {
        'init' { Invoke-FreyaInit }

        'up' {
            Assert-Target $Target 'el nombre del servicio'
            Assert-Docker
            Start-FreyaService -Service $Target -NoBuild:$NoBuild
        }

        'down' {
            Assert-Target $Target 'el nombre del servicio'
            Assert-Docker
            Stop-FreyaService -Service $Target -RemoveVolumes:$Volumes
        }

        'restart' {
            Assert-Target $Target 'el nombre del servicio'
            Assert-Docker
            Restart-FreyaService -Service $Target
        }

        'logs' {
            Assert-Target $Target 'el nombre del servicio'
            Assert-Docker
            Get-FreyaLog -Service $Target -Tail $Tail -Follow:$Follow
        }

        'status' {
            Get-FreyaStatus | Format-Table -AutoSize
        }

        'phase' {
            Assert-Target $Target 'el numero de fase'
            Assert-Docker
            Start-FreyaPhase -Phase ([int]$Target)
        }

        'new' {
            Assert-Target $Target 'el nombre del servicio'
            Assert-Docker
            New-FreyaService -Service $Target -Port $Port
        }

        'test' {
            Assert-Target $Target 'el nombre del servicio'
            Assert-Docker
            exit (Invoke-FreyaTest -Service $Target)
        }

        'lint' {
            Assert-Target $Target 'el nombre del servicio'
            Assert-Docker
            exit (Invoke-FreyaTest -Service $Target -Lint)
        }

        'secret' {
            Assert-Target $Target 'el nombre del servicio'
            Assert-Target $Extra 'el nombre del secreto'
            New-FreyaSecret -Service $Target -Name $Extra -Owner $Owner
        }

        'validate' { Test-FreyaBacklog }

        'import-backlog' {
            Assert-Docker
            Import-FreyaBacklog
        }

        'backup' {
            Assert-Target $Target 'el nombre del servicio'
            Assert-Docker
            Backup-FreyaDatabase -Service $Target
        }

        'restore-check' {
            Assert-Target $Target 'el nombre del servicio'
            Assert-Target $Extra 'la clave de storage del volcado (p.ej. database/freya-....dump)'
            Assert-Docker
            Restore-FreyaDatabaseCheck -Service $Target -Key $Extra
        }

        'signing-key' {
            Assert-Target $Target 'el nombre del servicio'
            Assert-Docker
            New-FreyaSigningKey -Service $Target
        }

        'init-internal-ca' {
            Assert-Docker
            New-FreyaInternalCA
        }

        'renew-cert' {
            Assert-Target $Target 'el nombre del servicio'
            Assert-Docker
            Update-FreyaCertificate -Service $Target
        }

        'import-bootstrap-secrets' {
            Assert-Docker
            Import-FreyaBootstrapSecrets
        }

        'rotate-signing-key' {
            Assert-Target $Target 'el nombre del servicio'
            Assert-Docker
            Update-FreyaSigningKey -Service $Target
        }

        'doctor' { exit (Invoke-FreyaDoctor) }

        'fix-eol' { Repair-FreyaLineEnding }

        'shell' { Invoke-FreyaShell }

        default { Show-FreyaHelp }
    }
}
catch {
    Write-FreyaError $_.Exception.Message
    exit 1
}

<#
.SYNOPSIS
    Primitivas de la plataforma Freya: Docker, redes, toolbox y certificados.

.DESCRIPTION
    Todo lo que este modulo hace se ejecuta dentro de contenedores. El host
    Windows solo necesita Docker Desktop: ni Python, ni openssl, ni WSL.

    No se invoca directamente. Lo carga freya.ps1.
#>

Set-StrictMode -Version Latest

$script:ToolboxImage = 'freya/toolbox:dev'

# freya-mesh NO es interna: git necesita alcanzar GitHub y cicd los registros
# de paquetes. Las redes de los gestores si lo son: nadie fuera del gestor
# puede hablar con PostgreSQL ni con los backends de metricas.
$script:Networks = @(
    [pscustomobject]@{ Name = 'freya-mesh'; Internal = $false; Purpose = 'HTTPS entre servicios' }
    [pscustomobject]@{ Name = 'freya-db';   Internal = $true;  Purpose = 'gestor-db <-> database' }
    [pscustomobject]@{ Name = 'freya-mon';  Internal = $true;  Purpose = 'gestor-monitoring <-> backends' }
    [pscustomobject]@{ Name = 'freya-edge'; Internal = $false; Purpose = 'unica puerta al exterior' }
)

function Write-FreyaInfo {
    param([Parameter(Mandatory)][string]$Message)
    Write-Host '[freya] ' -ForegroundColor Cyan -NoNewline
    Write-Host $Message
}

function Write-FreyaOk {
    param([Parameter(Mandatory)][string]$Message)
    Write-Host '[  ok  ] ' -ForegroundColor Green -NoNewline
    Write-Host $Message
}

function Write-FreyaWarn {
    param([Parameter(Mandatory)][string]$Message)
    Write-Host '[ warn ] ' -ForegroundColor Yellow -NoNewline
    Write-Host $Message
}

function Write-FreyaError {
    param([Parameter(Mandatory)][string]$Message)
    Write-Host '[error ] ' -ForegroundColor Red -NoNewline
    Write-Host $Message
}

function Get-FreyaRoot {
    <#
        Raiz del repositorio. Se calcula desde la ubicacion de este modulo,
        no desde el directorio actual, para poder invocar freya.ps1 desde
        cualquier sitio.
    #>
    return (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
}

function ConvertTo-DockerPath {
    <#
        Docker Desktop acepta rutas de Windows en -v, pero con barras normales
        y sin comillas raras. D:\Proyectos\Freya -> D:/Proyectos/Freya
    #>
    param([Parameter(Mandatory)][string]$Path)
    return ($Path -replace '\\', '/')
}

function Assert-Docker {
    <#
        Comprueba que el CLI existe y que el demonio responde. Sin esto, los
        errores posteriores son cripticos.
    #>
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'No se encuentra "docker". Instala Docker Desktop y reabre PowerShell.'
    }

    docker info --format '{{.ServerVersion}}' 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'Docker Desktop no responde. Arrancalo y espera a que el icono deje de girar.'
    }
}

function Test-DockerNetwork {
    param([Parameter(Mandatory)][string]$Name)
    docker network inspect $Name 2>&1 | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Initialize-FreyaNetworks {
    <#
        Crea las cuatro redes de Freya. Idempotente.
    #>
    foreach ($network in $script:Networks) {
        if (Test-DockerNetwork -Name $network.Name) {
            Write-FreyaInfo "red $($network.Name) ya existe"
            continue
        }

        $arguments = @('network', 'create')
        if ($network.Internal) { $arguments += '--internal' }
        $arguments += $network.Name

        docker @arguments | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "No se pudo crear la red $($network.Name)"
        }
        $scope = if ($network.Internal) { 'privada' } else { 'con salida' }
        Write-FreyaOk "red $($network.Name) creada ($scope) - $($network.Purpose)"
    }
}

function Test-ToolboxImage {
    # -join '' porque docker puede devolver varias lineas y el cast a string
    # de un array fallaria bajo StrictMode.
    $imageId = (docker images -q $script:ToolboxImage 2>$null) -join ''
    return -not [string]::IsNullOrWhiteSpace($imageId)
}

function Build-Toolbox {
    <#
        Construye la imagen del toolbox. Solo la primera vez, o con -Force.
    #>
    param([switch]$Force)

    if ((Test-ToolboxImage) -and -not $Force) { return }

    $root = Get-FreyaRoot
    Write-FreyaInfo 'construyendo la imagen del toolbox (solo la primera vez)'

    docker build --quiet `
        --tag $script:ToolboxImage `
        --file (Join-Path $root 'infra\toolbox\Dockerfile') `
        (Join-Path $root 'infra\toolbox') | Out-Null

    if ($LASTEXITCODE -ne 0) { throw 'Fallo la construccion del toolbox' }
    Write-FreyaOk 'toolbox listo'
}

function Invoke-Toolbox {
    <#
    .SYNOPSIS
        Ejecuta un comando dentro del contenedor toolbox, con el repositorio
        montado en /workspace.

    .DESCRIPTION
        Sin red por defecto (emitir certificados o generar un servicio desde
        la plantilla no necesita salir del contenedor). -Network permite
        excepciones puntuales y explícitas, como importar el backlog contra
        project-manager (Import-FreyaBacklog): sigue siendo el toolbox quien
        orquesta, nunca un servicio leyendo projects/*.yaml por su cuenta.

    .EXAMPLE
        Invoke-Toolbox -Arguments @('bash', 'infra/scripts/gen_dev_ca.sh')
    #>
    param(
        [Parameter(Mandatory)][string[]]$Arguments,
        [switch]$Quiet,
        [string]$Network = 'none',
        [string[]]$ExtraDockerArgs = @()
    )

    Build-Toolbox
    $mount = ConvertTo-DockerPath (Get-FreyaRoot)

    $dockerArguments = @(
        'run', '--rm',
        '--volume', "${mount}:/workspace",
        '--workdir', '/workspace',
        '--network', $Network
    ) + $ExtraDockerArgs + @($script:ToolboxImage) + $Arguments

    if ($Quiet) {
        $output = docker @dockerArguments 2>&1
        return @{ ExitCode = $LASTEXITCODE; Output = $output }
    }

    docker @dockerArguments
    if ($LASTEXITCODE -ne 0) {
        throw "El comando en el toolbox fallo con codigo $LASTEXITCODE"
    }
}

function New-FreyaCertificates {
    <#
        Emite la CA de desarrollo y un certificado por servicio, dentro del
        toolbox. En la Fase 3, `secrets` asume esta tarea y esto se retira.
    #>
    Write-FreyaInfo 'emitiendo certificados de desarrollo'
    Invoke-Toolbox -Arguments @('bash', 'infra/scripts/gen_dev_ca.sh')
    Write-FreyaOk 'certificados en infra\certs (no versionados)'
}

function New-FreyaSecret {
    <#
    .SYNOPSIS
        Genera un secreto aleatorio en infra\secrets\<servicio>\<nombre>.

    .EXAMPLE
        New-FreyaSecret -Service gestor-db -Name bootstrap_token
    #>
    param(
        [Parameter(Mandatory)][string]$Service,
        [Parameter(Mandatory)][string]$Name,
        [int]$Bytes = 32,
        # 10001 es el UID "freya" de todo Dockerfile propio (ver plantilla).
        # Un backend de terceros corre con el UID de su propia imagen -- p.ej.
        # Grafana usa 472:472 -- y necesita este valor explícito, o su
        # proceso no puede leer el secreto (falla en silencio: read_secret_file
        # atrapa el PermissionError y devuelve "", no un error claro).
        [string]$Owner = '10001:10001'
    )

    $relative = "infra/secrets/$Service/$Name"
    $full = Join-Path (Get-FreyaRoot) ($relative -replace '/', '\')

    if (Test-Path $full) {
        Write-FreyaWarn "$relative ya existe, no se sobrescribe"
        return
    }

    Invoke-Toolbox -Arguments @(
        'bash', '-c',
        "mkdir -p infra/secrets/$Service && openssl rand -hex $Bytes | tr -d '\n' > $relative && chown $Owner $relative && chmod 600 $relative"
    )
    Write-FreyaOk "secreto generado en $relative"
}

function New-FreyaSigningKey {
    <#
    .SYNOPSIS
        Genera un par de claves RSA en infra\secrets\<servicio>\signing_keys\.

    .DESCRIPTION
        RSA (RS256), no Ed25519 -- docs/freya-api-contract.md §15.1 fija RSA
        para el JWT interno de servicio. El nombre de fichero es sólo una
        marca de tiempo para ordenar; el kid real de JWKS lo calcula auth en
        Python a partir de la clave pública cargada, no del nombre del
        fichero. auth carga todos los ficheros del directorio al arrancar:
        firma con el más nuevo, publica todos en el JWKS para poder
        verificar tokens de una clave anterior mientras se retira.
    #>
    param([Parameter(Mandatory)][string]$Service)

    $dir = "infra/secrets/$Service/signing_keys"
    $full = Join-Path (Get-FreyaRoot) ($dir -replace '/', '\')
    New-Item -ItemType Directory -Force -Path $full | Out-Null

    $stamp = Get-Date -Format 'yyyyMMddHHmmss'
    Invoke-Toolbox -Arguments @(
        'bash', '-c',
        "openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out $dir/$stamp.pem 2>/dev/null && chown 10001:10001 $dir/$stamp.pem && chmod 600 $dir/$stamp.pem"
    )
    Write-FreyaOk "clave de firma generada en $dir/$stamp.pem"
}

function Test-FreyaBacklog {
    <#
        Valida projects\*.yaml y muestra la tabla de dificultad y XP.
    #>
    Write-FreyaInfo 'validando el backlog'
    Invoke-Toolbox -Arguments @('python3', 'infra/scripts/backlog_stats.py')
}

function Import-FreyaBacklog {
    <#
        Importa projects\*.yaml a project-manager por su propia API
        (ROADMAP.md pm-08). Necesita red hacia freya-mesh y el api_secret
        de project-manager -- única excepción documentada al toolbox sin
        red (ver Invoke-Toolbox).
    #>
    $secretDir = Join-Path (Get-FreyaRoot) 'infra\secrets\project-manager'
    if (-not (Test-Path (Join-Path $secretDir 'api_secret'))) {
        throw "No existe el secreto de project-manager. Levanta el servicio primero: .\freya.ps1 up project-manager"
    }
    $secretMount = ConvertTo-DockerPath $secretDir

    Write-FreyaInfo 'importando projects/*.yaml a project-manager'
    Invoke-Toolbox -Network 'freya-mesh' `
        -ExtraDockerArgs @('--volume', "${secretMount}:/run/secrets:ro") `
        -Arguments @('python3', 'infra/scripts/import_backlog.py')
}

Export-ModuleMember -Function @(
    'Write-FreyaInfo', 'Write-FreyaOk', 'Write-FreyaWarn', 'Write-FreyaError',
    'Get-FreyaRoot', 'ConvertTo-DockerPath', 'Assert-Docker',
    'Test-DockerNetwork', 'Initialize-FreyaNetworks',
    'Build-Toolbox', 'Invoke-Toolbox',
    'New-FreyaCertificates', 'New-FreyaSecret', 'New-FreyaSigningKey', 'Test-FreyaBacklog',
    'Import-FreyaBacklog'
)

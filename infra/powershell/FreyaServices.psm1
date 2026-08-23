<#
.SYNOPSIS
    Ciclo de vida de los servicios de Freya: crear, levantar, parar, inspeccionar.

.DESCRIPTION
    Todo se resuelve con "docker compose". El host no ejecuta nada del proyecto:
    solo habla con Docker.

    No se invoca directamente. Lo carga freya.ps1.
#>

Set-StrictMode -Version Latest

Import-Module (Join-Path $PSScriptRoot 'FreyaCore.psm1') -DisableNameChecking

# Registro unico de servicios. Cambiar un puerto aqui obliga a cambiarlo
# tambien en docs\ARCHITECTURE.md y en infra\scripts\gen_dev_ca.sh.
$script:Registry = [ordered]@{
    'database'          = @{ Port = 5432; Phase = 1;  Kind = 'backend' }
    'gestor-db'         = @{ Port = 8001; Phase = 1;  Kind = 'propio'  }
    'auth'              = @{ Port = 8002; Phase = 2;  Kind = 'propio'  }
    'secrets'           = @{ Port = 8003; Phase = 3;  Kind = 'propio'  }
    'storage'           = @{ Port = 8004; Phase = 4;  Kind = 'propio'  }
    'git'               = @{ Port = 8005; Phase = 5;  Kind = 'propio'  }
    'project-manager'   = @{ Port = 8006; Phase = 6;  Kind = 'propio'  }
    'metrics'           = @{ Port = 8428; Phase = 7;  Kind = 'backend' }
    'logs'              = @{ Port = 9428; Phase = 7;  Kind = 'backend' }
    'gestor-monitoring' = @{ Port = 8008; Phase = 7;  Kind = 'propio'  }
    # Perfil opcional: NO se levanta con 'phase 7' (el gate real es el
    # profile de docker compose, ver Start-FreyaService). Sólo con
    # '.\freya.ps1 up dashboards' explícito.
    'dashboards'        = @{ Port = 3000; Phase = 7;  Kind = 'backend' }
    'cicd'              = @{ Port = 8007; Phase = 8;  Kind = 'propio'  }
    # frontend ya no publica puerto propio (Port = su puerto interno en
    # freya-mesh, no uno del host) -- traefik es quien lo hace, ver abajo.
    'frontend'          = @{ Port = 8000; Phase = 9;  Kind = 'propio'  }
    # Unica puerta HTTPS al exterior (services/traefik/): enruta a frontend
    # via docker.sock, sin tocar ningun otro servicio.
    'traefik'           = @{ Port = 8000; Phase = 9;  Kind = 'backend' }
    'gamification'      = @{ Port = 8009; Phase = 10; Kind = 'propio'  }
    # Herramienta, no un servicio de la malla: sin puerto HTTP propio, y sin
    # fase -- se levanta a mano una vez el PAT esté en
    # infra/secrets/github-runner/ (ver README ahí), nunca por 'phase N'.
    'github-runner'     = @{ Port = 0;    Phase = 0;  Kind = 'backend' }
}

function Get-FreyaRegistry { return $script:Registry }

function Get-FreyaServicePort {
    param([Parameter(Mandatory)][string]$Service)
    if (-not $script:Registry.Contains($Service)) {
        throw "Servicio '$Service' desconocido. Conocidos: $($script:Registry.Keys -join ', ')"
    }
    return $script:Registry[$Service].Port
}

function Get-FreyaComposeFile {
    <#
        Ruta al docker-compose.yml del servicio. Cada servicio propio es su
        propio proyecto en la raiz del repo (su propio git, su propio
        pipeline) -- se busca ahi primero. services\ solo aloja ya los
        backends de terceros sin codigo propio que separar (database,
        metrics, logs, dashboards), asi que se revisa como respaldo. Falla
        claro si no existe en ninguno de los dos sitios.
    #>
    param([Parameter(Mandatory)][string]$Service)

    $root = Get-FreyaRoot
    $topLevel = Join-Path $root "$Service\docker-compose.yml"
    if (Test-Path $topLevel) { return $topLevel }

    $underServices = Join-Path $root "services\$Service\docker-compose.yml"
    if (Test-Path $underServices) { return $underServices }

    throw "No existe $Service\docker-compose.yml ni services\$Service\docker-compose.yml. Crea el servicio primero: .\freya.ps1 new $Service"
}

function Invoke-FreyaCompose {
    param(
        [Parameter(Mandatory)][string]$Service,
        [Parameter(Mandatory)][string[]]$Arguments,
        [string[]]$Profiles = @()
    )

    $compose = Get-FreyaComposeFile -Service $Service
    $root = Get-FreyaRoot
    Push-Location $root
    try {
        # Mismo nombre de proyecto para las 13 llamadas independientes a
        # "docker compose": sin esto, cada docker-compose.yml (uno por
        # servicio, en su propia carpeta) cae al nombre por defecto (el de
        # su directorio) y Docker Desktop los muestra como 13 grupos
        # sueltos en vez de uno solo.
        $composeArgs = @('--project-name', 'freya', '--file', $compose)

        # docker compose resuelve .env relativo al fichero compose, no a la
        # raiz del repo: sin esto, cada servicio ignora en silencio el .env
        # compartido y cae a los valores por defecto del docker-compose.yml.
        $envFile = Join-Path $root '.env'
        if (Test-Path $envFile) {
            $composeArgs += @('--env-file', $envFile)
        }

        # --profile es una opcion global de compose (va antes del
        # subcomando): sin ella, un servicio marcado "profiles:" en su
        # compose.yml (p.ej. dashboards/Grafana) no arranca con "up" a secas
        # -- es justo el mecanismo que lo mantiene apagado por defecto.
        foreach ($p in $Profiles) { $composeArgs += @('--profile', $p) }

        docker compose @composeArgs @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "docker compose fallo para '$Service' (codigo $LASTEXITCODE)"
        }
    }
    finally {
        Pop-Location
    }
}

function Start-FreyaService {
    param(
        [Parameter(Mandatory)][string]$Service,
        [switch]$NoBuild
    )

    $arguments = @('up', '--detach')
    if (-not $NoBuild) { $arguments += '--build' }

    # dashboards (Grafana) vive tras un profile de compose a proposito
    # (ROADMAP.md mon-07: "apagado por defecto"): sin --profile aqui, "up"
    # no arrancaria nada aunque se pida explicitamente.
    $profiles = if ($Service -eq 'dashboards') { @('dashboards') } else { @() }

    Write-FreyaInfo "levantando $Service"
    Invoke-FreyaCompose -Service $Service -Arguments $arguments -Profiles $profiles
    Write-FreyaOk "$Service levantado"
}

function Stop-FreyaService {
    param(
        [Parameter(Mandatory)][string]$Service,
        [switch]$RemoveVolumes
    )

    $arguments = @('down')
    if ($RemoveVolumes) { $arguments += '--volumes' }
    $profiles = if ($Service -eq 'dashboards') { @('dashboards') } else { @() }

    Write-FreyaInfo "parando $Service"
    Invoke-FreyaCompose -Service $Service -Arguments $arguments -Profiles $profiles
    Write-FreyaOk "$Service parado"
}

function Restart-FreyaService {
    param([Parameter(Mandatory)][string]$Service)
    Stop-FreyaService -Service $Service
    Start-FreyaService -Service $Service
}

function Get-FreyaLog {
    param(
        [Parameter(Mandatory)][string]$Service,
        [int]$Tail = 200,
        [switch]$Follow
    )

    $arguments = @('logs', '--tail', "$Tail")
    if ($Follow) { $arguments += '--follow' }
    Invoke-FreyaCompose -Service $Service -Arguments $arguments
}

function Get-FreyaStatus {
    <#
        Estado de los contenedores de Freya, cruzado con el registro para
        distinguir lo que falta por construir de lo que esta caido.
    #>
    Assert-Docker

    # JSON en vez de --format con comillas incrustadas: PowerShell 5.1
    # destroza las comillas dobles al pasarlas a un ejecutable nativo como
    # docker.exe (p.ej. `{{.Label "freya.service"}}` llega roto).
    $running = @{}
    $raw = docker ps --filter 'label=freya.service' --format '{{json .}}' 2>$null
    foreach ($line in $raw) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        $entry = $line | ConvertFrom-Json
        $name = $entry.Labels -split ',' |
            Where-Object { $_ -like 'freya.service=*' } |
            ForEach-Object { $_ -replace '^freya\.service=', '' } |
            Select-Object -First 1
        if ($name) {
            $running[$name] = [pscustomobject]@{ Status = $entry.Status; Image = $entry.Image }
        }
    }

    $root = Get-FreyaRoot
    $report = foreach ($name in $script:Registry.Keys) {
        $entry = $script:Registry[$name]
        $exists = (Test-Path (Join-Path $root "$name\docker-compose.yml")) -or
                  (Test-Path (Join-Path $root "services\$name\docker-compose.yml"))

        $state = if ($running.ContainsKey($name)) { $running[$name].Status }
                 elseif ($exists)                 { 'parado' }
                 else                             { 'sin crear' }

        [pscustomobject]@{
            Servicio = $name
            Fase     = $entry.Phase
            Puerto   = $entry.Port
            Estado   = $state
        }
    }

    return $report
}

function Start-FreyaPhase {
    <#
        Levanta todos los servicios de una fase, en orden de dependencia.
    #>
    param([Parameter(Mandatory)][int]$Phase)

    $services = @(
        $script:Registry.Keys | Where-Object { $script:Registry[$_].Phase -eq $Phase }
    )

    if ($services.Count -eq 0) {
        throw "La fase $Phase no tiene servicios asociados. Fases validas: 1-10."
    }

    Write-FreyaInfo "fase $Phase : $($services -join ', ')"
    foreach ($service in $services) {
        Start-FreyaService -Service $service
    }
}

function New-FreyaService {
    <#
    .SYNOPSIS
        Crea un servicio desde la plantilla, dentro del toolbox.

    .DESCRIPTION
        El puerto se toma del registro si el servicio es conocido. Para
        servicios fuera del registro hay que indicarlo con -Port.
    #>
    param(
        [Parameter(Mandatory)][string]$Service,
        [int]$Port = 0
    )

    if ($Port -eq 0) {
        if (-not $script:Registry.Contains($Service)) {
            throw "Servicio '$Service' no esta en el registro. Indica el puerto con -Port."
        }
        $Port = $script:Registry[$Service].Port
    }

    $destination = Join-Path (Get-FreyaRoot) $Service
    if (Test-Path $destination) {
        throw "Ya existe $Service"
    }

    Write-FreyaInfo "creando $Service en el puerto $Port"
    Invoke-Toolbox -Arguments @('bash', 'infra/scripts/new_service.sh', $Service, "$Port")

    New-FreyaCertificates
    New-FreyaSecret -Service $Service -Name 'api_secret'

    Write-FreyaOk "$Service listo. Levantalo con: .\freya.ps1 up $Service"
}

function Invoke-FreyaTest {
    <#
    .SYNOPSIS
        Ejecuta los tests de un servicio dentro de su propio contenedor.

    .DESCRIPTION
        Construye la etapa `dev` del Dockerfile del servicio, que anade pytest
        sobre la imagen de runtime, y la ejecuta. Nada se instala en el host.
    #>
    param(
        [Parameter(Mandatory)][string]$Service,
        [switch]$Lint
    )

    $root = Get-FreyaRoot
    $dockerfile = Join-Path $root "$Service\Dockerfile"
    if (-not (Test-Path $dockerfile)) {
        $dockerfile = Join-Path $root "services\$Service\Dockerfile"
    }
    if (-not (Test-Path $dockerfile)) {
        throw "No existe $Service\Dockerfile ni services\$Service\Dockerfile. Crea el servicio primero."
    }

    $image = "freya/${Service}:test"

    Write-FreyaInfo "construyendo la imagen de test de $Service"
    Push-Location $root
    try {
        docker build --quiet --target dev --tag $image --file $dockerfile . | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Fallo la construccion de la imagen de test" }

        if ($Lint) {
            $command = @('ruff', 'check', '/srv/app')
            Write-FreyaInfo "lint de $Service"
        }
        else {
            $command = @('pytest', '-q', '/srv/tests')
            Write-FreyaInfo "tests de $Service"
        }

        # Out-Host, no pipeline: la salida de docker no debe contaminar el
        # valor de retorno de la funcion, que es el codigo de salida.
        docker run --rm --network none $image @command | Out-Host
        $code = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }

    if ($code -ne 0) {
        Write-FreyaError "$Service : fallaron"
        return $code
    }

    Write-FreyaOk "$Service : pasaron"
    return 0
}

function New-FreyaServiceAccount {
    <#
    .SYNOPSIS
        Da de alta (o corrige los permisos de) una cuenta de servicio en
        auth, generando su api_secret.

    .DESCRIPTION
        Para identidades operativas que sólo actúan como CLIENTE de la
        malla y nunca sirven HTTP (p.ej. freya-ops, que sube backups a
        storage) -- los 14 servicios del registro se aprovisionan al
        crearse (ver New-FreyaService), esto es aparte.

        POST /admin/service-accounts exige FREYA_AUTH_ENABLED=false (modo
        bootstrap) o un JWT de rol admin. Lo segundo no existe todavía como
        cuenta persistente, y lo primero se probó en vivo y resultó ser una
        puerta rota: gestor-db invalidó su token de bootstrap para siempre
        al cerrar la Fase 2, así que poner auth en modo bootstrap le impide
        escribir en gestor-db para CUALQUIER cosa mientras dura -- no sólo
        /admin/*, así que un backup real habría dejado login/service-auth
        caídos durante la ventana.

        En su lugar, infra/scripts/provision_via_auth_keys.py corre DENTRO
        del contenedor de auth (docker exec): usa el mismo SelfTokenProvider
        que auth ya usa en producción para hablar consigo mismo, firma su
        propio JWT con su propio keyring, y llama al dominio en proceso.
        Cero modo bootstrap, cero HTTP de más, auth nunca deja de responder
        con normalidad.

    .EXAMPLE
        New-FreyaServiceAccount -Service freya-ops -Permissions @('read:storage','write:storage')
    #>
    param(
        [Parameter(Mandatory)][string]$Service,
        [Parameter(Mandatory)][string[]]$Permissions
    )

    if (-not (docker ps -q --filter 'name=^/freya-auth$')) {
        throw 'freya-auth no esta corriendo. Levantalo con: .\freya.ps1 up auth'
    }

    New-FreyaSecret -Service $Service -Name 'api_secret'
    $secretPath = Join-Path (Get-FreyaRoot) "infra\secrets\$Service\api_secret"
    $apiSecret = (Get-Content $secretPath -Raw).Trim()
    $scriptPath = Join-Path (Get-FreyaRoot) 'infra\scripts\provision_via_auth_keys.py'

    Write-FreyaInfo "dando de alta '$Service' con las claves propias de auth"
    $output = Get-Content $scriptPath -Raw | docker exec -i `
        -e "SERVICE_NAME=$Service" `
        -e "API_SECRET=$apiSecret" `
        -e "PERMISSIONS_CSV=$($Permissions -join ',')" `
        freya-auth python3 -
    $output | Write-Host
    if ($LASTEXITCODE -ne 0 -or ($output -join "`n") -match 'Traceback') {
        throw "fallo aprovisionando '$Service' (ver salida arriba)"
    }
    Write-FreyaOk "cuenta de servicio '$Service' lista"
}

function Assert-FreyaOpsAccount {
    <#
        Da de alta la cuenta 'freya-ops' la primera vez que hace falta
        (Backup-FreyaDatabase, Restore-FreyaDatabaseCheck, New-FreyaInternalCA,
        Update-FreyaCertificate): identidad operativa que actua en nombre
        de freya.ps1 -- sube/baja blobs de infraestructura a storage, y
        pide certificados a la CA interna de secrets -- nunca de un
        servicio. Si el secreto ya existe, se asume que la cuenta también
        -- no repite el ciclo de alta en cada backup, sólo actualiza
        permisos por si una versión anterior la creó con menos.
    #>
    $secretPath = Join-Path (Get-FreyaRoot) 'infra\secrets\freya-ops\api_secret'
    if (Test-Path $secretPath) { return }

    Write-FreyaInfo "'freya-ops' no existe todavia, se aprovisiona"
    New-FreyaServiceAccount -Service 'freya-ops' -Permissions @(
        'read:storage', 'write:storage', 'read:secrets', 'write:secrets', 'write:certs'
    )
}

function New-FreyaInternalCA {
    <#
    .SYNOPSIS
        Importa infra\certs\ca\ al vault de secrets, una sola vez
        (docs/ROADMAP.md Fase 3, punto 4). A partir de aquí, renovar un
        certificado pasa por Update-FreyaCertificate, no por volver a
        correr gen_dev_ca.sh.

    .DESCRIPTION
        Idempotente: si la CA ya se importó, no la sustituye (ver
        infra/scripts/import_ca.py). No borra infra\certs\ca\ca.key --
        eso es un paso aparte y deliberado (ver el aviso al final), para
        no dejar la malla sin arranque en frío si algo sale mal a mitad.
    #>
    Assert-FreyaOpsAccount
    $secretMount = ConvertTo-DockerPath (Join-Path (Get-FreyaRoot) 'infra\secrets\freya-ops')

    Write-FreyaInfo 'importando la CA de desarrollo al vault de secrets'
    Invoke-Toolbox -Network 'freya-mesh' `
        -ExtraDockerArgs @('--volume', "${secretMount}:/run/secrets:ro") `
        -Arguments @('python3', 'infra/scripts/import_ca.py')

    Write-FreyaOk 'CA importada'
    Write-FreyaWarn 'infra\certs\ca\ca.key sigue en disco a proposito -- borralo a mano cuando confirmes que Update-FreyaCertificate funciona (ver secrets\README.md)'
}

function Update-FreyaCertificate {
    <#
    .SYNOPSIS
        Renueva el certificado de un servicio pidiendoselo a la CA interna
        de secrets, en vez de volver a correr gen_dev_ca.sh.

    .EXAMPLE
        Update-FreyaCertificate -Service storage
    #>
    param([Parameter(Mandatory)][string]$Service)

    Assert-FreyaOpsAccount
    $secretMount = ConvertTo-DockerPath (Join-Path (Get-FreyaRoot) 'infra\secrets\freya-ops')
    $certDir = Join-Path (Get-FreyaRoot) "infra\certs\$Service"
    New-Item -ItemType Directory -Force -Path $certDir | Out-Null
    $certMount = ConvertTo-DockerPath $certDir

    Write-FreyaInfo "pidiendo un certificado nuevo para '$Service' a la CA interna"
    Invoke-Toolbox -Network 'freya-mesh' `
        -ExtraDockerArgs @(
            '--volume', "${secretMount}:/run/secrets:ro",
            '--volume', "${certMount}:/out"
        ) `
        -Arguments @('python3', 'infra/scripts/renew_cert.py', $Service)

    Invoke-Toolbox -Arguments @(
        'bash', '-c',
        "chown 10001:10001 infra/certs/$Service/tls.key && chmod 600 infra/certs/$Service/tls.key"
    )
    Write-FreyaOk "certificado de '$Service' renovado -- reinicia el servicio para que lo recoja: .\freya.ps1 restart $Service"
}

function Import-FreyaBootstrapSecrets {
    <#
    .SYNOPSIS
        Echa una copia de cada credencial de arranque (infra\secrets\*) al
        vault de secrets, para que quede administrada desde ahi (auditoria,
        futura rotacion) -- ver infra/scripts/import_bootstrap_secrets.py
        para el porque el fichero en disco no desaparece.

    .DESCRIPTION
        Idempotente (overwrite: false): correrlo de nuevo no sustituye lo
        que ya se importo. master_key de secrets NUNCA se importa -- es la
        clave que cifra todo lo demas en el vault.
    #>
    Assert-FreyaOpsAccount
    $secretMount = ConvertTo-DockerPath (Join-Path (Get-FreyaRoot) 'infra\secrets\freya-ops')
    $bootstrapMount = ConvertTo-DockerPath (Join-Path (Get-FreyaRoot) 'infra\secrets')

    Write-FreyaInfo 'importando credenciales de arranque al vault de secrets'
    Invoke-Toolbox -Network 'freya-mesh' `
        -ExtraDockerArgs @(
            '--volume', "${secretMount}:/run/secrets:ro",
            '--volume', "${bootstrapMount}:/bootstrap:ro"
        ) `
        -Arguments @('python3', 'infra/scripts/import_bootstrap_secrets.py')

    Write-FreyaOk 'credenciales de arranque importadas'
}

function Update-FreyaSigningKey {
    <#
    .SYNOPSIS
        Rota la clave de firma JWT de un servicio generando una nueva y
        subiendola a secrets (sec-05 extendido) -- nunca toca el fichero
        de arranque en infra\secrets\<servicio>\signing_keys\, que sigue
        siendo la primera clave imprescindible (ver
        docs/ARCHITECTURE.md §2.1).

    .DESCRIPTION
        Sólo 'auth' hoy: es el único servicio que firma JWT. El servicio
        tiene que reiniciarse para recoger la clave nueva de secrets --
        esto no reinicia nada por si se quiere coordinar la ventana.

    .EXAMPLE
        Update-FreyaSigningKey -Service auth
        .\freya.ps1 restart auth
    #>
    param([Parameter(Mandatory)][string]$Service)

    if ($Service -ne 'auth') {
        throw "Rotacion de clave de firma solo soportada para 'auth' por ahora."
    }

    Assert-FreyaOpsAccount
    $secretMount = ConvertTo-DockerPath (Join-Path (Get-FreyaRoot) 'infra\secrets\freya-ops')

    Write-FreyaInfo "rotando la clave de firma de '$Service'"
    Invoke-Toolbox -Network 'freya-mesh' `
        -ExtraDockerArgs @('--volume', "${secretMount}:/run/secrets:ro") `
        -Arguments @('bash', 'infra/scripts/rotate_signing_key.sh')

    Write-FreyaOk "clave nueva en secrets -- reinicia '$Service' para que la recoja"
}

function Backup-FreyaDatabase {
    <#
    .SYNOPSIS
        Vuelca la base con pg_dump -Fc y lo sube al bucket 'backups' de
        storage (ROADMAP.md Fase 11 adelantada). Devuelve la clave de
        storage, no una ruta local: nada del volcado sobrevive en el host.

    .DESCRIPTION
        pg_dump corre dentro del propio contenedor y escribe a un directorio
        del volumen persistente (no a /tmp: es tmpfs, y "docker cp" no ve de
        forma fiable ficheros de un tmpfs con el backend WSL2 de Docker
        Desktop). docker cp lo saca al host en binario, sin pasar el volcado
        por la tubería de texto de PowerShell (que lo corrompería) -- pero
        sólo de paso: infra\backups\<servicio> es una escala efímera hacia
        storage, se borra en cuanto la subida termina.
    #>
    param([Parameter(Mandatory)][string]$Service)

    $container = "freya-$Service"
    if (-not (docker ps -q --filter "name=^/${container}$")) {
        throw "$container no esta corriendo. Levantalo con: .\freya.ps1 up $Service"
    }

    Assert-FreyaOpsAccount

    # docker exec con argumentos separados, sin "sh -c": evita anidar comillas
    # de shell dentro de comillas de PowerShell, que es fragil y dificil de leer.
    $pgUser = (docker exec $container printenv POSTGRES_USER | Out-String).Trim()
    $pgDb = (docker exec $container printenv POSTGRES_DB | Out-String).Trim()

    $stagingDir = Join-Path (Get-FreyaRoot) "infra\backups\$Service"
    New-Item -ItemType Directory -Force -Path $stagingDir | Out-Null

    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $fileName = "freya-$stamp.dump"
    $workDir = '/var/lib/postgresql/data/freya_backup_tmp'
    $containerPath = "$workDir/$fileName"
    $stagingFile = Join-Path $stagingDir $fileName

    Write-FreyaInfo "generando volcado de $Service"
    docker exec $container mkdir -p $workDir
    docker exec $container pg_dump -U $pgUser -Fc -f $containerPath $pgDb
    if ($LASTEXITCODE -ne 0) { throw 'pg_dump fallo' }

    docker cp "${container}:${containerPath}" $stagingFile
    if ($LASTEXITCODE -ne 0) { throw 'no se pudo copiar el volcado fuera del contenedor' }
    docker exec $container rm -f $containerPath | Out-Null

    $key = "$Service/$fileName"
    $secretMount = ConvertTo-DockerPath (Join-Path (Get-FreyaRoot) 'infra\secrets\freya-ops')
    $stagingMount = ConvertTo-DockerPath $stagingDir

    Write-FreyaInfo "subiendo volcado a storage ($key)"
    try {
        Invoke-Toolbox -Network 'freya-mesh' `
            -ExtraDockerArgs @(
                '--volume', "${secretMount}:/run/secrets:ro",
                '--volume', "${stagingMount}:/staging:ro"
            ) `
            -Arguments @('python3', 'infra/scripts/backup_upload.py', "/staging/$fileName", $key)
    }
    finally {
        Remove-Item $stagingFile -ErrorAction SilentlyContinue
    }

    Write-FreyaOk "backup en storage: $key"
    return $key
}

function Restore-FreyaDatabaseCheck {
    <#
    .SYNOPSIS
        Baja un volcado de storage, lo restaura en una base temporal para
        verificar que es recuperable, y la borra. Nunca toca los datos
        reales.

    .DESCRIPTION
        -Key es la clave que devolvió Backup-FreyaDatabase (p.ej.
        "database/freya-20260821-120000.dump"), no una ruta local: el
        volcado ya no vive en el host entre backup y restore-check, sólo
        durante la ventana de esta verificación.
    #>
    param(
        [Parameter(Mandatory)][string]$Service,
        [Parameter(Mandatory)][string]$Key
    )

    $container = "freya-$Service"
    Assert-FreyaOpsAccount

    $stagingDir = Join-Path (Get-FreyaRoot) "infra\backups\$Service"
    New-Item -ItemType Directory -Force -Path $stagingDir | Out-Null
    $fileName = Split-Path -Leaf $Key
    $stagingFile = Join-Path $stagingDir $fileName

    $secretMount = ConvertTo-DockerPath (Join-Path (Get-FreyaRoot) 'infra\secrets\freya-ops')
    $stagingMount = ConvertTo-DockerPath $stagingDir

    Write-FreyaInfo "descargando $Key desde storage"
    Invoke-Toolbox -Network 'freya-mesh' `
        -ExtraDockerArgs @(
            '--volume', "${secretMount}:/run/secrets:ro",
            '--volume', "${stagingMount}:/staging"
        ) `
        -Arguments @('python3', 'infra/scripts/backup_download.py', $Key, "/staging/$fileName")

    try {
        $pgUser = (docker exec $container printenv POSTGRES_USER | Out-String).Trim()

        $verifyDb = 'freya_restore_check'
        $workDir = '/var/lib/postgresql/data/freya_backup_tmp'
        $containerPath = "$workDir/$fileName"

        Write-FreyaInfo "verificando restauracion en la base temporal '$verifyDb'"
        docker exec $container mkdir -p $workDir
        docker cp $stagingFile "${container}:${containerPath}"
        if ($LASTEXITCODE -ne 0) { throw 'no se pudo copiar el volcado al contenedor' }

        docker exec $container dropdb -U $pgUser --if-exists $verifyDb
        docker exec $container createdb -U $pgUser $verifyDb
        if ($LASTEXITCODE -ne 0) {
            docker exec $container rm -f $containerPath | Out-Null
            throw 'no se pudo crear la base temporal de verificacion'
        }

        docker exec $container pg_restore -U $pgUser -d $verifyDb --exit-on-error $containerPath
        $restoreCode = $LASTEXITCODE

        # pg_tables + current_schema(): confirma que la base restaurada responde
        # y tiene contenido.
        $sql = 'select count(*) from pg_tables where schemaname = current_schema()'
        $tableCount = (docker exec $container psql -U $pgUser -d $verifyDb -tAc $sql | Out-String).Trim()

        docker exec $container dropdb -U $pgUser --if-exists $verifyDb | Out-Null
        docker exec $container rm -f $containerPath | Out-Null

        if ($restoreCode -ne 0) {
            throw "la restauracion de verificacion fallo (codigo $restoreCode)"
        }

        Write-FreyaOk "restauracion verificada: $tableCount tabla(s) recuperadas en '$verifyDb', luego borrada"
    }
    finally {
        Remove-Item $stagingFile -ErrorAction SilentlyContinue
    }
}

function Invoke-FreyaDoctor {
    <#
        Diagnostico del entorno. Lo primero que ejecutar cuando algo no arranca.
    #>
    Write-FreyaInfo 'diagnostico del entorno'
    $problems = @()

    try {
        Assert-Docker
        $version = docker info --format '{{.ServerVersion}}' 2>$null
        Write-FreyaOk "Docker responde (servidor $version)"
    }
    catch {
        Write-FreyaError $_.Exception.Message
        return 1
    }

    # Docker Desktop en Windows tiene que estar en contenedores Linux.
    $osType = docker info --format '{{.OSType}}' 2>$null
    if ($osType -ne 'linux') {
        $problems += "Docker esta en modo '$osType'. Cambia a contenedores Linux."
        Write-FreyaError "modo de contenedor: $osType (se necesita linux)"
    }
    else {
        Write-FreyaOk 'modo de contenedor: linux'
    }

    foreach ($name in @('freya-mesh', 'freya-db', 'freya-mon', 'freya-edge')) {
        if (Test-DockerNetwork -Name $name) {
            Write-FreyaOk "red $name presente"
        }
        else {
            $problems += "Falta la red $name. Ejecuta: .\freya.ps1 init"
            Write-FreyaError "red $name ausente"
        }
    }

    $root = Get-FreyaRoot
    if (Test-Path (Join-Path $root 'infra\certs\ca\ca.crt')) {
        Write-FreyaOk 'CA de desarrollo presente'
    }
    else {
        $problems += 'Faltan los certificados. Ejecuta: .\freya.ps1 init'
        Write-FreyaError 'CA de desarrollo ausente'
    }

    # CRLF en un .sh rompe el interprete dentro del contenedor Linux.
    $shellScript = Join-Path $root 'infra\scripts\gen_dev_ca.sh'
    if (Test-Path $shellScript) {
        $bytes = [System.IO.File]::ReadAllBytes($shellScript)
        if ($bytes -contains 13) {
            $problems += 'Los .sh tienen finales de linea CRLF. Ejecuta: .\freya.ps1 fix-eol'
            Write-FreyaError 'scripts .sh con CRLF (bash fallara dentro del contenedor)'
        }
        else {
            Write-FreyaOk 'scripts .sh con finales de linea LF'
        }
    }

    if ($problems.Count -eq 0) {
        Write-FreyaOk 'entorno correcto'
        return 0
    }

    Write-Host ''
    Write-FreyaWarn "$($problems.Count) problema(s) encontrado(s):"
    foreach ($problem in $problems) { Write-Host "  - $problem" }
    return 1
}

function Repair-FreyaLineEnding {
    <#
        Convierte a LF los ficheros que se montan en contenedores Linux.
        Necesario si se clono el repositorio sin .gitattributes.
    #>
    $root = Get-FreyaRoot
    $patterns = @('*.sh', '*.py', '*.yaml', '*.yml', '*.toml', 'Dockerfile')
    $fixed = 0

    foreach ($pattern in $patterns) {
        $files = Get-ChildItem -Path $root -Filter $pattern -Recurse -File -ErrorAction SilentlyContinue |
                 Where-Object { $_.FullName -notmatch '\\(\.git|infra\\certs|infra\\secrets)\\' }

        foreach ($file in $files) {
            $content = [System.IO.File]::ReadAllText($file.FullName)
            if ($content -notmatch "`r`n") { continue }
            $normalized = $content -replace "`r`n", "`n"
            [System.IO.File]::WriteAllText(
                $file.FullName, $normalized, (New-Object System.Text.UTF8Encoding $false)
            )
            $fixed++
        }
    }

    Write-FreyaOk "$fixed fichero(s) convertido(s) a LF"
}

Export-ModuleMember -Function @(
    'Get-FreyaRegistry', 'Get-FreyaServicePort', 'Get-FreyaComposeFile',
    'Start-FreyaService', 'Stop-FreyaService', 'Restart-FreyaService',
    'Get-FreyaLog', 'Get-FreyaStatus', 'Start-FreyaPhase',
    'New-FreyaService', 'Invoke-FreyaTest', 'Invoke-FreyaDoctor',
    'Repair-FreyaLineEnding', 'Backup-FreyaDatabase', 'Restore-FreyaDatabaseCheck',
    'Assert-FreyaOpsAccount', 'New-FreyaServiceAccount', 'New-FreyaInternalCA',
    'Update-FreyaCertificate', 'Import-FreyaBootstrapSecrets', 'Update-FreyaSigningKey'
)

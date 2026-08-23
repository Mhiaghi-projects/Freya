# Freya — Arquitectura

## 1. Principio rector

Freya es una plataforma de servicios **autoalojada y autoconsumida**: cada servicio
de Freya se apoya en los demás servicios de Freya. No hay dependencias externas
para identidad, secretos, almacenamiento o versionado.

Freya es además **multi-tenant desde el diseño**: todo servicio distingue entre
el tenant `freya` (uso interno de la plataforma) y tenants externos (otros
proyectos y usuarios). Lo que Freya consume de sí misma vive en un espacio
reservado, separado del de terceros.

## 2. Reglas duras

1. **Todo corre en contenedores.** El host (Windows) sólo tiene Docker Desktop y
   `freya.ps1`, que se limita a hablar con Docker. Ni Python, ni openssl, ni WSL.
   Las tareas que necesitan herramientas Unix corren en el contenedor `toolbox`.
2. **Comunicación entre servicios: HTTPS.** Sin excepción. Certificados emitidos
   por la CA interna de Freya.
3. **Un "gestor" puede hablar con sus contenedores por el protocolo nativo.**
   `gestor-db` habla PostgreSQL con `database`; `gestor-monitoring` habla PromQL
   con su backend de métricas. Ese tráfico vive en una red privada que ningún
   otro servicio puede alcanzar.
4. **Recursos escasos.** Se prefiere open source ligero. Si no hay opción ligera,
   se desarrolla propio.
5. **Un servicio = un contenedor = un proyecto** en el backlog, con su nivel de
   dificultad y sus tasks.
6. **Nada toca el socket de Docker salvo `freya.ps1` — con dos
   excepciones, ambas decididas en vivo con el usuario, no asumidas.**
   `gestor-monitoring` lo monta de **sólo lectura** para descubrir
   contenedores por la etiqueta `freya.service` (Fase 7, ROADMAP.md
   mon-02): sin eso, "sin reinicio al añadir un servicio" sólo podría
   lograrse con una lista estática que dependiera de que todo cambio
   pasara por `freya.ps1` — no sería descubrimiento real. `cicd` lo monta
   en **escritura** (Fase 8, ROADMAP.md ci-03): construye y corre la
   imagen de test de un servicio conocido para ejecutar de verdad su
   lint/pytest, por un único camino fijo que nunca acepta un Dockerfile,
   imagen o comando definido por quien llama — nunca un runner de
   pipelines arbitrarios. Es la concesión más amplia de las dos: el
   socket en escritura equivale a control total del daemon de Docker del
   host. En ambos casos se acota todo lo demás que se pueda (`group_add:
   ["0"]` en vez de correr como root — el socket es `660 root:root` en
   Docker Desktop —, `cap_drop: ALL`, sin más salida de red que la
   estrictamente necesaria). Ver `gestor-monitoring/README.md` y
   `cicd/README.md`.

## 2.1 Todo lo que no sea código vive en `storage`; todo lo que sea
    secreto o certificado, gestionado por `secrets`

`storage` es el NAS de Freya: sus bytes viven en `D:\share` del host
(bind mount, no un volumen Docker con nombre), en una carpeta real por
`tenant/bucket/key` — navegable en el Explorador, no un espacio de hashes
opacos (`storage/app/domain/blob_store.py`). Backups de
`database`, packfiles de `git`, y cualquier blob de infraestructura
futuro van ahí, nunca al filesystem de un servicio ni al host suelto.

`secrets` es quien gestiona certificados desde la Fase 3: mantiene la
clave privada de la CA interna cifrada en su propio vault (misma envelope
encryption que cualquier secreto) y emite certificados nuevos via
`POST /certs/{service}/issue` — ver `secrets/README.md`. Sigue
habiendo un mínimo irreducible en disco (`infra/certs/ca/ca.crt`, la CA
raíz PÚBLICA, y el primer certificado de cada servicio): ningún
contenedor, `secrets` incluido, puede hablar HTTPS con nadie antes de
tener uno, así que el primer certificado no puede depender de una llamada
HTTPS a `secrets`. Ese mínimo es un `.crt`/`.key` por servicio, nunca la
clave privada de la CA misma.

## 3. Mapa de servicios

| Servicio | Tipo | Puerto | Expuesto al host | Depende de |
|---|---|---|---|---|
| `frontend` | propio | 8000 | Sí (443 público) | todos |
| `gestor-db` | propio | 8001 | No | `database` |
| `auth` | propio | 8002 | No | `gestor-db` |
| `secrets` | propio | 8003 | No | `gestor-db`, `auth` |
| `storage` | propio | 8004 | No | `auth`, `gestor-db` |
| `git` | propio | 8005 | No | `storage`, `auth`, `gestor-db` |
| `project-manager` | propio | 8006 | No | `gestor-db`, `auth` |
| `cicd` | propio | 8007 | No | `git`, `storage`, `secrets`, `auth` |
| `gestor-monitoring` | propio | 8008 | No | backends de monitoring |
| `gamification` | propio | 8009 | No | `project-manager`, `gestor-db`, `auth` |
| `database` | PostgreSQL 16-alpine | 5432 | No | — |
| `metrics` | VictoriaMetrics single | 8428 | No | — |
| `logs` | VictoriaLogs | 9428 | No | — |
| `dashboards` | Grafana (perfil opcional) | 3000 | No | `metrics`, `logs` |

### Contenedores agrupados bajo un gestor

```
gestor-db  ──(red freya-db)──▶  database (PostgreSQL)

gestor-monitoring ──(red freya-mon)──▶ metrics   (VictoriaMetrics)
                                     ├▶ logs     (VictoriaLogs)
                                     └▶ dashboards (Grafana, opcional)
```

Ningún servicio que no sea el gestor tiene ruta de red hacia esos backends.
Para leer métricas o consultar la base, se pasa por la API HTTPS del gestor.

## 4. Redes Docker

| Red | Miembros | `--internal` | Propósito |
|---|---|---|---|
| `freya-mesh` | todos los servicios propios | no | tráfico HTTPS servicio-a-servicio |
| `freya-db` | `gestor-db`, `database` | **sí** | protocolo PostgreSQL |
| `freya-mon` | `gestor-monitoring`, `metrics`, `logs`, `dashboards` | **sí** | scrape y consultas |
| `freya-edge` | `frontend` únicamente | no | única puerta al exterior |

`database`, `metrics`, `logs` y `dashboards` **no** están en `freya-mesh`.
Sólo `frontend` está en `freya-edge`.

`freya-mesh` no es `--internal` a propósito: `git` necesita alcanzar GitHub para
la sincronización, y `cicd` los registros de paquetes. Eso concede salida a todos
los servicios de la malla, que es más de lo estrictamente necesario. Queda
apuntado como tarea de endurecimiento en la Fase 11: separar una red de egreso
para los dos servicios que la necesitan y dejar el resto sin salida.

Las redes se crean con `.\freya.ps1 init`, nunca a mano.

## 5. Elección de tecnología y por qué

| Necesidad | Descartado | Elegido | Motivo |
|---|---|---|---|
| Object storage | MinIO (~250 MB RAM, cambio de licencia) | **propio** sobre filesystem, API S3-compatible parcial | huella mínima, control total |
| Gestión de secretos | HashiCorp Vault (~200 MB RAM, operativa pesada) | **propio**: AES-256-GCM + envelope encryption | suficiente para el alcance, arranca en MB |
| Git server | Gitea (~150 MB), GitLab (descartado de plano) | **propio**: FastAPI sobre `git http-backend` | necesitamos política de "5 commits locales, resto a GitHub" |
| Métricas | Prometheus (~200 MB con retención) | **VictoriaMetrics single** (~40 MB) | 5-10x menos RAM, compatible PromQL |
| Logs | Loki + Promtail (~250 MB) | **VictoriaLogs** (~30 MB) | mismo ecosistema, huella mínima |
| Dashboards | Grafana siempre encendido | **Grafana bajo perfil opcional** + vistas propias en `frontend` | se enciende sólo cuando se necesita |
| CI/CD | Jenkins, GitLab CI, Zuul | **propio**: runner que lanza contenedores efímeros | control del scheduler y del consumo |
| Gestión de proyectos | Jira, OpenProject (~1 GB) | **propio** | integración directa con `gamification` |
| Base de datos | — | **PostgreSQL 16-alpine** | único componente pesado justificado |

## 6. El ciclo `auth` ↔ `gestor-db`

`auth` necesita `gestor-db` para guardar usuarios. `gestor-db` necesita `auth`
para validar quién lo llama. Se rompe con un **modo bootstrap**:

1. `gestor-db` arranca con `FREYA_BOOTSTRAP_TOKEN` (un token estático leído de
   un fichero montado). Mientras `AUTH_ENABLED=false`, sólo acepta ese token.
2. `auth` arranca, usa el token de bootstrap contra `gestor-db`, crea su schema
   y las cuentas de servicio.
3. `auth` emite una service account para `gestor-db` y su clave de firma pública.
4. `gestor-db` se reinicia con `AUTH_ENABLED=true` y valida JWT contra `auth`.
   El token de bootstrap queda inválido y se registra un evento de auditoría.

El mismo patrón aplica a `secrets`: arranca con una master key en fichero, y una
vez `secrets` está sano, los demás servicios dejan de leer `.env` y piden sus
credenciales a `secrets`.

## 7. Autenticación servicio-a-servicio

- Cada servicio tiene una **service account** en `auth` con `client_id` y
  `client_secret` (guardado en `secrets`).
- Flujo: `client_credentials` → JWT de vida corta (5 min) firmado con EdDSA.
- El llamante manda `Authorization: Bearer <jwt>`.
- El receptor valida la firma contra el JWKS público de `auth`, cacheado 10 min.
  **No** hace una llamada a `auth` por cada petición.
- Las claims incluyen `sub` (servicio o usuario), `tenant`, `scopes` y `act`
  (actor, cuando un servicio actúa en nombre de un usuario).

## 8. Superficie externa

Todo lo que entra desde fuera pasa por `frontend`:

```
Internet ─▶ frontend (443) ─▶ HTTPS mesh ─▶ servicio destino
```

`frontend` cumple dos funciones: la UI web y un **gateway HTTP** para que
proyectos externos consuman los servicios de Freya sin exponerlos directamente.

## 9. Separación Freya / terceros

- **Base de datos**: `database` aloja un schema por servicio y por tenant.
  Freya usa `freya_auth`, `freya_storage`, …; un tenant externo `acme` usa
  `acme_auth`, `acme_storage`, …
- **Storage**: `/{tenant}/{bucket}/…`. Freya vive bajo `/freya/{servicio}/`.
- **Auth**: los tenants están aislados; un token de un tenant no sirve en otro.
- **Monitoring**: los targets de terceros van a un espacio de nombres aparte y
  no aparecen en los dashboards internos de Freya.

# athenea

Prueba de concepto: una app tipo Notion construida como tenant externo sobre
Freya (docs/ARCHITECTURE.md §9), no un servicio interno de la plataforma.

- **Auth**: usuarios del tenant `athenea`, autenticados por `auth` como
  cualquier otro usuario de Freya -- `app/deps.py` sólo exige un JWT de
  usuario válido, ninguna página tiene permisos por role.
- **Datos**: páginas y bloques viven en `gestor-db`, bajo el schema
  `athenea` (separado del de `freya`).
- **Objetos**: los adjuntos de una página se suben directo a storage por el
  cliente, a través del gateway `/api/storage` de `frontend` -- este
  servicio nunca habla con storage (sin `FREYA_STORAGE_URL` en
  `docker-compose.yml`, a propósito). Sólo guarda el `bucket`/`object_key`
  que el cliente le manda después de subir el objeto.

## Endpoints

`Authorization: Bearer <jwt de usuario>`.

| Ruta | Método | Qué hace |
|---|---|---|
| `/api/v1/pages` | POST / GET | Crear / listar las páginas propias. |
| `/api/v1/pages/{id}` | GET / DELETE | |
| `/api/v1/pages/{id}/blocks` | POST / GET | Bloques de una página (`text`, `heading`, `todo`). |
| `/api/v1/pages/{id}/attachments` | POST / GET | Metadato de un adjunto ya subido a storage. |

## Estructura

```
app/
├── main.py       lifespan: gestor_db + MigrationRunner (tenant "athenea")
├── config.py     default_tenant = "athenea"
├── deps.py       UserDep: JWT de usuario, sin permisos por servicio
├── api/pages.py  páginas, bloques, adjuntos
└── domain/       pages.py, blocks.py, attachments.py
```

## Tests

```powershell
.\freya.ps1 test athenea
.\freya.ps1 lint athenea
```

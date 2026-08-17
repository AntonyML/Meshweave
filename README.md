# ⬡ Meshweave

Centro de control local para Windows: túnel Cloudflare, backend FastAPI,
sincronización Docker → Supabase Cloud, backups del dump y alertas por email.

> Reestructuración del prototipo *TunnelCloudFlare* (ya eliminado): paquete
> Python ordenado, datos fuera del código, secretos cifrados con DPAPI y
> camino hacia un instalador distribuible.

## Arquitectura

```
Docker (Supabase self-hosted)   ←── fuente de verdad (escribe la app)
        │  sync incremental 01:00 (MeshweaveSyncService)
        ▼
Supabase Cloud (pooler, free tier)  ←── backup conservador (nunca se borra)
        │  backup del dump 01:30 (MeshweaveBackupService)
        ▼
backups/cloud-YYYYMMDD.dump (retención 7 días)
        │  si algo falla / todo OK
        ▼
Email (Resend): alerta de fallo o resumen diario
```

| Hora | Tarea | Qué hace |
|---|---|---|
| 01:00 | `MeshweaveSyncService` | Sync incremental Docker → nube (lotes 200, delay/backoff, nunca borra) |
| 01:30 | `MeshweaveBackupService` | `pg_dump` completo de la nube vía contenedor `supabase-db` → `backups/` |

## Estructura del repositorio

```
src/meshweave/
├── app.py                # ventana principal + modo headless
├── paths.py              # %ProgramData%\Meshweave / %LOCALAPPDATA%\Meshweave
├── config.py             # config pública (atómica), sin secretos
├── secrets.py            # almacén DPAPI (nunca JSON en claro)
├── logging_setup.py      # log rotativo + redacción de credenciales
├── process_runner.py     # procesos controlados (PID, timeouts, huérfanos)
├── windows_tasks.py      # Task Scheduler (CLI y GUI comparten la misma lógica)
├── services/             # tunnel, backend, cloudflared_manager, sync, updater
├── sync/                 # engine (watermark), alerts (Resend), backup
├── ui/                   # vistas (Panel, Túnel, Backend, Sync, Backups, …)
└── workers/sync_worker.py# CLI: run/check/status/install/backup/alertas
```

## Dónde viven los datos (fuera del código)

| Qué | Ruta |
|---|---|
| Config pública | `%ProgramData%\Meshweave\config\config.json` |
| Secretos (DPAPI) | `%ProgramData%\Meshweave\secrets.bin` |
| Logs | `%ProgramData%\Meshweave\logs\` |
| Estado/watermarks | `%ProgramData%\Meshweave\state\` |
| Backups | `%ProgramData%\Meshweave\backups\` |
| Binario cloudflared | `%ProgramData%\Meshweave\bin\cloudflared.exe` |
| Runtime (config túnel) | `%ProgramData%\Meshweave\runtime\` |
| Cache/descargas/updates | `%LOCALAPPDATA%\Meshweave\` |

Nada de esto se escribe en la carpeta de instalación ni en el repo.

## Desarrollo

```bat
scripts\run_dev.bat                  :: crea .venv, pip install -e ., abre la GUI
.venv\Scripts\python -m meshweave    :: GUI
.venv\Scripts\python -m meshweave.workers.sync_worker check   :: CLI
```

Los `.bat` son **solo para desarrollo**; el producto final se lanza con
`Meshweave.exe` (sin consola).

## CLI de referencia

```
python -m meshweave.workers.sync_worker check           # conexiones local + nube
python -m meshweave.workers.sync_worker run             # sync incremental ahora
python -m meshweave.workers.sync_worker run --dry-run   # solo lee, no escribe
python -m meshweave.workers.sync_worker status          # último run + tareas + watermarks
python -m meshweave.workers.sync_worker install         # tarea 01:00 (MeshweaveSyncService)
python -m meshweave.workers.sync_worker uninstall
python -m meshweave.workers.sync_worker backup          # backup del dump ahora
python -m meshweave.workers.sync_worker backup-install  # tarea 01:30
python -m meshweave.workers.sync_worker backup-uninstall
python -m meshweave.workers.sync_worker alert-test      # email de prueba (Resend)
python -m meshweave.workers.sync_worker summary-test    # prueba del resumen diario
```

Task Scheduler ejecuta `python -m meshweave.workers.sync_worker run` (o `backup`).

## Configuración (`%ProgramData%\Meshweave\config\config.json`)

Claves principales (públicas — los secretos van a DPAPI):

| Clave | Default | Descripción |
|---|---|---|
| `tunnel_hostname` / `tunnel_id` / `account_tag` | — | Túnel Cloudflare (TunnelSecret en DPAPI) |
| `backend_project_dir` / `backend_command` | — | Backend FastAPI (comando vacío = uvicorn) |
| `supabase_env` | ruta al `.env` local | Credenciales Docker locales |
| `cloud_db_host` / `cloud_db_user` / `cloud_db_port` / `cloud_db_name` | — | Nube (password en DPAPI) |
| `batch_size` / `batch_delay_seconds` / `max_retries` | 200 / 1.5 / 4 | Tuning free tier |
| `schedule_time` / `backup_time` | 01:00 / 01:30 | Horarios de las tareas |
| `backup_retention_days` | 7 | Dumps a conservar |
| `alert_on_error` / `alert_on_partial` / `summary_email` | true | Emails (Resend); API key cifrada en DPAPI |

Edítala desde la sección **Configuración** (guarda de forma atómica con
respaldo `.bak`). Los secretos se escriben en el almacén DPAPI desde la misma
pestaña. Resend se configura completamente aquí; Meshweave no lee credenciales
desde el `.env` del backend.

## Primera instalación (nueva PC)

1. Instala y abre Meshweave → el **asistente de primera configuración** te guía:
   túnel Cloudflare, Supabase (local + nube) y alertas. La carpeta, comando y
   El comando y la carpeta del backend se configuran en la sección **Backend**.
2. Si falta `cloudflared`, descárgalo desde el asistente o la pestaña
   **Diagnóstico** (GitHub Releases → `%ProgramData%\Meshweave\bin\`, verificado).
3. Instala las tareas desde **Sincronización** (01:00 sync / 01:30 backup).
4. Si la PC nueva tiene la DB local vacía, usa **Backups → Restaurar dump**
   para traer los datos desde un dump de la nube (una sola vez).

## Empaquetado y releases

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

Produce `dist\Meshweave.exe`, `Meshweave-Setup-x64.exe` (Inno Setup) y
`Meshweave-portable-x64.zip` + `SHA256SUMS.txt`.

GitHub Actions: `validation.yml` (lint/tests/secret-scan), `build.yml`
(artefactos Windows x64) y `release.yml` (al crear un tag `v*` publica la
release con los artefactos).

### Mirrors de descarga (Catbox / GoFile)

Cuando GitHub Releases va lento para descargar el binario, el workflow de
release **también sube el ZIP portable a mirrors externos** y los publica en
el body de la release (tabla "⚡ Descarga rápida"):

- 🐱 **Catbox** — `https://catbox.moe` (upload anónimo, ~200 MB máx).
- 📁 **GoFile** — `https://gofile.io` (upload anónimo, enlaces públicos).

Si un mirror falla (p. ej. Catbox responde `Invalid uploader`), el paso lo
reporta como aviso y continúa con el otro; la release se crea igual con los
assets en GitHub.

## Seguridad

- Los secretos **nunca** se escriben en logs, errores, diagnósticos ni emails
  (ver `meshweave/logging_setup.redact`).
- `credentials.json`, `sync_config.json` y `secrets.bin` están bloqueados en
  `.gitignore` y el CI falla si algo así aparece rastreado.
- ⚠ Antes de **publicar** el repo: rota el `TunnelSecret` de Cloudflare y el
  password del pooler de Supabase (se compartieron en conversación privada).

## Solución de problemas

| Síntoma | Causa / solución |
|---|---|
| Tarea termina con **0x2** y sin logs | El worker no arrancó: la acción debe ser `python -m meshweave.workers.sync_worker run` (sin `--`). Reinstala desde la pestaña Sincronización. |
| `FATAL: no tenant identifier provided` (local) | El pooler local exige el usuario `postgres.<POOLER_TENANT_ID>` — se resuelve solo leyendo el `.env` de supabase. |
| Error **403 / 1010** de Resend | Falta el header `User-Agent` (ya incluido). Si vuelve, verifica el dominio en Resend. |
| Corrida `partial` | Ver `%ProgramData%\Meshweave\logs\meshweave.log`. Común: conflicto de clave única no-PK (caso `plans`) → alinear ids manualmente. |
| `cloudflared: NO INSTALADO` | Descárgalo desde la pestaña Diagnóstico (GitHub Releases → `bin\`, verificado). |
| Lock huérfano | `state\sync.lock` con más de 6 h se elimina solo; si no, bórralo. |
| Resincronizar todo | Borra `state\sync_state.json` (watermarks) — el próximo run hace full sync. |

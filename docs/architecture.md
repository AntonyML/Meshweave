# Arquitectura de Meshweave

Fecha: 2026-08-16 · Estado: refactor interno completado (Etapas 1-7 del plan)

## Identidad

| Concepto | Valor |
|---|---|
| Nombre comercial | Meshweave |
| Ejecutable | `Meshweave.exe` |
| Repositorio | `meshweave-app` |
| App ID | `com.meshweave.desktop` |
| Tareas de Windows | `MeshweaveSyncService` (01:00), `MeshweaveBackupService` (01:30) |
| Instalación | `C:\Program Files\Meshweave\` |
| Datos del sistema | `C:\ProgramData\Meshweave\` |
| Datos del usuario | `C:\Users\<usuario>\AppData\Local\Meshweave\` |

## Capas

```
ui/            → solo widgets; llama servicios; recibe eventos por cola
services/      → lógica de dominio (túnel, backend, sync, cloudflared, updater)
sync/          → motor (watermark), alerts (Resend), backup (pg_dump)
infra          → paths, config (atómica), secrets (DPAPI), process_runner,
                 windows_tasks, logging (rotativo + redact)
workers/       → CLI headless (Task Scheduler / consola técnica)
```

Reglas:
1. La UI **nunca** toca `subprocess`, `psycopg` ni archivos directamente.
2. Los secretos **nunca** viven en config.json ni se loguean (DPAPI + `redact`).
3. La configuración se escribe de forma atómica (temp → validar → replace → `.bak`).
4. No hay instalación de dependencias en runtime: el ejecutable empaqueta todo;
   si falta algo, se muestra un error claro.
5. Los `.bat` son solo herramientas de desarrollo.

## Decisiones clave

- **DPAPI (CryptProtectData)** en lugar de texto plano para `TunnelSecret` y
  password de la nube. Solo la cuenta de Windows que escribió puede leer.
- **`%ProgramData%\Meshweave`** para datos del sistema: ProgramData permite a
  usuarios estándar crear subcarpetas, así el runtime no necesita admin.
- **Task Scheduler con `StartWhenAvailable`**: si el PC está apagado a la 1 AM,
  la tarea corre al encender (con límite de 2 h).
- **Nube como superset**: el sync nunca borra en la nube (backup conservador).
- **Watermark por tabla `(updated_at, pk)`** persistido tras cada lote:
  reanudable si el proceso muere a mitad.

## Camino a producción (siguiente etapa)

- [x] Etapas 1-2: auditoría, .gitignore, ejemplos, repo, nombre.
- [x] Etapa 3: refactor interno (config/secretos/procesos separados).
- [x] Etapa 4: nueva UI (8 pestañas) sobre servicios.
- [x] Etapa 5: cloudflared_manager (detectar/descargar/verificar).
- [x] Etapa 6: empaquetado (spec PyInstaller + Inno Setup + build.ps1).
- [x] Etapa 7: CI/CD (validation, build, release).
- [ ] Etapa 8: probar build real en máquina limpia, publicar beta, firmar.
- [ ] Restaurar/validar backups desde la UI (parcial: listar + validar).
- [ ] Rotar credenciales antes de cualquier publicación pública.

## Riesgos abiertos

- El password de la nube y el TunnelSecret se compartieron en conversación
  privada: **rotar antes de publicar** (ver `docs/secrets-audit.md`).
- `cloudflared` se descarga desde GitHub Releases; si el release no publica
  checksum, la verificación cae a "PE válido + tamaño" (visible al usuario).
- La ingesta (:8001) escribe en tablas de sync; si un día crece mucho,
  revisar `auto_full_sync_max_rows` y el tamaño de lotes.

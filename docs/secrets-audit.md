# Auditoría de seguridad — Migración TunnelCloudFlare → Meshweave

Fecha: 2026-08-16 · Estado: Etapa 1 (auditoría y protección)

> ⚠ Este documento describe **qué** es sensible y **cómo** se mitiga, pero
> **nunca** contiene los valores de los secretos.

## Inventario de secretos encontrados

| Archivo (origen) | Secreto | Riesgo | Mitigación aplicada |
|---|---|---|---|
| `credentials.json` | `TunnelSecret` de Cloudflare (base64), `AccountTag`, `TunnelID` | Quien lo tenga puede controlar el túnel | Excluido de Git; se migra al almacén DPAPI (`%ProgramData%\Meshweave\secrets.bin`) y se materializa solo en runtime |
| `sync_config.json` | URL del pooler con **password de la DB nube en texto plano** | Acceso total a la DB de la nube | Excluido de Git; el password pasa a DPAPI; `cloud_db_url` se arma en runtime |
| `config.yml` / `config.runtime.yml` | Rutas absolutas + referencia a credenciales | Exposición indirecta | Se generan en runtime bajo `%ProgramData%\Meshweave\config\` |
| `backend.config.json` | Ruta absoluta del proyecto backend | No es secreto, pero rompe portabilidad | Se mueve a `config.json` (configurable desde la UI) |
| `.env` del backend | `RESEND_API_KEY`, credenciales | Secreto de terceros | Se lee en runtime desde su ruta configurada; nunca se copia ni se loguea |

## Antipatrones detectados (a corregir)

1. **Auto-instalación de dependencias con `pip`** al arrancar (`manager.py` y `runManager.bat`) → se elimina; el ejecutable empaqueta sus dependencias y si falta algo muestra un error claro.
2. **`.bat` como mecanismo de ejecución** → quedan solo como herramienta de desarrollo (`scripts/run_dev.bat`); el producto se lanza con `Meshweave.exe`.
3. **Rutas absolutas `E:\...`** → reemplazadas por rutas configurables + estándares de Windows (`%ProgramData%\Meshweave`, `%LOCALAPPDATA%\Meshweave`).
4. **Configuración mezclada con secretos** → separados: config pública en `config.json`, secretos en DPAPI.
5. **`cloudflared.exe` (~54 MB) dentro del proyecto** → se descarga/verifica bajo `%ProgramData%\Meshweave\bin\` (fuera del repo).
6. **Escritura directa de configs** → ahora atómica (temp + validar + reemplazar + respaldo).

## Credenciales comprometidas

- **No hubo historial Git previo** en `TunnelCloudFlare` (carpeta sin repo), por lo que
  los secretos **no** fueron publicados en un repositorio.
- ⚠ La contraseña de la DB nube y el `TunnelSecret` sí se compartieron en esta
  conversación privada. **Antes de cualquier publicación pública del repo**, se
  recomienda rotar ambos (regenerar `TunnelSecret` en Cloudflare Zero Trust y
  cambiar el password del pooler en Supabase). Es barato y elimina el riesgo.

## Reglas a partir de ahora

- Los secretos **nunca** se escriben en logs, mensajes de error, diagnósticos ni emails.
- El diagnóstico exportado filtra cualquier valor que parezca credencial.
- El workflow de CI incluye un paso de *secret scanning* que falla si detecta patrones.
- `.gitignore` bloquea los archivos de credenciales incluso si se intenta `git add -f` (con `core.hooksPath`/pre-commit recomendado en Etapa 7).

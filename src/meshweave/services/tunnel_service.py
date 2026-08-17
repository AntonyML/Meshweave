"""Servicio del túnel Cloudflare: config runtime + proceso controlado.

El config.runtime.yml y el credentials.json se generan bajo
%ProgramData%\\Meshweave\\runtime\\ a partir de la configuración pública y el
TunnelSecret guardado en DPAPI (nunca en el repo ni en config.json).
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from meshweave.config import load_config
from meshweave.errors import ConfigError
from meshweave.paths import runtime_dir
from meshweave.process_runner import CREATE_NO_WINDOW, ProcessRunner
from meshweave.secrets import SecretStore
from meshweave.services import cloudflared_manager


def cloudflared_service_status() -> str:
    """Estado del servicio de Windows 'cloudflared' (sc query)."""
    try:
        result = subprocess.run(["sc", "query", "cloudflared"],
                                capture_output=True, text=True, timeout=5,
                                creationflags=CREATE_NO_WINDOW)
        output = result.stdout.upper()
        if "RUNNING" in output:
            return "running"
        if "STOPPED" in output:
            return "stopped"
        if result.returncode == 1060:
            return "not_installed"
        return "stopped"
    except Exception:  # noqa: BLE001
        return "unknown"


def prepare_runtime(cfg: dict[str, Any] | None = None) -> tuple[bool, str]:
    """Genera config.runtime.yml + credentials.json (desde DPAPI) en runtime_dir."""
    cfg = cfg or load_config()
    try:
        runtime_dir().mkdir(parents=True, exist_ok=True)
        exe = cloudflared_manager.binary_path()
        if not exe.exists():
            return False, "cloudflared.exe no encontrado. Descárgalo en la pestaña Diagnóstico."

        tunnel_id = cfg.get("tunnel_id", "")
        hostname = cfg.get("tunnel_hostname", "")
        port = int(cfg.get("tunnel_local_port", 8000))
        if not tunnel_id:
            return False, "Falta tunnel_id en la configuración (pestaña Configuración)."

        secret = SecretStore().get("tunnel_secret")
        account_tag = cfg.get("account_tag", "")
        if not secret:
            return False, ("Falta el TunnelSecret de Cloudflare (almacén DPAPI). "
                           "Configúralo en la pestaña Configuración.")
        if not account_tag:
            return False, "Falta account_tag en la configuración."

        # credentials.json materializado SOLO en runtime (permisos restringidos).
        creds = runtime_dir() / "credentials.json"
        payload = json.dumps({
            "AccountTag": account_tag,
            "TunnelSecret": secret,
            "TunnelID": tunnel_id,
        })
        fd, tmp_name = tempfile.mkstemp(prefix="creds-", suffix=".json", dir=str(runtime_dir()))
        os.close(fd)
        tmp = Path(tmp_name)
        tmp.write_text(payload, encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, creds)
        try:
            os.chmod(creds, 0o600)
        except OSError:
            pass

        config_rt = runtime_dir() / "config.runtime.yml"
        config_rt.write_text(
            f"tunnel: {tunnel_id}\n"
            f"credentials-file: {creds}\n"
            f"logfile: {runtime_dir().parent / 'logs' / 'tunnel-cloudflared.log'}\n"
            f"loglevel: {cfg.get('tunnel_log_level', 'info')}\n\n"
            f"ingress:\n"
            f"  - hostname: {hostname}\n"
            f"    service: http://127.0.0.1:{port}\n"
            f"  - service: http_status:404\n",
            encoding="utf-8",
        )
        return True, "Config runtime lista y validada."
    except ConfigError as e:
        return False, str(e)
    except OSError as e:
        return False, f"Error de permisos al preparar config: {e}"
    except Exception as e:  # noqa: BLE001
        return False, f"Error preparando config runtime: {e}"


class TunnelService:
    """Proceso cloudflared controlado (foreground, sin consola)."""

    def __init__(self, on_line: Callable[[str], None] | None = None):
        self.runner = ProcessRunner("tunnel", on_line)

    def start(self, cfg: dict[str, Any] | None = None) -> tuple[bool, str]:
        if self.runner.is_alive():
            return False, "El túnel ya está corriendo."
        cfg = cfg or load_config()
        ok, msg = prepare_runtime(cfg)
        if not ok:
            return False, msg
        exe = cloudflared_manager.binary_path()
        config_rt = runtime_dir() / "config.runtime.yml"
        try:
            return self.runner.start(
                [str(exe), "tunnel", "--config", str(config_rt), "run"],
                cwd=runtime_dir(),
            )
        except Exception as e:  # noqa: BLE001
            return False, f"No se pudo iniciar el túnel: {e}"

    def stop(self) -> tuple[bool, str]:
        return self.runner.stop()

    def terminate(self) -> None:
        """Parada best-effort para el cierre de la app."""
        self.runner.terminate()

    @property
    def running(self) -> bool:
        return self.runner.is_alive()

    @property
    def uptime(self) -> str:
        return self.runner.uptime

"""Servicio del backend FastAPI (proceso controlado, sin consola).

La ruta del proyecto y el comando son configurables desde la UI
(backend_project_dir / backend_command en config.json).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

from meshweave.config import load_config
from meshweave.process_runner import ProcessRunner


class BackendService:
    def __init__(self, on_line: Callable[[str], None] | None = None):
        self.runner = ProcessRunner("backend", on_line)

    @staticmethod
    def _python_for(project_dir: Path) -> Path:
        venv = project_dir / ".venv" / "Scripts" / "python.exe"
        return venv if venv.exists() else Path(sys.executable)

    def start(self, project_dir: Path, command: str | None = None) -> tuple[bool, str]:
        if self.runner.is_alive():
            return False, "El backend ya está corriendo."
        if not project_dir.is_dir():
            return False, f"La carpeta del backend no existe: {project_dir}"
        if not (project_dir / "app" / "main.py").exists():
            return False, "La carpeta no parece un backend FastAPI válido (falta app/main.py)."

        if command and command.strip():
            cmd = [str(self._python_for(project_dir)), *command.strip().split()]
        else:
            cmd = [str(self._python_for(project_dir)), "-m", "uvicorn", "app.main:app",
                   "--host", "127.0.0.1", "--port", "8000", "--workers", "4"]
        try:
            return self.runner.start(cmd, cwd=project_dir)
        except Exception as e:  # noqa: BLE001
            return False, f"No se pudo iniciar el backend: {e}"

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


def default_backend_dir(cfg: dict[str, Any] | None = None) -> Path:
    """Ruta del backend desde config (o vacía si no está configurada)."""
    cfg = cfg or load_config()
    return Path(cfg.get("backend_project_dir") or "")

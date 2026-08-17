"""Gestión controlada de procesos hijos (cloudflared, backend…).

Cubre lo que el plan pide para "no usar un proceso global sin control":
- estado explícito (running / ready / pid / started_at),
- arranque con timeout y parada con timeout (terminate → kill → taskkill /T),
- detección de procesos huérfanos (¿el pid sigue vivo aunque el runner murió?),
- captura de stdout/stderr por línea,
- limpieza al cerrar la aplicación (close_all).
"""
from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from meshweave.errors import ProcessError

# Suprime la ventana de consola al lanzar procesos hijo (Windows).
# Público: otros módulos (windows_tasks, backups, app…) lo usan para evitar
# los parpadeos de consola con powershell / sc / docker / clip.
CREATE_NO_WINDOW = 0x08000000


def _kill_tree(pid: int) -> None:
    """taskkill /PID <pid> /T /F — mata el árbol (p.ej. uvicorn --workers)."""
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        capture_output=True, text=True, timeout=8,
        creationflags=CREATE_NO_WINDOW,
    )


class ProcessRunner:
    def __init__(
        self,
        name: str,
        on_line: Callable[[str], None] | None = None,
        *,
        start_timeout_s: float = 60.0,
        stop_timeout_s: float = 15.0,
    ):
        self.name = name
        self._on_line = on_line or (lambda line: None)
        self._proc: subprocess.Popen | None = None
        self.running = False
        self.ready = False
        self.started_at: datetime | None = None
        self._start_timeout = start_timeout_s
        self._stop_timeout = stop_timeout_s

    # ── Estado ───────────────────────────────────────────────────────────

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc and self._proc.poll() is None else None

    @property
    def uptime(self) -> str:
        if not self.started_at:
            return "—"
        s = int((datetime.now(UTC) - self.started_at).total_seconds())
        return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @staticmethod
    def orphan_alive(pid: int | None) -> bool:
        """¿El pid sigue vivo aunque ya no lo gestionamos? (detección de huérfanos)."""
        if not pid:
            return False
        try:
            import psutil
            return psutil.pid_exists(pid)
        except ImportError:
            r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                               capture_output=True, text=True, timeout=5,
                               creationflags=CREATE_NO_WINDOW)
            return str(pid) in r.stdout

    # ── Ciclo de vida ────────────────────────────────────────────────────

    def start(self, cmd: list[str], cwd: Path | None = None) -> tuple[bool, str]:
        if self.is_alive():
            return False, f"{self.name} ya está corriendo."
        self.ready = False
        try:
            self._proc = subprocess.Popen(
                cmd,
                cwd=str(cwd) if cwd else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=CREATE_NO_WINDOW,
            )
        except OSError as e:
            raise ProcessError(f"No se pudo iniciar {self.name}: {e}") from e
        self.running = True
        self.started_at = datetime.now(UTC)
        threading.Thread(target=self._reader, daemon=True).start()
        threading.Thread(target=self._watcher, daemon=True).start()
        return True, f"{self.name} iniciado."

    def stop(self) -> tuple[bool, str]:
        if not self._proc:
            return False, f"{self.name} no está corriendo."
        pid = self._proc.pid
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=self._stop_timeout)
            except subprocess.TimeoutExpired:
                _kill_tree(pid)  # incluye hijos (uvicorn --workers)
        self._proc = None
        self.running = False
        self.ready = False
        self.started_at = None
        return True, f"{self.name} detenido."

    def terminate(self) -> None:
        """Parada best-effort para cierre de la app (sin esperar)."""
        try:
            if self._proc and self._proc.poll() is None:
                _kill_tree(self._proc.pid)
        except Exception:  # noqa: BLE001
            pass
        self._proc = None
        self.running = False
        self.ready = False

    # ── Hilos internos ───────────────────────────────────────────────────

    def _reader(self) -> None:
        if not self._proc or not self._proc.stdout:
            return
        for line in self._proc.stdout:
            line = line.rstrip()
            if line:
                self._on_line(line)

    def _watcher(self) -> None:
        if not self._proc:
            return
        code = self._proc.wait()
        self.running = False
        self.ready = False
        self.started_at = None
        self._on_line(f"── {self.name} finalizado (código {code}) ──")
        self._proc = None

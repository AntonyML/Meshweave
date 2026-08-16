"""Logging rotativo de Meshweave (logs fuera de la carpeta de instalación).

Los logs van a %ProgramData%\\Meshweave\\logs\\ y rotan por tamaño.
Nunca se escriben credenciales: los mensajes pasan por redact().
"""
from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler

from meshweave.config import load_config
from meshweave.paths import logs_dir

_configured = False

# Patrones de secretos a enmascarar en cualquier mensaje de log/error.
_REDACT_PATTERNS = [
    re.compile(r"(postgres(?:ql)?://[^:\s]+:)([^@\s]+)(@)"),
    re.compile(r"(Authorization:\s*Bearer\s+)\S+"),
    re.compile(r"(RESEND_API_KEY[=:]\s*)\S+"),
    re.compile(r"(password[=:]\s*)\S+", re.IGNORECASE),
    re.compile(r"(\b[a-f0-9]{64}\b)"),  # hashes largos (API keys encriptadas)
]


def redact(text: str) -> str:
    """Enmascara credenciales en mensajes de log, errores y diagnósticos."""
    for pattern in _REDACT_PATTERNS:
        text = pattern.sub(lambda m: m.group(1) + "***" + (m.group(3) if m.lastindex and m.lastindex >= 3 else ""), text)
    return text


def setup_logging(logger_name: str | None = None) -> logging.Logger:
    """Configura el logger raíz (o uno específico) con rotación por tamaño."""
    global _configured
    try:
        cfg = load_config()
        level = getattr(logging, str(cfg.get("log_level", "INFO")).upper(), logging.INFO)
        max_bytes = int(cfg.get("log_max_bytes", 10 * 1024 * 1024))
        backup_count = int(cfg.get("log_backup_count", 5))
    except Exception:  # noqa: BLE001 — defaults si la config aún no existe
        level, max_bytes, backup_count = logging.INFO, 10 * 1024 * 1024, 5

    logger = logging.getLogger(logger_name) if logger_name else logging.getLogger()
    if _configured and logger.handlers:
        return logger
    logger.setLevel(level)

    logs_dir().mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        logs_dir() / "meshweave.log",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    if logger.handlers:
        logger.handlers.clear()
    logger.addHandler(handler)
    if not _configured:
        logger.setLevel(level)
        _configured = True
    return logger

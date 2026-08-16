"""Errores tipados de la aplicación."""


class MeshweaveError(Exception):
    """Error base de la aplicación."""


class ConfigError(MeshweaveError):
    """Configuración ausente, inválida o ilegible."""


class SecretsError(MeshweaveError):
    """Fallo del almacén de credenciales (DPAPI)."""


class ProcessError(MeshweaveError):
    """Fallo al gestionar un proceso (arranque, parada, timeout…)."""


class DownloadError(MeshweaveError):
    """Fallo al descargar/verificar un binario."""

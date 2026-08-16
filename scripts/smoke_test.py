"""Smoke test headless de Meshweave (para CI / validación de build).

Abre la ventana unos segundos, verifica que las pestañas existen y cierra.
No requiere pantalla real en Windows con escritorio activo.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

# Redirigir los datos a un directorio temporal (no tocar ProgramData en CI).
os.environ["MESHWEAVE_DATA_DIR"] = os.environ.get(
    "MESHWEAVE_DATA_DIR", os.path.join(tempfile.mkdtemp(prefix="meshweave-smoke-"), "data")
)

EXPECTED_TABS = ["Dashboard", "Túnel", "Backend", "Sincronización", "Backups",
                 "Configuración", "Logs", "Diagnóstico"]


def main() -> int:
    from meshweave.app import App

    app = App()
    tabs = list(app._tabs._tab_dict.keys())
    if tabs != EXPECTED_TABS:
        print(f"ERROR: pestañas inesperadas: {tabs}")
        app.destroy()
        return 1
    print("Pestañas OK:", tabs)

    # Ejecuta el ciclo de la UI brevemente y cierra.
    def _close():
        time.sleep(2.5)
        app.after(0, app._on_close)

    import threading
    threading.Thread(target=_close, daemon=True).start()
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            app.update()
        except Exception as e:  # noqa: BLE001
            print(f"ERROR durante update(): {e}")
            return 1
        if not app.winfo_exists():
            break
        time.sleep(0.02)
    else:
        print("ERROR: timeout esperando cierre de la ventana")
        return 1
    print("Smoke test OK — ventana abrió y cerró limpiamente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

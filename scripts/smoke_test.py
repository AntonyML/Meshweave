"""Smoke test headless de Meshweave (para CI / validación de build).

Abre la ventana, verifica que las pestañas existen y cierra limpiamente.
No requiere mainloop: usa update() en bucle con timeout, y el cierre se
programa desde el hilo principal (llamar a app.after desde un hilo no es
seguro en modo headless).
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

    # Cierre programado desde el hilo principal (thread-safe).
    app.after(2500, app._on_close)

    # Bucle de eventos manual con timeout duro (no puede colgarse).
    deadline = time.time() + 25
    closed_cleanly = False
    while time.time() < deadline:
        try:
            app.update()
            if not app.winfo_exists():
                closed_cleanly = True
                break
        except Exception:  # noqa: BLE001 — la app ya fue destruida
            closed_cleanly = True
            break
        time.sleep(0.02)
    if not closed_cleanly:
        print("ERROR: timeout esperando cierre de la ventana")
        return 1
    print("Smoke test OK — ventana abrió y cerró limpiamente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

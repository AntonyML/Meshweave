@echo off
REM ============================================================
REM Meshweave - Launcher de DESARROLLO (no es el mecanismo del
REM producto final; el producto se lanza con Meshweave.exe).
REM Instala el paquete en modo editable y abre la GUI.
REM ============================================================
setlocal
cd /d "%~dp0\.."

set "VENV=.venv"
set "PYTHON=%VENV%\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo [setup] Creando entorno virtual...
    python -m venv "%VENV%" || goto :fatal
)

echo [setup] Verificando dependencias (pip install -e .)...
"%PYTHON%" -m pip install -q --disable-pip-version-check -e . "psycopg[binary]" psutil customtkinter || goto :fatal

echo [run] Lanzando Meshweave (dev)...
"%PYTHON%" -m meshweave %*
exit /b %errorlevel%

:fatal
echo [ERROR] No se pudo preparar el entorno. Revisa que Python 3.11+ esté instalado.
pause
exit /b 1

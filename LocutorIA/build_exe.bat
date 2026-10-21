@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ============================================================
echo   LOCUTOR IA  -  Creando el programa (LocutorIA.exe)
echo ============================================================
where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo  Falta Python. Instala Python 3.11 o 3.12 desde https://www.python.org/downloads/
  echo  y marca la casilla "Add python.exe to PATH". Luego ejecuta este archivo otra vez.
  pause & exit /b 1
)
if not exist .venv ( python -m venv .venv || goto :error )
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip || goto :error
powershell -NoProfile -ExecutionPolicy Bypass -File build_windows.ps1 || goto :error
echo.
echo  El programa esta en:  dist\LocutorIA\LocutorIA.exe
echo  Copia la carpeta "LocutorIA" completa donde quieras (por ejemplo C:\LocutorIA).
echo.
pause & exit /b 0

:error
echo.
echo  Hubo un error. Revisa los mensajes de arriba (y que tengas internet).
pause & exit /b 1

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
pip install -r requirements.txt pyinstaller || goto :error

echo.
echo [1/3] Empaquetando la aplicacion...
pyinstaller --noconfirm --clean --windowed --name LocutorIA --add-data "locutor\static;locutor\static" --collect-all webview main.py || goto :error

echo.
echo [2/3] Descargando ffmpeg y yt-dlp a la carpeta "herramientas"...
mkdir dist\LocutorIA\herramientas 2>nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe' -OutFile 'dist\LocutorIA\herramientas\yt-dlp.exe'; Invoke-WebRequest 'https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip' -OutFile 'ffmpeg.zip'; Expand-Archive -Force ffmpeg.zip -DestinationPath ffmpeg_tmp; Copy-Item (Get-ChildItem ffmpeg_tmp -Recurse -Filter ffmpeg.exe | Select-Object -First 1).FullName 'dist\LocutorIA\herramientas\ffmpeg.exe'; Remove-Item ffmpeg.zip,ffmpeg_tmp -Recurse -Force } catch { Write-Host 'No se pudieron descargar las herramientas: copia ffmpeg.exe y yt-dlp.exe a dist\LocutorIA\herramientas manualmente.' }"

echo.
echo [3/3] Listo.
echo.
echo  El programa esta en:  dist\LocutorIA\LocutorIA.exe
echo  Copia la carpeta "LocutorIA" completa donde quieras (por ejemplo C:\LocutorIA)
echo  y crea un acceso directo a LocutorIA.exe en el escritorio.
echo.
pause & exit /b 0

:error
echo.
echo  Hubo un error. Revisa los mensajes de arriba (y que tengas internet).
pause & exit /b 1

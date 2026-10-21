# Compila Locutor IA para Windows y descarga las herramientas (ffmpeg, ffprobe, yt-dlp, deno).
# Lo usan build_exe.bat (en tu PC) y el flujo de GitHub Actions.
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

pip install -r requirements.txt pyinstaller
if ($LASTEXITCODE -ne 0) { throw "No se pudieron instalar las dependencias" }

pyinstaller --noconfirm --clean --windowed --name LocutorIA --add-data "locutor/static;locutor/static" --collect-all webview --collect-all pythonnet --collect-all clr_loader main.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller fallo" }

$h = "dist/LocutorIA/herramientas"
New-Item -ItemType Directory $h -Force | Out-Null

Write-Host "Descargando yt-dlp..."
Invoke-WebRequest "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe" -OutFile "$h/yt-dlp.exe"

Write-Host "Descargando ffmpeg y ffprobe..."
Invoke-WebRequest "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip" -OutFile ffmpeg.zip
Expand-Archive -Force ffmpeg.zip -DestinationPath ff_tmp
foreach ($n in "ffmpeg.exe", "ffprobe.exe") {
  Copy-Item (Get-ChildItem ff_tmp -Recurse -Filter $n | Select-Object -First 1).FullName "$h/$n"
}
Remove-Item ffmpeg.zip, ff_tmp -Recurse -Force

Write-Host "Descargando Deno (motor JavaScript que YouTube exige)..."
Invoke-WebRequest "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip" -OutFile deno.zip
Expand-Archive -Force deno.zip -DestinationPath deno_tmp
Copy-Item (Get-ChildItem deno_tmp -Recurse -Filter deno.exe | Select-Object -First 1).FullName "$h/deno.exe"
Remove-Item deno.zip, deno_tmp -Recurse -Force

Get-ChildItem $h | Format-Table Name, Length
Write-Host "LISTO: dist/LocutorIA/LocutorIA.exe"

"""Rutas de la aplicación (funciona igual en desarrollo y dentro del .exe)."""
import os
import shutil
import sys
from pathlib import Path


def frozen():
    return bool(getattr(sys, "frozen", False))


def recursos():
    """Carpeta donde viven los recursos empaquetados (static/...)."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def exe_dir():
    return Path(sys.executable).parent if frozen() else Path(__file__).resolve().parent.parent


def data_dir():
    r = os.environ.get("LOCUTOR_DATA")
    if r:
        p = Path(r)
    elif os.name == "nt":
        p = Path(os.environ.get("APPDATA", str(Path.home()))) / "LocutorIA"
    else:
        p = Path.home() / ".locutor_ia"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _buscar(nombre):
    exe = ".exe" if os.name == "nt" else ""
    for c in (exe_dir() / "herramientas" / (nombre + exe), exe_dir() / (nombre + exe),
              exe_dir() / "ffmpeg" / (nombre + exe), data_dir() / (nombre + exe)):
        if c.exists():
            return str(c)
    return shutil.which(nombre)


def ffmpeg():
    return _buscar("ffmpeg")


def ytdlp():
    return _buscar("yt-dlp")


def sin_ventana():
    """Evita que aparezcan consolas negras al lanzar ffmpeg/yt-dlp en Windows."""
    return {"creationflags": 0x08000000} if os.name == "nt" else {}

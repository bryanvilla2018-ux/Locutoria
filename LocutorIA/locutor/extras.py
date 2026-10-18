"""Clima, titulares RSS y descargas de YouTube (usa yt-dlp como programa externo, fácil de actualizar)."""
import json
import re
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

from . import paths
from .store import nuevo_id

# ----------------------------------------------------------------------------- clima
_WMO = {0: "despejado", 1: "mayormente despejado", 2: "parcialmente nublado", 3: "nublado", 45: "con neblina", 48: "con neblina",
        51: "con llovizna", 53: "con llovizna", 55: "con llovizna", 61: "con lluvia ligera", 63: "con lluvia", 65: "con lluvia fuerte",
        80: "con chubascos", 81: "con chubascos", 82: "con chubascos fuertes", 95: "con tormenta", 96: "con tormenta", 99: "con tormenta"}
_cache = {"clima": (0, None), "noticias": (0, [])}


def clima(cfg):
    if not cfg["clima"]["activo"]:
        return None
    if time.time() - _cache["clima"][0] < 600:
        return _cache["clima"][1]
    try:
        e = cfg["estacion"]
        r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=6, params={
            "latitude": e["latitud"], "longitude": e["longitud"], "current": "temperature_2m,weather_code", "timezone": "auto"})
        c = r.json()["current"]
        v = f"{round(c['temperature_2m'])} grados, {_WMO.get(c['weather_code'], 'variable')}"
    except Exception:
        v = None
    _cache["clima"] = (time.time(), v)
    return v


# ----------------------------------------------------------------------------- noticias RSS
def titulares(cfg):
    n = cfg["noticias"]
    if not n["activo"] or not n["feeds"]:
        return []
    if time.time() - _cache["noticias"][0] < 900:
        return _cache["noticias"][1]
    out = []
    for url in n["feeds"]:
        try:
            r = requests.get(url, timeout=8, headers={"User-Agent": "LocutorIA/1.0"})
            root = ET.fromstring(r.content)
            for it in root.iter("item"):
                t = re.sub(r"\s+", " ", (it.findtext("title") or "")).strip()
                if t:
                    out.append(t)
                if len(out) >= int(n["max_titulares"]) * len(n["feeds"]):
                    break
        except Exception:
            continue
    out = out[: max(int(n["max_titulares"]), 1) * 2]
    _cache["noticias"] = (time.time(), out)
    return out


# ----------------------------------------------------------------------------- YouTube
def _cmd_ytdlp():
    exe = paths.ytdlp()
    if exe:
        return [exe]
    try:
        import yt_dlp  # noqa: F401
        return [sys.executable, "-m", "yt_dlp"]
    except ImportError:
        return None


class YouTube:
    def __init__(self, ajustes, voz, hacer_rb, log):
        self.aj, self.voz, self.hacer_rb, self.log = ajustes, voz, hacer_rb, log
        self.jobs, self.lock = {}, threading.Lock()

    def disponible(self):
        return _cmd_ytdlp() is not None

    def buscar(self, q, n=8):
        cmd = _cmd_ytdlp()
        if not cmd:
            raise RuntimeError("No encuentro yt-dlp (ponlo en la carpeta 'herramientas').")
        r = subprocess.run(cmd + [f"ytsearch{n}:{q}", "--flat-playlist", "--dump-json", "--no-warnings"],
                           capture_output=True, text=True, timeout=60, **paths.sin_ventana())
        if r.returncode and not r.stdout:
            raise RuntimeError(r.stderr.strip()[-300:] or "yt-dlp falló")
        out = []
        for linea in r.stdout.splitlines():
            try:
                j = json.loads(linea)
            except ValueError:
                continue
            out.append({"id": j.get("id"), "titulo": j.get("title"), "canal": j.get("channel") or j.get("uploader") or "",
                        "dur": int(j.get("duration") or 0), "url": j.get("url") or f"https://www.youtube.com/watch?v={j.get('id')}",
                        "mini": f"https://i.ytimg.com/vi/{j.get('id')}/mqdefault.jpg"})
        return out

    def descargar(self, url, titulo, destino):
        jid = nuevo_id()
        with self.lock:
            self.jobs[jid] = {"id": jid, "titulo": titulo or url, "estado": "en cola", "pct": 0, "ruta": "", "error": "", "destino": destino}
        threading.Thread(target=self._trabajo, args=(jid, url), daemon=True).start()
        return jid

    def _set(self, jid, **kw):
        with self.lock:
            self.jobs[jid].update(kw)

    def estado(self):
        with self.lock:
            return list(self.jobs.values())[::-1]

    def _trabajo(self, jid, url):
        try:
            cmd = _cmd_ytdlp()
            if not cmd:
                raise RuntimeError("No encuentro yt-dlp.")
            carpeta = Path(self.aj.datos["carpetas"].get("youtube") or Path.home() / "Music" / "LocutorIA-YouTube")
            carpeta.mkdir(parents=True, exist_ok=True)
            ff = paths.ffmpeg()
            args = cmd + ["-x", "--audio-format", "mp3", "--audio-quality", "192K", "--embed-metadata", "--no-playlist", "--windows-filenames",
                          "--trim-filenames", "150", "--newline", "--progress", "--progress-template", "download:[dl] %(progress._percent_str)s",
                          "--print", "after_move:filepath", "-o", str(carpeta / "%(title)s.%(ext)s")]
            if ff:
                args += ["--ffmpeg-location", str(Path(ff).parent)]
            self._set(jid, estado="descargando")
            p = subprocess.Popen(args + [url], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                 errors="replace", **paths.sin_ventana())
            ruta, cola = "", []
            for linea in p.stdout:
                linea = linea.strip()
                m = re.match(r"\[dl\]\s+([\d.]+)%", linea)
                if m:
                    self._set(jid, pct=float(m[1]), estado="descargando" if float(m[1]) < 100 else "convirtiendo")
                elif linea:
                    cola.append(linea)
                    if Path(linea).suffix.lower() == ".mp3":
                        ruta = linea
            if p.wait() or not ruta:
                raise RuntimeError(" ".join(cola[-2:])[:300] or "yt-dlp no devolvió archivo")
            self._set(jid, ruta=ruta, estado="listo", pct=100)
            dest = self.jobs[jid]["destino"]
            if dest in ("siguiente", "final"):
                ok = self.hacer_rb().insertar(ruta, -2 if dest == "siguiente" else -1)
                self.log("info" if ok else "aviso", f"YouTube → RadioBOSS ({dest}): {Path(ruta).name}" + ("" if ok else " (RadioBOSS la rechazó)"))
                self._set(jid, estado="en RadioBOSS" if ok else "listo (no se pudo insertar)")
        except Exception as e:
            self.log("aviso", f"YouTube: {e}")
            self._set(jid, estado="error", error=str(e)[:300])

    def actualizar(self):
        cmd = _cmd_ytdlp()
        if not cmd or cmd[0] == sys.executable:
            return "yt-dlp está dentro de Python: actualízalo con  pip install -U yt-dlp"
        r = subprocess.run(cmd + ["-U"], capture_output=True, text=True, timeout=120, **paths.sin_ventana())
        return (r.stdout + r.stderr).strip()[-400:]

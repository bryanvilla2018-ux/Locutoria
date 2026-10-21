"""Clima, titulares RSS y descargas de YouTube (usa yt-dlp como programa externo, fácil de actualizar)."""
import json
import os
import re
import subprocess
import sys
import tempfile
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


def _env():
    e = dict(os.environ)
    e.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1")      # nombres con tildes/ñ bien leídos en Windows
    return e


def pista(texto):
    """Traduce los errores típicos de yt-dlp a algo accionable."""
    t = (texto or "").lower()
    if "not a bot" in t or "sign in to confirm" in t or "cookies" in t and "sign in" in t:
        return "YouTube pide comprobar que no eres un robot. En Ajustes → Sistema elige un navegador en «Cookies de YouTube» (Firefox es el que mejor funciona) y entra a YouTube en ese navegador."
    if "javascript runtime" in t or "challenge" in t or "requested format is not available" in t or "not available" in t and "video" in t:
        return "Falta el motor de JavaScript (Deno) o yt-dlp está desactualizado. Usa «Comprobar YouTube» y «Actualizar yt-dlp»; si no hay deno.exe en la carpeta «herramientas», vuelve a compilar con la versión nueva."
    if "ffmpeg" in t or "ffprobe" in t:
        return "Falta ffmpeg/ffprobe en la carpeta «herramientas»."
    if "403" in t or "forbidden" in t:
        return "YouTube rechazó la descarga (403). Prueba «Actualizar yt-dlp» o activa las cookies del navegador en Ajustes → Sistema."
    if "private" in t or "unavailable" in t or "removed" in t:
        return "Ese video no está disponible (privado, borrado o con restricción de país)."
    return ""


class YouTube:
    def __init__(self, ajustes, voz, hacer_rb, log):
        self.aj, self.voz, self.hacer_rb, self.log = ajustes, voz, hacer_rb, log
        self.jobs, self.lock = {}, threading.Lock()

    def disponible(self):
        return _cmd_ytdlp() is not None

    def _base(self):
        a, c = [], self.aj.datos
        d = paths.deno()
        if d:
            a += ["--js-runtimes", f"deno:{d}"]
        a += ["--remote-components", "ejs:github"]
        if c["sistema"].get("yt_cookies"):
            a += ["--cookies-from-browser", c["sistema"]["yt_cookies"]]
        ff = paths.ffmpeg()
        if ff:
            a += ["--ffmpeg-location", str(Path(ff).parent)]
        return a

    def _correr(self, args, timeout=90):
        return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=_env(), **paths.sin_ventana())

    def buscar(self, q, n=8):
        cmd = _cmd_ytdlp()
        if not cmd:
            raise RuntimeError("No encuentro yt-dlp (debe estar en la carpeta «herramientas» junto al programa).")
        r = self._correr(cmd + [f"ytsearch{n}:{q}", "--flat-playlist", "--dump-json", "--no-warnings"], 60)
        if r.returncode and not r.stdout:
            raise RuntimeError((r.stderr.strip()[-300:] or "yt-dlp falló") + " " + pista(r.stderr))
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
            marca = Path(tempfile.gettempdir()) / f"locutor_yt_{jid}.txt"
            t0 = time.time() - 2
            args = cmd + self._base() + ["-x", "--audio-format", "mp3", "--audio-quality", "192K", "--embed-metadata", "--no-playlist",
                                         "--windows-filenames", "--trim-filenames", "150", "--newline", "--progress",
                                         "--progress-template", "download:[dl] %(progress._percent_str)s",
                                         "--print-to-file", "after_move:filepath", str(marca), "-o", str(carpeta / "%(title)s.%(ext)s"), url]
            self._set(jid, estado="descargando")
            p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                 env=_env(), **paths.sin_ventana())
            ruta, cola = "", []
            for linea in p.stdout:
                linea = linea.strip()
                m = re.match(r"\[dl\]\s+([\d.]+)%", linea)
                if m:
                    self._set(jid, pct=float(m[1]), estado="descargando" if float(m[1]) < 100 else "convirtiendo")
                elif linea:
                    cola.append(linea)
                    if Path(linea).suffix.lower() == ".mp3" and not ruta:
                        ruta = linea
            codigo = p.wait()
            if marca.exists():                                   # la ruta exacta, escrita en UTF-8 por yt-dlp
                lineas = [x.strip() for x in marca.read_text("utf-8", errors="replace").splitlines() if x.strip()]
                marca.unlink(missing_ok=True)
                if lineas:
                    ruta = lineas[-1]
            if not ruta or not Path(ruta).exists():              # último recurso: el mp3 más reciente de la carpeta
                nuevos = [f for f in carpeta.glob("*.mp3") if f.stat().st_mtime >= t0]
                ruta = str(max(nuevos, key=lambda f: f.stat().st_mtime)) if nuevos else ""
            if not ruta:
                detalle = " ".join(cola[-3:])[:400] or "yt-dlp no devolvió ningún archivo"
                raise RuntimeError((detalle + "  →  " + pista(" ".join(cola))).strip(" →"))
            self._set(jid, ruta=ruta, estado="listo", pct=100)
            dest = self.jobs[jid]["destino"]
            if dest in ("siguiente", "final"):
                ok = self.hacer_rb().insertar(ruta, -2 if dest == "siguiente" else -1)
                self.log("ok" if ok else "aviso", f"YouTube → RadioBOSS ({dest}): {Path(ruta).name}" + ("" if ok else " (RadioBOSS la rechazó)"))
                self._set(jid, estado="en RadioBOSS" if ok else "listo (no se pudo insertar)")
        except Exception as e:
            self.log("aviso", f"YouTube: {e}")
            self._set(jid, estado="error", error=str(e)[:500])

    def probar(self):
        """Diagnóstico de YouTube: versiones, motor JS y una extracción real de prueba."""
        res = []
        cmd = _cmd_ytdlp()
        if not cmd:
            return [{"nombre": "yt-dlp", "ok": False, "detalle": "No encontrado en la carpeta «herramientas»."}]
        try:
            res.append({"nombre": "yt-dlp", "ok": True, "detalle": "versión " + self._correr(cmd + ["--version"], 20).stdout.strip()})
        except Exception as e:
            return [{"nombre": "yt-dlp", "ok": False, "detalle": str(e)[:200]}]
        d = paths.deno()
        if d:
            try:
                res.append({"nombre": "Deno (motor JS)", "ok": True, "detalle": self._correr([d, "--version"], 20).stdout.splitlines()[0]})
            except Exception as e:
                res.append({"nombre": "Deno (motor JS)", "ok": False, "detalle": str(e)[:200]})
        else:
            res.append({"nombre": "Deno (motor JS)", "ok": False, "detalle": "No está en «herramientas». Sin él, YouTube suele fallar. Recompila con la versión nueva."})
        ff = paths.ffmpeg()
        res.append({"nombre": "ffmpeg", "ok": bool(ff), "detalle": ff or "No encontrado"})
        try:
            r = self._correr(cmd + self._base() + ["--simulate", "--no-warnings", "--no-playlist", "-f", "ba/b",
                                                   "https://www.youtube.com/watch?v=jNQXAC9IVRw"], 120)
            if r.returncode == 0:
                res.append({"nombre": "Extracción de prueba", "ok": True, "detalle": "YouTube respondió y entregó el audio. Todo bien."})
            else:
                err = (r.stderr.strip().splitlines() or ["sin detalle"])[-1][:300]
                res.append({"nombre": "Extracción de prueba", "ok": False, "detalle": err + "  →  " + (pista(r.stderr) or "Copia este mensaje para pedir ayuda.")})
        except Exception as e:
            res.append({"nombre": "Extracción de prueba", "ok": False, "detalle": str(e)[:300]})
        return res

    def actualizar(self):
        cmd = _cmd_ytdlp()
        if not cmd or cmd[0] == sys.executable:
            return "yt-dlp está dentro de Python: actualízalo con  pip install -U yt-dlp"
        r = self._correr(cmd + ["-U"], 180)
        return (r.stdout + r.stderr).strip()[-400:]

    def actualizar_auto(self):
        """Una vez al día, al abrir el programa, actualiza yt-dlp (YouTube cambia seguido)."""
        try:
            exe = paths.ytdlp()
            marca = paths.data_dir() / "yt_ultima_actualizacion.txt"
            if not (self.aj.datos["sistema"].get("yt_autoactualizar") and exe and Path(exe).parent.name == "herramientas"):
                return
            if marca.exists() and time.time() - marca.stat().st_mtime < 86400:
                return
            r = self.actualizar()
            marca.write_text(r, "utf-8")
            self.log("info", "yt-dlp revisado/actualizado: " + r.splitlines()[-1][:120] if r else "yt-dlp revisado.")
        except Exception:
            pass

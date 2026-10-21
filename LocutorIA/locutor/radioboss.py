"""Cliente de la API HTTP de RadioBOSS (Settings > API)."""
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

_RUIDO = re.compile(r"[\(\[]\s*(official|oficial|video|lyric|letra|audio|hd|4k|mv|visualizer)[^\)\]]*[\)\]]", re.I)


def limpiar(s):
    """Quita basura típica de títulos de YouTube: (Official Video), [HD], etc."""
    return re.sub(r"\s+", " ", _RUIDO.sub("", s or "")).strip(" -_")


def parse_dur(s):
    try:
        seg = 0
        for p in s.split(":"):
            seg = seg * 60 + int(p)
        return seg
    except (ValueError, AttributeError):
        return 0


def a_track(el):
    if el is None:
        return None
    a = el.attrib
    fn = a.get("FILENAME", "")
    base = Path(fn.replace("\\", "/")).stem
    artista, titulo = limpiar(a.get("ARTIST")), limpiar(a.get("TITLE"))
    if not titulo:
        if " - " in base:
            artista, titulo = [limpiar(x) for x in base.split(" - ", 1)]
        else:
            titulo = limpiar(base)
    return {"archivo": fn, "artista": artista, "titulo": titulo, "dur": parse_dur(a.get("DURATION", ""))}


def etiqueta(t):
    return f"{t['titulo']} (artista: {t['artista']})" if t["artista"] else t["titulo"]


class RadioBoss:
    def __init__(self, c):
        self.base = f"http://{c['host']}:{int(c['puerto'])}/"
        self.auth = {"pass": c.get("password", "")}
        if c.get("usuario"):
            self.auth["user"] = c["usuario"]
        self.pos = int(c.get("posicion", -2))

    def _get(self, **p):
        r = requests.get(self.base, params={**self.auth, **p}, timeout=5)
        r.raise_for_status()
        return r.content

    def version(self):
        root = ET.fromstring(self._get(action="status"))
        return root.find("Player").get("version")

    def info(self):
        root = ET.fromstring(self._get(action="playbackinfo"))
        pb = root.find("Playback")
        try:
            pos = float(pb.get("pos") or 0)
        except (TypeError, ValueError, AttributeError):
            pos = 0.0
        return {"estado": pb.get("state") if pb is not None else "stop", "pos": pos,
                "actual": a_track(root.find("CurrentTrack/TRACK")),
                "siguiente": a_track(root.find("NextTrack/TRACK"))}

    def insertar(self, ruta, pos=None, titulo=None):
        p = {"action": "inserttrack", "filename": str(ruta), "pos": self.pos if pos is None else pos}
        if titulo:
            p["streamingtitle"] = titulo
        return self._get(**p).decode("utf-8", "ignore").strip().upper().startswith("OK")

    def insertar_en_orden(self, rutas, titulo=None):
        """pos -2/-3 insertan siempre justo después de lo que suena: se insertan al revés para que queden en orden."""
        return all([self.insertar(r, None, titulo) for r in reversed(rutas)])

"""Voz: síntesis (ElevenLabs / OpenAI / Edge) + masterizado de radio con ffmpeg."""
import asyncio
import hashlib
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

import requests

from . import paths


class Voz:
    def __init__(self, ajustes):
        self.aj = ajustes

    @property
    def cfg(self):
        return self.aj.datos

    def carpeta(self, que):
        c = self.cfg["carpetas"].get(que) or str(paths.data_dir() / "audio" / que)
        Path(c).mkdir(parents=True, exist_ok=True)
        return Path(c)

    def clave(self, nombre):
        return self.cfg["claves"].get(nombre) or os.getenv(nombre.upper() + "_API_KEY") or ""

    # --- síntesis ---------------------------------------------------------------------
    def _pron(self, texto):
        for r in self.cfg.get("pronunciacion", []):
            if r.get("palabra") and r.get("como"):
                texto = re.sub(rf"(?<!\w){re.escape(r['palabra'])}(?!\w)", r["como"], texto, flags=re.I)
        return texto

    def _tts(self, texto, rol, destino):
        t = self.cfg["tts"]
        prov = t["proveedor"]
        c = t[prov]
        voz = c.get(f"voz_{rol}") or c.get("voz_locutor")
        if prov == "elevenlabs":
            if not voz or not self.clave("elevenlabs"):
                raise RuntimeError("ElevenLabs: falta la clave o el ID de la voz (pestaña Voz).")
            r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voz}", timeout=40,
                              params={"output_format": "mp3_44100_128"}, headers={"xi-api-key": self.clave("elevenlabs")},
                              json={"text": texto, "model_id": c.get("modelo", "eleven_multilingual_v2"),
                                    "voice_settings": {"stability": c.get("stability", 0.45), "similarity_boost": c.get("similarity", 0.8),
                                                       "style": c.get("style", 0.3), "use_speaker_boost": True}})
            r.raise_for_status()
            destino.write_bytes(r.content)
        elif prov == "openai":
            if not self.clave("openai"):
                raise RuntimeError("OpenAI: falta la clave (Ajustes → Claves).")
            r = requests.post("https://api.openai.com/v1/audio/speech", timeout=40,
                              headers={"Authorization": f"Bearer {self.clave('openai')}"},
                              json={"model": c.get("modelo", "gpt-4o-mini-tts"), "voice": voz, "input": texto,
                                    "instructions": c.get("instrucciones", ""), "response_format": "mp3"})
            r.raise_for_status()
            destino.write_bytes(r.content)
        elif prov == "edge":
            import edge_tts
            asyncio.run(edge_tts.Communicate(texto, voz, rate=f"{int(c.get('rate', 0)):+d}%",
                                             pitch=f"{int(c.get('pitch', 0)):+d}Hz").save(str(destino)))
        else:
            raise ValueError(f"Proveedor de voz desconocido: {prov}")

    # --- ffmpeg -------------------------------------------------------------------------
    def _ff(self, args):
        exe = paths.ffmpeg()
        if not exe:
            raise RuntimeError("No encuentro ffmpeg (ponlo en la carpeta 'herramientas' junto al programa).")
        r = subprocess.run([exe, "-y", "-hide_banner", "-loglevel", "error", *args], capture_output=True, text=True, **paths.sin_ventana())
        if r.returncode:
            raise RuntimeError("ffmpeg: " + r.stderr[-300:])

    def duracion(self, archivo):
        r = subprocess.run([paths.ffmpeg(), "-hide_banner", "-i", str(archivo)], capture_output=True, text=True, **paths.sin_ventana())
        m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
        return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0.0

    def _masterizar(self, crudo, salida, cama=None, cama_vol=0.25):
        a = self.cfg["audio"]
        ini, fin = int(a["pad_ini_ms"]), int(a["pad_fin_ms"])
        pre = ["highpass=f=70"] if a["procesar"] else []
        if a["procesar"] and a["compresor"]:
            pre.append("acompressor=threshold=-20dB:ratio=3:attack=5:release=60")
        if ini:
            pre.append(f"adelay={ini}:all=1")
        post = [f"loudnorm=I={a['loudness']}:TP=-1.5:LRA=8"] if a["procesar"] else []
        if cama and Path(cama).exists():
            d = self.duracion(crudo) + ini / 1000 + 1.0
            pre.append("apad=pad_dur=1.0")
            fc = (f"[0:a]{','.join(pre) or 'anull'}[v];[1:a]volume={cama_vol},afade=t=in:d=0.4[b];"
                  f"[v][b]amix=inputs=2:duration=first:dropout_transition=0,afade=t=out:st={max(d - 0.9, 0):.2f}:d=0.9"
                  + ("," + ",".join(post) if post else "") + "[o]")
            self._ff(["-i", str(crudo), "-stream_loop", "-1", "-i", str(cama), "-filter_complex", fc, "-map", "[o]",
                      "-ar", "44100", "-ac", "2", "-b:a", "192k", str(salida)])
            return
        if fin:
            post.append(f"apad=pad_dur={fin / 1000}")
        af = ",".join(pre + post)
        self._ff(["-i", str(crudo), *(["-af", af] if af else []), "-ar", "44100", "-ac", "2", "-b:a", "192k", str(salida)])

    def sintetizar(self, texto, rol="locutor", cache=False, cama=None, cama_vol=0.25):
        texto = self._pron(texto)
        prov = self.cfg["tts"]["proveedor"]
        clave = f"{prov}|{rol}|{texto}|{cama}|{cama_vol}|{self.cfg['audio']}|{self.cfg['tts'][prov]}"
        h = hashlib.sha1(clave.encode()).hexdigest()[:12]
        if cache:
            salida = self.carpeta("spots") / f"spot_{h}.mp3"
            if salida.exists():
                return salida
        else:
            salida = self.carpeta("voces") / f"voz_{datetime.now():%Y%m%d_%H%M%S}_{h[:6]}.mp3"
        crudo = salida.with_suffix(".raw.mp3")
        try:
            self._tts(texto, rol, crudo)
            self._masterizar(crudo, salida, cama, cama_vol)
        finally:
            crudo.unlink(missing_ok=True)
        return salida

    def limpiar_viejos(self):
        lim = time.time() - float(self.cfg["sistema"]["horas_audio"]) * 3600
        for f in self.carpeta("voces").glob("voz_*.mp3"):
            if f.stat().st_mtime < lim:
                f.unlink(missing_ok=True)

    # --- listas de voces para la interfaz ------------------------------------------------
    def voces_edge(self):
        import edge_tts
        vs = asyncio.run(edge_tts.list_voices())
        return [{"id": v["ShortName"], "nombre": f"{v['ShortName']} ({v['Gender']})"} for v in vs if v["Locale"].startswith("es-")]

    def voces_eleven(self):
        r = requests.get("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": self.clave("elevenlabs")}, timeout=15)
        r.raise_for_status()
        return [{"id": v["voice_id"], "nombre": v["name"]} for v in r.json().get("voices", [])]

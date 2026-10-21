"""RadioBOSS simulado (misma API HTTP) para probar Locutor IA SIN tener RadioBOSS.
Uso:  python herramientas/radioboss_simulado.py   (puerto 9001, contraseña vacía)
En Locutor IA deja los ajustes de RadioBOSS por defecto y pulsa «Iniciar»."""
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse
from xml.sax.saxutils import quoteattr

DUR = int(sys.argv[2]) if len(sys.argv) > 2 else 70
CANCIONES = [("Artista Uno", "Primera canción"), ("Artista Dos", "Segunda canción"), ("Artista Tres", "Tercera canción"),
             ("Artista Cuatro", "Cuarta canción"), ("Artista Cinco", "Quinta canción"), ("Artista Seis", "Sexta canción")] * 4
pl = [dict(fn=f"C:\\Musica\\{a} - {t}.mp3", a=a, t=t, dur=DUR) for a, t in CANCIONES]
st = {"i": 0, "t": time.time()}


def avanzar():
    while True:
        time.sleep(0.3)
        if time.time() - st["t"] >= pl[st["i"]]["dur"] and st["i"] + 1 < len(pl):
            st["i"] += 1
            st["t"] = time.time()
            print("▶ suena:", pl[st["i"]]["fn"])


def trk(t):
    d = t["dur"]
    return (f'<TRACK ARTIST={quoteattr(t.get("a", ""))} TITLE={quoteattr(t.get("t", ""))} FILENAME={quoteattr(t["fn"])} DURATION="{d // 60:02d}:{d % 60:02d}"/>')


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
        i = st["i"]
        if q.get("action") == "playbackinfo":
            nx = trk(pl[i + 1]) if i + 1 < len(pl) else ""
            body = (f'<?xml version="1.0" encoding="utf-8"?><Info><CurrentTrack>{trk(pl[i])}</CurrentTrack>'
                    f'<Playback pos="{int(time.time() - st["t"])}" len="{pl[i]["dur"]}" state="play"/><NextTrack>{nx}</NextTrack></Info>')
        elif q.get("action") == "status":
            body = '<?xml version="1.0" encoding="utf-8"?><Info><Player version="SIMULADO 1.0"/></Info>'
        elif q.get("action") == "inserttrack":
            pos = int(q.get("pos", -2))
            at = i + 1 if pos in (-2, -3) else len(pl)
            pl.insert(at, dict(fn=q["filename"], dur=8, a="", t=""))
            print("  ➕ insertado:", q["filename"].replace("\\", "/").split("/")[-1])
            body = "OK"
        else:
            body = "ERROR"
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))


if __name__ == "__main__":
    puerto = int(sys.argv[1]) if len(sys.argv) > 1 else 9001
    threading.Thread(target=avanzar, daemon=True).start()
    print(f"RadioBOSS simulado en puerto {puerto}. Canciones de {DUR}s. Ctrl+C para salir.")
    HTTPServer(("127.0.0.1", puerto), H).serve_forever()

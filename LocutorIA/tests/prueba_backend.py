"""Pruebas del backend (sin red, sin RadioBOSS real). Ejecutar:  python tests/prueba_backend.py"""
import json, logging, os, stat, subprocess, sys, tempfile, time
from datetime import datetime
from pathlib import Path
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
TMP = Path(tempfile.mkdtemp(prefix="locutor_be_"))
os.environ["LOCUTOR_DATA"] = str(TMP / "datos")
logging.disable(logging.CRITICAL)

# yt-dlp falso en el PATH
fake = TMP / "bin"; fake.mkdir()
(fake / "yt-dlp").write_text('''#!/usr/bin/env python3
import sys, json, subprocess
a = sys.argv[1:]
if "--version" in a: print("2099.01.01"); sys.exit(0)
if "--simulate" in a: sys.exit(0)
if a and a[0].startswith("ytsearch"):
    for i in range(2): print(json.dumps({"id": f"id{i}", "title": f"Canción {i}", "channel": "Canal", "duration": 200 + i, "url": f"https://www.youtube.com/watch?v=id{i}"}))
else:
    out = a[a.index("-o") + 1].replace("%(title)s", "Canción ñandú").replace("%(ext)s", "mp3")
    for p in (10, 55, 100): print(f"[dl] {p}.0%", flush=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=duration=1", out], check=True)
    if "--print-to-file" in a:
        open(a[a.index("--print-to-file") + 2], "w", encoding="utf-8").write(out + "\\n")
    # sin imprimir la ruta por stdout: se debe usar el archivo de --print-to-file
''')
(fake / "yt-dlp").chmod(0o755)
os.environ["PATH"] = str(fake) + os.pathsep + os.environ["PATH"]

from locutor import voice
def fake_tts(self, texto, rol, destino):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=300:duration=2", "-q:a", "5", str(destino)], check=True)
voice.Voz._tts = fake_tts
from locutor.app import construir
from locutor.engine import hora_hablada

ok_n, fallos = 0, []
def chequear(nombre, cond, detalle=""):
    global ok_n
    if cond: ok_n += 1; print("  ✓", nombre)
    else: fallos.append(nombre); print("  ✗", nombre, detalle)

ctx, app = construir(); c = app.test_client(); H = {"X-Locutor": "1"}
motor, aj, com, db, voz = ctx["motor"], ctx["aj"], ctx["com"], ctx["db"], ctx["voz"]

print("Seguridad y ajustes")
chequear("POST sin cabecera X-Locutor → 403", c.post("/api/motor/detener").status_code == 403)
chequear("GET ajustes funciona", c.get("/api/ajustes").status_code == 200)
c.patch("/api/ajustes", json={"cambios": {"claves.anthropic": "sk-secreta-1234", "estacion.nombre": "Radio Prueba", "tandas.minutos": [10, 40]}}, headers=H)
j = c.get("/api/ajustes").json
chequear("la clave NO se devuelve a la interfaz", j["claves"]["anthropic"] == "" and j["claves_guardadas"]["anthropic"] is True)
chequear("cambio anidado guardado", j["estacion"]["nombre"] == "Radio Prueba" and j["tandas"]["minutos"] == [10, 40])
c.patch("/api/ajustes", json={"cambios": {"claves.anthropic": ""}}, headers=H)
chequear("clave vacía no borra la guardada", aj.datos["claves"]["anthropic"] == "sk-secreta-1234")
aj.datos["claves"]["anthropic"] = ""
chequear("audio: extensión no permitida → 404", c.get("/api/audio?f=/etc/passwd").status_code == 404)

print("Hora hablada y perfiles")
chequear("15:45 → las 4 menos cuarto", hora_hablada(datetime(2026, 1, 1, 15, 45)).startswith("las 4 menos cuarto de la tarde"))
chequear("00:05 → las 12 y 5 madrugada", hora_hablada(datetime(2026, 1, 1, 0, 5)) == "las 12 y 5 de la madrugada")
for hh, esperado in ((23, "Madrugada"), (2, "Madrugada"), (12, "Tarde"), (7, "Mañanero"), (20, "Noche")):
    chequear(f"perfil a las {hh}h = {esperado}", motor.perfil_en(datetime(2026, 1, 1, hh, 30))["nombre"] == esperado)
chequear("fecha especial 15 sep", "Independencia" in (motor.fecha_especial(datetime(2026, 9, 15)) or ""))
chequear("sin fecha especial el 3 mar", motor.fecha_especial(datetime(2026, 3, 3)) is None)

print("Comerciales: vigencia, días, horas, límites, categorías")
ahora = datetime.now(); dia_hoy = ahora.weekday()
sin_hoy = [1] * 7; sin_hoy[dia_hoy] = 0
base = {"modo": "texto", "texto": "Texto de prueba del comercial.", "uso": "tanda", "peso": 1, "activo": True}
ids = {}
def nuevo(nombre, **kw): ids[nombre] = c.post("/api/comerciales", json={**base, "nombre": nombre, **kw}, headers=H).json["id"]
nuevo("A", categoria="comida"); nuevo("B", categoria="comida"); nuevo("C", categoria="autos"); nuevo("Dia_excluido", dias=sin_hoy)
nuevo("Fuera_de_hora", hora_desde="00:00", hora_hasta="00:01") if ahora.strftime("%H:%M") > "00:01" else None
nuevo("Vencido", hasta="2020-01-01"); nuevo("Futuro", desde="2999-01-01"); nuevo("Inactivo", activo=False); nuevo("Solo_mencion", uso="mencion")
nuevo("Limite", max_por_dia=1); db.registrar("comercial", "Limite", "", "x", "emitido")
motor.cfg["tandas"]["cantidad"] = 10
elegidos = {x[0]["nombre"] for x in motor.elegir_spots(ahora)}
chequear("incluye C (autos) y solo UNA de comida (A o B)", "C" in elegidos and len(elegidos & {"A", "B"}) == 1, elegidos)
for malo in ("Dia_excluido", "Fuera_de_hora", "Vencido", "Futuro", "Inactivo", "Solo_mencion", "Limite"):
    if malo in ids: chequear(f"excluye {malo}", malo not in elegidos, elegidos)
chequear("la mención sí está disponible como patrocinador", (motor.patrocinador(ahora) or {}).get("nombre") == "Solo_mencion")

print("Audio: cama musical y caché")
cama = TMP / "cama.mp3"; subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=110:duration=10", str(cama)], check=True)
r1 = voz.sintetizar("Hola con cama musical", "comercial", cache=True, cama=str(cama), cama_vol=0.2)
chequear("mezcla con cama genera mp3", r1.exists() and r1.stat().st_size > 1000)
d = voz.duracion(r1); chequear(f"duración razonable ({d:.1f}s: voz 2s + colchón)", 2.5 < d < 6)
r2 = voz.sintetizar("Hola con cama musical", "comercial", cache=True, cama=str(cama), cama_vol=0.2)
chequear("segunda vez usa caché (mismo archivo)", r1 == r2)
r3 = voz.sintetizar("Prueba sin procesar", "locutor")
chequear("síntesis normal genera archivo", r3.exists() and voz.duracion(r3) > 2)
aj.datos["pronunciacion"] = [{"palabra": "Bad Bunny", "como": "bad buni"}]
chequear("diccionario de pronunciación", voz._pron("Suena Bad Bunny hoy") == "Suena bad buni hoy")

print("Guion de respaldo (sin IA)")
cer = ctx["cerebro"]
sal = {"sig": "Tema (artista: X)", "ant": "Otro", "hora": "las 3", "saludo": "buenas tardes", "dia": "lunes", "estilo": ""}
t, origen = cer.guion("saludo", "x", sal, "NOTA INTERNA", [{"de": "Ana", "para": "Luis", "mensaje": "feliz día"}])
chequear("banco de frases para saludos: natural, sin notas internas", "Ana" in t and "feliz día" in t and "NOTA INTERNA" not in t and "conserva" not in t.lower(), t)
chequear("sin IA → origen frases", origen == "frases")

print("Saludos y comandos")
c.post("/api/decir", json={"mensaje": "saluda a Carlos"}, headers=H)
s = c.get("/api/saludos").json
chequear("orden creada con prioridad 'ya'", s and s[-1]["tipo"] == "orden" and s[-1]["prioridad"] == "ya")
sid = s[-1]["id"]; c.patch(f"/api/saludos/{sid}", json={"estado": "leido"}, headers=H)
chequear("PATCH parcial actualiza solo ese campo", c.get("/api/saludos").json[-1]["estado"] == "leido" and c.get("/api/saludos").json[-1]["mensaje"] == "saluda a Carlos")
c.delete(f"/api/saludos/{sid}", headers=H); chequear("DELETE elimina", not c.get("/api/saludos").json)

print("YouTube (yt-dlp simulado)")
r = c.get("/api/yt/buscar?q=algo").json
chequear("búsqueda devuelve 2 resultados con duración", len(r) == 2 and r[1]["dur"] == 201)
aj.datos["carpetas"]["youtube"] = str(TMP / "yt")
jid = c.post("/api/yt/descargar", json={"url": "https://youtu.be/x", "titulo": "t", "destino": "biblioteca"}, headers=H).json["id"]
for _ in range(40):
    job = [j for j in c.get("/api/yt/estado").json["trabajos"] if j["id"] == jid][0]
    if job["estado"] in ("listo", "error"): break
    time.sleep(0.25)
chequear("descarga termina 'listo' con archivo mp3", job["estado"] == "listo" and Path(job["ruta"]).exists(), job)

print("Reportes, respaldo y diagnóstico")
i = db.registrar("comercial", "Cliente X", "t", "a.mp3", "insertado"); db.emitido(i)
db.registrar("comercial", "Cliente X", "t", "a.mp3", "insertado")
hoy = datetime.now().strftime("%Y-%m-%d")
rep = {x["nombre"]: x for x in c.get(f"/api/reporte?desde={hoy}&hasta={hoy}").json}
chequear("reporte: 2 insertados, 1 emitido", rep["Cliente X"]["insertados"] == 2 and rep["Cliente X"]["emitidos"] == 1, rep)
csv = c.get(f"/api/reporte.csv?desde={hoy}&hasta={hoy}").data.decode("utf-8")
chequear("CSV con BOM, cabecera y filas", csv.startswith("\ufeff") and "Cliente X" in csv and "Comercial" in csv)
aj.datos["claves"]["anthropic"] = "sk-secreta-9999"
resp = c.get("/api/exportar"); datos = json.loads(resp.data)
c.patch("/api/ajustes", json={"cambios": {"estacion.nombre": "CAMBIADO"}}, headers=H)
c.post("/api/importar", json=datos, headers=H)
chequear("importar restaura el respaldo", aj.datos["estacion"]["nombre"] == "Radio Prueba" and len(com.lista()) >= 5)
chequear("el respaldo NO incluye claves reales", "sk-secreta" not in resp.data.decode())
chequear("al importar se conservan las claves de este PC", aj.datos["claves"]["anthropic"] == "sk-secreta-9999")
dg = c.get("/api/diagnostico").json
chequear("diagnóstico lista ffmpeg, RadioBOSS, Claude, carpetas", len(dg) >= 5 and any(x["nombre"].startswith("ffmpeg") and x["ok"] for x in dg))
motor.cfg["tandas"]["minutos"] = []
chequear("sin minutos de tanda → nunca 'vencida' (bug corregido)", not motor._tanda_vencida(datetime.now()))


print("IA gratis: cadena con respaldo (servidores falsos)")
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
llamadas = {}
class FakeLLM(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps({"data": [{"id": "whisper-large-v3"}, {"id": "llama-guard-4"}, {"id": "modelo-nuevo"}]}).encode())
    def do_POST(self):
        cuerpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        m = cuerpo["model"]; llamadas[m] = llamadas.get(m, 0) + 1
        if m == "retirado":
            self.send_response(404); self.end_headers(); self.wfile.write(json.dumps({"error": {"message": "The model retirado does not exist or you do not have access to it."}}).encode()); return
        if m == "limitado": self.send_response(429); self.send_header("retry-after", "120"); self.end_headers(); self.wfile.write(b"{}"); return
        if m == "malo": self.send_response(401); self.end_headers(); self.wfile.write(b"{}"); return
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps({"choices": [{"message": {"content": "  ¡Hola! 🎵 Esto es **la IA falsa**.  "}}]}).encode())
servers = []
for puerto in (1234, 11434):
    try:
        sv = HTTPServer(("127.0.0.1", puerto), FakeLLM); threading.Thread(target=sv.serve_forever, daemon=True).start(); servers.append(sv)
    except OSError: pass
cer = ctx["cerebro"]
motor.cfg["llm"]["base_url"] = "http://127.0.0.1:1234/v1"
aj.datos["claves"]["personalizado"] = "k-falsa"
aj.datos["llm"]["cadena"] = [{"proveedor": "personalizado", "modelo": "limitado"}, {"proveedor": "personalizado", "modelo": "malo"}, {"proveedor": "ollama", "modelo": "bueno"}]
chequear("hay IA configurada", cer.hay_ia())
sal = {"sig": "Tema (artista: X)", "ant": "Otro (artista: Y)", "hora": "las 3 de la tarde", "saludo": "buenas tardes", "dia": "lunes", "estilo": "", "clima": None}
t, origen = cer.guion("transicion", "x", sal)
chequear("pasa del límite (429) y de la clave mala (401) a la tercera IA", origen == "ollama/bueno", origen)
chequear("limpia emojis y markdown de la respuesta", t == "¡Hola! Esto es la IA falsa.", t)
t, origen = cer.guion("transicion", "x", sal)
chequear("la IA en pausa por límite NO se vuelve a llamar", llamadas.get("limitado") == 1 and llamadas.get("malo") == 1 and llamadas.get("bueno") == 2, llamadas)
r = cer.probar()
chequear("probar() informa cada eslabón (429 = clave válida, 401 = rechazada, bueno = ok)", [x["ok"] for x in r] == [False, False, True] and "válida" in r[0]["mensaje"] and "rechazada" in r[1]["mensaje"], r)
aj.datos["llm"]["cadena"] = [{"proveedor": "groq", "modelo": "llama-3.3-70b-versatile"}]
chequear("sin clave de Groq: no hay IA (se usa el banco de frases)", not cer.hay_ia())
t, origen = cer.guion("transicion", "x", sal)
chequear("sin IA el origen es 'frases'", origen == "frases" and "Tema" in t, (t, origen))
try: cer.escribir_spot("X", "brief"); chequear("escribir_spot sin IA lanza error claro", False)
except RuntimeError as e: chequear("escribir_spot sin IA lanza error claro", "IA gratis" in str(e))

print("IA: modelo retirado (404) → se sustituye solo, y mensajes reales")
aj.datos["llm"]["cadena"] = [{"proveedor": "personalizado", "modelo": "retirado"}]
cer.enfriar.clear(); cer.alias.clear(); cer._modelos.clear()
chequear("la lista de modelos excluye whisper y guard", cer.modelos("personalizado", True) == ["modelo-nuevo"], cer.modelos("personalizado"))
t, origen = cer.guion("transicion", "x", sal)
chequear("modelo retirado → usa el disponible automáticamente", origen == "personalizado/modelo-nuevo", origen)
chequear("recuerda la sustitución (no vuelve a fallar)", cer.alias.get(("personalizado", "retirado")) == "modelo-nuevo")
cer.alias.clear()
r = cer.probar()
chequear("probar() explica la sustitución", r[0]["ok"] and "ya no existe" in r[0]["mensaje"] and "modelo-nuevo" in r[0]["mensaje"], r)
# migración de ajustes guardados con modelos Llama de Groq (retirados 16-ago-2026)
aj.datos["llm"]["cadena"] = [{"proveedor": "groq", "modelo": "llama-3.3-70b-versatile"}, {"proveedor": "groq", "modelo": "llama-3.1-8b-instant"}]
aj.guardar()
ctx2, _ = construir()
chequear("al abrir, los modelos Llama retirados se migran a gpt-oss", [e["modelo"] for e in ctx2["aj"].datos["llm"]["cadena"]] == ["openai/gpt-oss-120b", "openai/gpt-oss-20b"])
# parámetros enviados a Groq para gpt-oss
import requests as _rq
enviado = {}
class _R:
    status_code = 200; headers = {}; text = ""
    def json(self): return {"choices": [{"message": {"content": "ok"}}]}
    def raise_for_status(self): pass
_orig = _rq.post
_rq.post = lambda url, **kw: (enviado.update(url=url, **kw["json"]), _R())[1]
aj.datos["claves"]["groq"] = "gsk_falsa"
cer._una("groq", "openai/gpt-oss-120b", "sys", "usr", 300)
_rq.post = _orig; aj.datos["claves"]["groq"] = ""
chequear("Groq gpt-oss: URL correcta, reasoning_effort=low y tokens suficientes", enviado["url"] == "https://api.groq.com/openai/v1/chat/completions" and enviado["reasoning_effort"] == "low" and enviado["max_tokens"] >= 1000, enviado)
aj.datos["llm"]["cadena"] = [{"proveedor": "personalizado", "modelo": "malo"}]
cer.enfriar.clear()
try: cer._generar("s", "u"); chequear("error 401 explicado", False)
except RuntimeError as e: chequear("error 401 explicado (clave rechazada)", "clave rechazada" in str(e), str(e))

for sv in servers: sv.shutdown()

print("Banco de frases (sin IA, sin internet)")
cer.recientes.clear()
sal = {"sig": "Vivir Mi Vida (artista: Marc Anthony)", "ant": "Tití Me Preguntó (artista: Bad Bunny)", "hora": "la una y 15 de la tarde", "saludo": "buenas tardes", "dia": "martes", "estilo": "", "clima": "29 grados, despejado", "noticias": ["Titular de prueba"], "patrocinador": "Taller El Rayo. Datos: x"}
todo_ok, vistos = True, []
for tipo in ("transicion", "hora_clima", "id_estacion", "interaccion", "noticias", "mencion", "pre_tanda", "post_tanda"):
    for _ in range(6):
        f = cer._plantilla(tipo, sal)
        if "{" in f or "}" in f or not f.strip(): todo_ok = False; print("   mal:", tipo, f)
        if tipo == "transicion": vistos.append(f)
chequear("todos los tipos generan texto sin llaves sobrantes", todo_ok)
chequear("transición: 6 seguidas sin repetir frase", len(set(vistos)) == 6, vistos)
hs = {cer._plantilla("hora_clima", sal) for _ in range(30)}
chequear("«la una» → usa 'Es/Va' (gramática)", any(x.startswith(("Es la una", "Va la una")) for x in hs) and not any(x.startswith(("Son la una", "Van la una")) for x in hs), hs)
sal2 = {**sal, "clima": None}; cer.recientes.clear()
chequear("sin clima se saltan las frases que lo usan", all("grados" not in cer._plantilla("hora_clima", sal2) for _ in range(20)))
sal3 = {**sal, "sig": None}
chequear("post_tanda sin canción siguiente usa frases sin {sig}", all("{" not in cer._plantilla("post_tanda", sal3) for _ in range(20)))
chequear("el locutor dice 'Tití Me Preguntó de Bad Bunny' (artista incluido)", any("Bad Bunny" in cer._plantilla("transicion", {**sal, "sig": "Tití Me Preguntó (artista: Bad Bunny)"}) for _ in range(12)))

print("YouTube: ruta desde --print-to-file, tildes y diagnóstico")
from locutor import extras
jid = c.post("/api/yt/descargar", json={"url": "https://youtu.be/x", "titulo": "t", "destino": "biblioteca"}, headers=H).json["id"]
for _ in range(40):
    job = [j for j in c.get("/api/yt/estado").json["trabajos"] if j["id"] == jid][0]
    if job["estado"] in ("listo", "error"): break
    time.sleep(0.25)
chequear("ruta con ñ obtenida por --print-to-file (sin imprimirla)", job["estado"] == "listo" and "ñandú" in job["ruta"] and Path(job["ruta"]).exists(), job)
dg = c.get("/api/yt/probar").json
chequear("probar YouTube: yt-dlp con versión y extracción OK", dg[0]["ok"] and "2099" in dg[0]["detalle"] and any(x["nombre"].startswith("Extracción") and x["ok"] for x in dg), dg)
chequear("probar YouTube avisa que falta Deno", any("Deno" in x["nombre"] and not x["ok"] for x in dg))
chequear("pista: bot → cookies", "cookies" in extras.pista("ERROR: Sign in to confirm you’re not a bot").lower())
chequear("pista: JS runtime → Deno", "Deno" in extras.pista("WARNING: No supported JavaScript runtime could be found"))
chequear("pista: 403", "403" in extras.pista("HTTP Error 403: Forbidden"))

print(f"\n{ok_n} comprobaciones correctas, {len(fallos)} fallos")
if fallos: print("FALLOS:", fallos); sys.exit(1)

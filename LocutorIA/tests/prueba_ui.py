"""Prueba de punta a punta: app real + RadioBOSS simulado + voz de relleno + navegador (Playwright)."""
import os, subprocess, sys, tempfile, threading, time, json
from pathlib import Path
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
TMP = tempfile.mkdtemp(prefix="locutor_test_")
os.environ["LOCUTOR_DATA"] = TMP
SHOTS = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/shots"); SHOTS.mkdir(exist_ok=True, parents=True)

subprocess.run(['pkill', '-f', '[r]adioboss_simulado'])
time.sleep(0.5)
# --- RadioBOSS simulado en proceso aparte (canciones de 40 s)
rb = subprocess.Popen([sys.executable, str(RAIZ / "herramientas/radioboss_simulado.py"), "19001", "30"], stdout=open(TMP + "/rb.log", "w"), stderr=subprocess.STDOUT)
time.sleep(1)

import logging; logging.getLogger('werkzeug').setLevel(logging.ERROR)
from locutor import voice
from locutor.app import construir, servir
def fake_tts(self, texto, rol, destino):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=330:duration=1.2", "-q:a", "5", str(destino)], check=True)
voice.Voz._tts = fake_tts

ctx, app = construir()
aj = ctx["aj"]
aj.datos["radioboss"].update(puerto=19001, intervalo_seg=0.5, anticipacion_seg=6, min_cancion_seg=5)
aj.datos["perfiles"] = [{"nombre": "Todo el día", "desde": "00:00", "hasta": "23:59", "estilo": "Natural", "cada_min": 1, "cada_max": 1, "habla": True}]
aj.datos["tandas"]["minutos"] = []   # las tandas se fuerzan a mano
aj.guardar()
servir(app, 18765)

from playwright.sync_api import sync_playwright
errores = []
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1340, "height": 860})
    pg.on("pageerror", lambda e: errores.append("pageerror: " + str(e)))
    pg.on("console", lambda m: errores.append("console: " + m.text) if m.type == "error" else None)
    pg.goto("http://127.0.0.1:18765/"); pg.wait_for_selector(".nav")
    time.sleep(1.5)
    pg.screenshot(path=SHOTS / "01_panel_detenido.png")

    # --- crear comercial desde la interfaz
    pg.click("text=Comerciales"); pg.wait_for_selector("text=Tandas")
    pg.click("text=＋ Añadir"); time.sleep(0.4)
    pg.fill(".form-item input[type=text] >> nth=0", "Pupusería Doña Rosa")
    pg.locator(".form-item textarea").first.fill("Antojo de pupusas? En Pupusería Doña Rosa las hacemos al momento. Te esperamos todos los días.")
    pg.locator(".form-item input[type=number]").first.fill("2"); pg.locator(".form-item input[type=number]").first.dispatch_event("change")
    time.sleep(0.6)
    pg.screenshot(path=SHOTS / "02_comerciales.png")
    pg.click("text=＋ Añadir"); time.sleep(0.3)
    pg.fill(".form-item input[type=text] >> nth=0", "Taller El Rayo")
    pg.locator(".form-item textarea").first.fill("Cambio de aceite y frenos en Taller El Rayo, de lunes a sábado.")
    time.sleep(0.6)
    pg.click("text=▶ Escuchar"); time.sleep(1.5)
    # --- saludo
    pg.click("text=Saludos"); pg.wait_for_selector("text=Nuevo saludo")
    pg.fill("input[placeholder='Familia Pérez']", "Familia Pérez"); pg.fill("input[placeholder='Doña Rosa']", "Carlos")
    pg.fill("textarea[placeholder^='Ej.: feliz']", "feliz cumpleaños, que la pase lindo")
    pg.click("text=＋ Añadir a la cola"); time.sleep(0.8)
    pg.screenshot(path=SHOTS / "03_saludos.png")
    # --- recorrer páginas de ajustes
    for nombre, esp in [("Locutor", "Identidad del locutor"), ("Voz", "Probar la voz"), ("YouTube", "Buscar"), ("Historial y reportes", "Reporte de comerciales"), ("Ajustes", "Conexión con RadioBOSS"), ("Ayuda", "Puesta en marcha")]:
        pg.click(f".nav >> text={nombre}"); pg.wait_for_selector(f"text={esp}"); time.sleep(0.4)
        pg.screenshot(path=SHOTS / f"04_{nombre.split()[0].lower()}.png")
    pg.click(".nav >> text=Locutor"); pg.click("text=Tipos de intervención"); time.sleep(0.4); pg.screenshot(path=SHOTS / "05_tipos.png")
    pg.click("text=Horarios y perfiles"); time.sleep(0.4); pg.screenshot(path=SHOTS / "06_horarios.png")
    pg.click("text=Probar >> nth=-1"); pg.click("text=Generar guion"); time.sleep(1.2); pg.click("text=▶ Escuchar con la voz"); time.sleep(1.5)
    pg.screenshot(path=SHOTS / "07_probar.png")
    # --- ajustes: probar conexión
    pg.click(".nav >> text=Ajustes"); pg.click("text=Probar conexión"); time.sleep(1.2)
    print("PROBAR RB:", pg.inner_text("text=/RadioBOSS SIMULADO|No se pudo/"))
    pg.screenshot(path=SHOTS / "08_ajustes_rb.png")
    # --- poner EN VIVO y arrancar el locutor
    pg.click("text=Sistema y respaldo"); pg.click("text=MODO ENSAYO >> xpath=../.. >> .slider"); time.sleep(0.8)
    pg.click(".nav >> text=Panel"); time.sleep(0.5); pg.click("text=▶ Iniciar locutor IA")
    print("emitiendo…")
    m = ctx["motor"]
    def esperar(cond, seg, que):
        t0 = time.time()
        while time.time() - t0 < seg:
            if cond(): return True
            time.sleep(0.5)
        print("TIMEOUT esperando:", que); return False
    insertados = lambda: sum(1 for x in m.logs if x["nivel"] == "ok" and x["msg"].startswith("Insertado"))
    esperar(lambda: insertados() >= 1, 70, "1ª inserción (saludo)")
    pg.click("text=Tanda comercial ahora")
    esperar(lambda: insertados() >= 2, 70, "2ª inserción (tanda)")
    esperar(lambda: m.snapshot()["hoy"]["spots_emitidos"] >= 2, 60, "emisión confirmada")
    time.sleep(1.5)
    pg.screenshot(path=SHOTS / "09_panel_vivo.png")
    pg.click(".nav >> text=Historial y reportes"); time.sleep(1.2); pg.screenshot(path=SHOTS / "10_historial.png")
    b.close()

rb.terminate()
print("\n--- LOG DEL RADIOBOSS SIMULADO ---"); print(open(TMP + "/rb.log").read())
print("--- ERRORES DEL NAVEGADOR ---", errores or "ninguno")
print("--- ESTADO FINAL ---"); print(json.dumps({k: ctx["motor"].snapshot()[k] for k in ("corriendo", "conectado", "hoy")}))
print("--- LOGS MOTOR ---")
for x in list(ctx["motor"].logs): print(x["ts"], x["nivel"], x["msg"])
print("--- SALUDOS ---", [(s["para"], s["estado"]) for s in ctx["sal"].lista()])
print("DATA:", TMP)

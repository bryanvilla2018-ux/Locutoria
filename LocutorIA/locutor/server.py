"""Servidor local (solo 127.0.0.1) que alimenta la interfaz de la aplicación."""
import csv
import io
import json
import logging
import os
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from flask import Flask, Response, jsonify, request, send_file, send_from_directory

from . import __version__, extras, paths
from .store import AJUSTES, COMERCIAL, SALUDO, mezclar

AUDIO_EXT = {".mp3", ".wav", ".m4a", ".flac", ".ogg"}
log = logging.getLogger("locutor.server")


def crear_app(ctx):
    aj, com, sal, db, motor, voz, cerebro, yt = (ctx[k] for k in ("aj", "com", "sal", "db", "motor", "voz", "cerebro", "yt"))
    static = paths.recursos() / "locutor" / "static"
    app = Flask(__name__, static_folder=None)
    listas = {"comerciales": (com, COMERCIAL), "saludos": (sal, SALUDO)}

    @app.before_request
    def proteger():
        if request.method != "GET" and request.headers.get("X-Locutor") != "1":
            return jsonify(error="solicitud no permitida"), 403

    @app.errorhandler(Exception)
    def error(e):
        log.exception("API")
        codigo = getattr(e, "code", None)
        return jsonify(error=str(e)[:400]), (codigo if isinstance(codigo, int) else 500)

    @app.get("/")
    def index():
        return send_from_directory(static, "index.html")

    @app.get("/<path:f>")
    def archivos(f):
        return send_from_directory(static, f)

    # ------------------------------------------------------------------ estado / registro
    @app.get("/api/estado")
    def estado():
        return jsonify(motor.snapshot())

    @app.get("/api/logs")
    def logs():
        d = int(request.args.get("desde", 0))
        return jsonify([x for x in list(motor.logs) if x["id"] > d])

    # ------------------------------------------------------------------ ajustes
    def publico():
        d = json.loads(json.dumps(aj.datos))
        usadas = {k: bool(v or os.getenv(k.upper() + "_API_KEY")) for k, v in d["claves"].items()}
        d["claves"] = {k: "" for k in d["claves"]}
        d["claves_guardadas"] = usadas
        d["herramientas"] = {"ffmpeg": paths.ffmpeg(), "ytdlp": paths.ytdlp(), "datos": str(paths.data_dir()), "version": __version__}
        return d

    @app.get("/api/ajustes")
    def get_ajustes():
        return jsonify(publico())

    @app.patch("/api/ajustes")
    def patch_ajustes():
        for ruta, valor in request.json["cambios"].items():
            if ruta.startswith("claves.") and not valor:
                continue
            aj.poner(ruta, valor)
        return jsonify(ok=True)

    # ------------------------------------------------------------------ control del motor
    @app.post("/api/motor/<accion>")
    def accion_motor(accion):
        {"iniciar": motor.iniciar, "detener": motor.detener, "pausar": lambda: motor.pausar(True),
         "reanudar": lambda: motor.pausar(False), "tanda": lambda: setattr(motor, "forzar_tanda", True)}[accion]()
        return jsonify(ok=True)

    @app.post("/api/decir")
    def decir():
        s = sal.agregar({**SALUDO, "tipo": "orden", "mensaje": request.json["mensaje"], "prioridad": "ya",
                         "creado": datetime.now().strftime("%Y-%m-%d %H:%M")})
        motor.log("info", "Orden recibida: se dirá en el próximo espacio entre canciones.")
        return jsonify(s)

    # ------------------------------------------------------------------ listas (comerciales, saludos)
    @app.get("/api/<lista>")
    def get_lista(lista):
        if lista not in listas:
            return jsonify(error="no existe"), 404
        return jsonify(listas[lista][0].lista())

    @app.post("/api/<lista>")
    def nuevo_item(lista):
        if lista not in listas:
            return jsonify(error="no existe"), 404
        st, base = listas[lista]
        extra = {"creado": datetime.now().strftime("%Y-%m-%d %H:%M")} if lista == "saludos" else {}
        return jsonify(st.agregar({**base, **extra, **(request.json or {})}))

    @app.patch("/api/<lista>/<id_>")
    def patch_item(lista, id_):
        if lista not in listas:
            return jsonify(error="no existe"), 404
        r = listas[lista][0].parchar(id_, request.json)
        return jsonify(r) if r else (jsonify(error="no existe"), 404)

    @app.delete("/api/<lista>/<id_>")
    def del_item(lista, id_):
        if lista not in listas:
            return jsonify(error="no existe"), 404
        listas[lista][0].borrar(id_)
        return jsonify(ok=True)

    # ------------------------------------------------------------------ audio y pruebas
    def url_audio(ruta):
        return "/api/audio?f=" + requests.utils.quote(str(ruta), safe="")

    @app.get("/api/audio")
    def audio():
        p = Path(request.args["f"])
        if p.suffix.lower() not in AUDIO_EXT or not p.exists():
            return jsonify(error="audio no disponible"), 404
        return send_file(p, conditional=True)

    @app.post("/api/probar/radioboss")
    def probar_rb():
        try:
            rb = motor.rb()
            v = rb.version()
            i = rb.info()
            sonando = f"{i['actual']['artista']} - {i['actual']['titulo']}" if i["actual"] else "nada"
            return jsonify(ok=True, mensaje=f"Conectado a RadioBOSS {v}. Estado: {i['estado']}. Suena: {sonando}.")
        except Exception as e:
            return jsonify(ok=False, mensaje=f"No se pudo conectar: {str(e)[:200]}")

    @app.post("/api/probar/ia")
    def probar_ia():
        return jsonify(resultados=cerebro.probar(), hay_ia=cerebro.hay_ia())

    @app.post("/api/probar/guion")
    def probar_guion():
        texto, origen = motor.generar_prueba(request.json.get("tipo", "transicion"))
        return jsonify(texto=texto, origen=origen)

    @app.post("/api/probar/voz")
    def probar_voz():
        j = request.json
        ruta = voz.sintetizar(j["texto"], j.get("rol", "locutor"))
        return jsonify(url=url_audio(ruta))

    @app.post("/api/comerciales/<id_>/escuchar")
    def escuchar(id_):
        c = com.buscar(id_)
        if c["modo"] == "archivo":
            return jsonify(url=url_audio(c["archivo"]))
        if not c.get("texto"):
            return jsonify(error="Este comercial no tiene texto. Escríbelo o usa «Redactar con IA»."), 400
        return jsonify(url=url_audio(voz.sintetizar(c["texto"], c.get("voz", "comercial"), cache=True,
                                                    cama=c.get("cama") or None, cama_vol=float(c.get("cama_volumen", 0.25)))))

    @app.post("/api/comerciales/<id_>/redactar")
    def redactar(id_):
        c = com.buscar(id_)
        texto = cerebro.escribir_spot(c["nombre"], c.get("brief", ""), c.get("categoria", ""))
        com.parchar(id_, {"texto": texto})
        return jsonify(texto=texto)

    @app.get("/api/voces/<prov>")
    def voces(prov):
        return jsonify(voz.voces_edge() if prov == "edge" else voz.voces_eleven())

    # ------------------------------------------------------------------ YouTube
    @app.get("/api/yt/buscar")
    def yt_buscar():
        return jsonify(yt.buscar(request.args["q"]))

    @app.post("/api/yt/descargar")
    def yt_descargar():
        j = request.json
        return jsonify(id=yt.descargar(j["url"], j.get("titulo"), j.get("destino", "biblioteca")))

    @app.get("/api/yt/estado")
    def yt_estado():
        return jsonify(trabajos=yt.estado(), disponible=yt.disponible())

    @app.get("/api/yt/probar")
    def yt_probar():
        return jsonify(yt.probar())

    @app.post("/api/yt/actualizar")
    def yt_actualizar():
        return jsonify(mensaje=yt.actualizar())

    # ------------------------------------------------------------------ historial y reportes
    @app.get("/api/historial")
    def historial():
        a = request.args
        return jsonify(db.listar(a.get("tipo", ""), a.get("estado", ""), a.get("desde", ""), a.get("hasta", ""), a.get("q", "")))

    @app.get("/api/reporte")
    def reporte():
        hoy = date.today().isoformat()
        a = request.args
        return jsonify(db.reporte(a.get("desde") or hoy, a.get("hasta") or hoy))

    @app.get("/api/reporte.csv")
    def reporte_csv():
        hoy = date.today().isoformat()
        d, h = request.args.get("desde") or hoy, request.args.get("hasta") or hoy
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["Comercial", "Insertado en lista", "Emitido (confirmado)", "Estado"])
        for r in db.detalle(d, h):
            w.writerow([r["nombre"], r["insertado"], r["emitido"] or "", r["estado"]])
        return Response("\ufeff" + out.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename=reporte_comerciales_{d}_{h}.csv"})

    # ------------------------------------------------------------------ diagnóstico, copias, salida
    @app.get("/api/diagnostico")
    def diagnostico():
        res = []
        ff = paths.ffmpeg()
        res.append({"nombre": "ffmpeg (procesa el audio)", "ok": bool(ff), "detalle": ff or "No encontrado: copia ffmpeg.exe a la carpeta «herramientas»."})
        try:
            res.append({"nombre": "RadioBOSS (API)", "ok": True, "detalle": "Versión " + motor.rb().version()})
        except Exception as e:
            res.append({"nombre": "RadioBOSS (API)", "ok": False, "detalle": f"Sin conexión: {str(e)[:120]}. Activa Settings → API en RadioBOSS."})
        r = cerebro.probar()
        ok = any(x["ok"] for x in r)
        res.append({"nombre": "IA para guiones", "ok": ok, "detalle": "; ".join(f"{x['proveedor']}/{x['modelo']}: {x['mensaje']}" for x in r) or "Sin IA configurada: se usa el banco de frases (gratis, sin internet)."})
        prov = aj.datos["tts"]["proveedor"]
        res.append({"nombre": f"Voz ({prov})", "ok": True, "detalle": "Usa «Probar voz» en la pestaña Voz para comprobarla."})
        y = paths.ytdlp()
        res.append({"nombre": "yt-dlp (YouTube)", "ok": yt.disponible(), "detalle": y or ("Disponible como módulo de Python" if yt.disponible() else "No encontrado (opcional).")})
        for k in ("voces", "spots"):
            p = voz.carpeta(k)
            res.append({"nombre": f"Carpeta de {k}", "ok": os.access(p, os.W_OK), "detalle": str(p)})
        return jsonify(res)

    @app.get("/api/exportar")
    def exportar():
        ajustes = {k: v for k, v in aj.datos.items() if k != "claves"}      # las claves nunca salen del PC
        d = {"version": __version__, "ajustes": ajustes, "comerciales": com.lista(), "saludos": sal.lista()}
        return Response(json.dumps(d, ensure_ascii=False, indent=2), mimetype="application/json",
                        headers={"Content-Disposition": "attachment; filename=locutor_ia_respaldo.json"})

    @app.post("/api/importar")
    def importar():
        d = request.json
        nuevo = mezclar(AJUSTES, {k: v for k, v in (d.get("ajustes") or {}).items() if k != "claves"})
        nuevo["claves"] = aj.datos["claves"]                                  # se conservan las claves de este PC
        aj.datos = nuevo
        aj.guardar()
        for st, k in ((com, "comerciales"), (sal, "saludos")):
            st.datos = d.get(k, [])
            st.guardar()
        return jsonify(ok=True)

    @app.post("/api/salir")
    def salir():
        threading.Timer(0.3, lambda: os._exit(0)).start()
        return jsonify(ok=True)

    return app

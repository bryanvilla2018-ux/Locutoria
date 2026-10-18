"""Motor: vigila RadioBOSS y, justo antes de que termine cada canción, inserta lo que toque
(intervención del locutor, saludos, tanda comercial). Si algo falla, no pasa nada al aire."""
import logging
import random
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path

import requests

from . import extras
from .radioboss import RadioBoss, etiqueta

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
logger = logging.getLogger("locutor.motor")


def hora_hablada(dt):
    h, m = dt.hour, dt.minute

    def art(h24):
        h12 = h24 % 12 or 12
        return "la una" if h12 == 1 else f"las {h12}"
    txt = (f"{art(h)} en punto" if m == 0 else f"{art(h)} y cuarto" if m == 15 else f"{art(h)} y media" if m == 30
           else f"{art(h + 1)} menos cuarto" if m == 45 else f"{art(h)} y {m}")
    per = ("del mediodía" if h == 12 else "de la madrugada" if h < 6 else "de la mañana" if h < 12
           else "de la tarde" if h < 19 else "de la noche")
    return f"{txt} {per}"


def saludo(dt):
    return "buenos días" if dt.hour < 12 else "buenas tardes" if dt.hour < 19 else "buenas noches"


def _norm(p):
    return str(p).replace("\\", "/").lower().rstrip("/")


class Motor:
    def __init__(self, aj, com, sal, db, voz, cerebro):
        self.aj, self.com, self.sal, self.db, self.voz, self.cerebro = aj, com, sal, db, voz, cerebro
        self.corriendo = self.pausado = False
        self.conectado, self.error, self.info = False, None, None
        self.gen_id, self.primera, self.ult_fn, self.ult_pos = 0, True, None, 0.0
        self.forzar_tanda, self.plan = False, None
        self.pendientes, self.etiquetas = {}, {}
        self.logs, self._log_id = deque(maxlen=600), 0
        self.desde = 0
        self.objetivo = self._nuevo_objetivo(self.perfil_en(datetime.now()))
        self.ult_marca = self._marca_pasada(datetime.now())

    @property
    def cfg(self):
        return self.aj.datos

    def rb(self):
        return RadioBoss(self.cfg["radioboss"])

    # --- registro -----------------------------------------------------------------------
    def log(self, nivel, msg):
        self._log_id += 1
        self.logs.append({"id": self._log_id, "ts": datetime.now().strftime("%H:%M:%S"), "nivel": nivel, "msg": msg})
        logger.log(logging.WARNING if nivel == "aviso" else logging.INFO, msg)

    # --- control --------------------------------------------------------------------------
    def iniciar(self):
        if self.corriendo:
            return
        self.corriendo, self.pausado, self.primera = True, False, True
        threading.Thread(target=self._bucle, daemon=True).start()
        self.log("info", "Locutor IA iniciado." + (" (MODO ENSAYO: no se inserta nada en RadioBOSS)" if self.cfg["sistema"]["ensayo"] else ""))

    def detener(self):
        if self.corriendo:
            self.log("info", "Locutor IA detenido. RadioBOSS sigue con su programación normal.")
        self.corriendo, self.plan = False, None
        self.gen_id += 1

    def pausar(self, v=True):
        self.pausado = v
        self.log("info", "Locutor IA en pausa (no habla)." if v else "Locutor IA reanudado.")

    def _bucle(self):
        ultima = 0
        while self.corriendo:
            try:
                self.tick()
            except Exception as e:
                self.log("aviso", f"Error interno: {e}")
                logger.exception("tick")
            if time.time() - ultima > 3600:
                try:
                    self.voz.limpiar_viejos()
                    self.db.purgar(int(self.cfg["sistema"]["historial_dias"]))
                except Exception:
                    pass
                ultima = time.time()
            time.sleep(max(float(self.cfg["radioboss"]["intervalo_seg"]), 0.3))

    # --- clasificación -------------------------------------------------------------------------
    def _ignorar(self):
        c = self.cfg["carpetas"]
        return [_norm(p) for p in [*c["ignorar"], self.voz.carpeta("voces"), self.voz.carpeta("spots")] if p]

    def es_musica(self, t):
        if not t or t["dur"] < int(self.cfg["radioboss"]["min_cancion_seg"]):
            return False
        r = _norm(t["archivo"])
        return not any(r.startswith(p + "/") for p in self._ignorar())

    def perfil_en(self, dt):
        t = dt.strftime("%H:%M")
        for p in self.cfg["perfiles"]:
            d, h = p["desde"], p["hasta"]
            if (d <= t < h) if d <= h else (t >= d or t < h):
                return p
        return {"nombre": "General", "estilo": "natural", "cada_min": 2, "cada_max": 4, "habla": True}

    @staticmethod
    def _nuevo_objetivo(perfil):
        a = max(int(perfil["cada_min"]), 1)
        return random.randint(a, max(a, int(perfil["cada_max"])))

    def fecha_especial(self, dt):
        k = dt.strftime("%m-%d")
        return " ".join(f["nota"] for f in self.cfg["fechas"] if f.get("fecha") == k) or None

    # --- tandas por reloj --------------------------------------------------------------------------
    def _marcas(self, base):
        return [base.replace(minute=0, second=0, microsecond=0) + timedelta(hours=h, minutes=int(m))
                for h in range(-1, 2) for m in self.cfg["tandas"]["minutos"]]

    def _marca_pasada(self, ref):
        c = [m for m in self._marcas(ref) if m <= ref]
        return max(c) if c else datetime.min

    def _en_ventana(self, dt):
        t = self.cfg["tandas"]
        return t["hora_desde"] <= dt.strftime("%H:%M") <= t["hora_hasta"]

    def _tanda_vencida(self, ref):
        marca = self._marca_pasada(ref)
        if marca > self.ult_marca:
            self.ult_marca = marca
            return self._en_ventana(marca)
        return False

    def proxima_tanda(self):
        if not self.cfg["tandas"]["activas"]:
            return None
        ahora = datetime.now()
        c = sorted(m for m in self._marcas(ahora) if m > ahora and self._en_ventana(m))
        return c[0].strftime("%H:%M") if c else None

    # --- comerciales ---------------------------------------------------------------------------------
    def vigente(self, c, ref, uso):
        if not c.get("activo", True) or c.get("uso", "tanda") not in (uso, "ambos"):
            return False
        f, t = ref.date().isoformat(), ref.strftime("%H:%M")
        if (c.get("desde") and f < c["desde"]) or (c.get("hasta") and f > c["hasta"]):
            return False
        if not (c.get("dias") or [1] * 7)[ref.weekday()]:
            return False
        if not (c.get("hora_desde", "00:00") <= t <= c.get("hora_hasta", "23:59")):
            return False
        return not (int(c.get("max_por_dia") or 0) and self.db.contar_hoy(c["nombre"]) >= int(c["max_por_dia"]))

    def _audio_spot(self, c):
        try:
            if c.get("modo") == "archivo":
                return Path(c["archivo"]) if c.get("archivo") and Path(c["archivo"]).exists() else None
            texto = (c.get("texto") or "").strip()
            if not texto and c.get("brief"):
                texto = self.cerebro.escribir_spot(c["nombre"], c["brief"], c.get("categoria", ""))
                self.com.parchar(c["id"], {"texto": texto})
                self.log("info", f"Guion redactado por IA para «{c['nombre']}» (revísalo en Comerciales).")
            if not texto:
                return None
            return self.voz.sintetizar(texto, c.get("voz", "comercial"), cache=True, cama=c.get("cama") or None,
                                       cama_vol=float(c.get("cama_volumen", 0.25)))
        except Exception as e:
            self.log("aviso", f"No pude preparar el comercial «{c.get('nombre')}»: {e}")
            return None

    def elegir_spots(self, ref):
        t = self.cfg["tandas"]
        vig = [c for c in self.com.lista() if self.vigente(c, ref, "tanda")]
        vig.sort(key=lambda c: (self.db.contar_hoy(c["nombre"]) / max(float(c.get("peso", 1)), 0.1), random.random()))
        out, cats = [], set()
        for c in vig:
            if len(out) >= int(t["cantidad"]):
                break
            cat = (c.get("categoria") or "").strip().lower()
            if t["separar_categorias"] and cat and cat in cats:
                continue
            ruta = self._audio_spot(c)
            if ruta:
                out.append((c, ruta))
                cats.add(cat)
        return out

    def patrocinador(self, ref):
        vig = [c for c in self.com.lista() if self.vigente(c, ref, "mencion")]
        vig.sort(key=lambda c: (self.db.contar_hoy(c["nombre"] + " (mención)") / max(float(c.get("peso", 1)), 0.1), random.random()))
        return vig[0] if vig else None

    # --- saludos ------------------------------------------------------------------------------------------
    def saludos_pendientes(self, ref):
        hhmm = ref.strftime("%H:%M")
        return [s for s in self.sal.lista() if s.get("estado") == "pendiente" and (not s.get("no_antes") or s["no_antes"] <= hhmm)]

    def _plan_saludos(self, items):
        items = items[: int(self.cfg["locutor"]["max_saludos"])]
        solo_ordenes = all(s.get("tipo") == "orden" for s in items)
        clave = "orden" if solo_ordenes else "saludo"
        return {"clave": clave, "nombre": "Orden del operador" if solo_ordenes else "Saludos de oyentes",
                "instruccion": self.cfg["instrucciones"][clave], "saludos": items}

    @staticmethod
    def _texto_saludos(items):
        out = []
        for s in items:
            out.append(f"INSTRUCCIÓN DEL OPERADOR: {s['mensaje']}" if s.get("tipo") == "orden" else
                       f"Saludo de {s.get('de') or 'un oyente'} para {s.get('para') or 'alguien especial'}: {s['mensaje']} "
                       "(conserva los nombres exactos; no añadas datos)")
        return "\n".join(out)

    # --- decisión ----------------------------------------------------------------------------------------------
    def elegir_plan(self, sig, ref, perfil):
        ensayo = self.cfg["sistema"]["ensayo"]
        if self.forzar_tanda or (self.cfg["tandas"]["activas"] and self._tanda_vencida(ref)):
            self.forzar_tanda, self.desde = False, 0
            return {"clave": "tanda", "nombre": "Tanda comercial"}
        pend = self.saludos_pendientes(ref)
        ya = [s for s in pend if s.get("prioridad") == "ya"]
        if ya and not ensayo:
            return self._plan_saludos(ya)
        if not perfil.get("habla", True):
            return None
        self.desde += 1
        if self.objetivo > max(int(perfil["cada_max"]), 1):      # cambió de horario: ajusta al nuevo ritmo
            self.objetivo = self._nuevo_objetivo(perfil)
        if self.desde < self.objetivo:
            return None
        self.desde, self.objetivo = 0, self._nuevo_objetivo(perfil)
        if pend:
            return self._plan_saludos(pend)
        sig_ok = self.es_musica(sig)
        ops = []
        for tp in self.cfg["tipos"]:
            if not tp.get("activo") or float(tp.get("peso", 0)) <= 0 or (tp.get("necesita_siguiente", True) and not sig_ok):
                continue
            if (tp["id"] == "noticias" and not extras.titulares(self.cfg)) or (tp["id"] == "mencion" and not self.patrocinador(ref)):
                continue
            ops.append(tp)
        if not ops:
            return None
        tp = random.choices(ops, weights=[float(x["peso"]) for x in ops])[0]
        return {"clave": tp["id"], "nombre": tp["nombre"], "instruccion": tp["instruccion"]}

    def contexto(self, act, sig, fin, perfil, plan):
        aire = datetime.fromtimestamp(max(fin, time.time()))
        ctx = {"dia": DIAS[aire.weekday()], "hora": hora_hablada(aire), "saludo": saludo(aire), "clima": extras.clima(self.cfg),
               "ant": etiqueta(act), "sig": etiqueta(sig) if self.es_musica(sig) else None, "estilo": perfil.get("estilo", ""),
               "fecha_especial": self.fecha_especial(aire)}
        if plan.get("clave") == "noticias":
            ctx["noticias"] = extras.titulares(self.cfg)
        if plan.get("clave") == "mencion":
            c = self.patrocinador(aire)
            plan["patrocinador"] = c
            ctx["patrocinador"] = f"{c['nombre']}. Datos: {c.get('texto') or c.get('brief') or ''}" if c else None
        return ctx

    def _voz(self, clave, instruccion, ctx, extra="", saludos=None):
        try:
            texto, origen = self.cerebro.guion(clave, instruccion, ctx, extra, saludos)
            self.log("voz", f"[{clave}] {texto}" + ("" if origen == "claude" else "  (plantilla: sin IA)"))
            return {"tipo": clave, "nombre": clave, "texto": texto, "ruta": self.voz.sintetizar(texto), "reg": True}
        except Exception as e:
            self.log("aviso", f"No pude generar la voz ({clave}): {e}")
            return None

    # --- trabajo por canción -----------------------------------------------------------------------------------
    def trabajo(self, gid, act, sig, t0):
        try:
            fin = t0 + act["dur"]
            ref = datetime.fromtimestamp(fin)
            perfil = self.perfil_en(ref)
            plan = self.elegir_plan(sig, ref, perfil)
            if not plan:
                return
            plan.update(fin=fin, estado="esperando", despues=etiqueta(act))
            self.plan = plan
            self.log("info", f"Planeo «{plan['nombre']}» después de: {etiqueta(act)}  (perfil {perfil['nombre']})")
            spots = []
            if plan["clave"] == "tanda":
                spots = self.elegir_spots(ref)
                if not spots:
                    plan["estado"] = "omitido"
                    self.log("aviso", "Tanda sin comerciales vigentes; la omito.")
                    return
            while time.time() < fin - float(self.cfg["radioboss"]["anticipacion_seg"]):
                if gid != self.gen_id:
                    plan["estado"] = "descartado"
                    return
                time.sleep(1)
            if gid != self.gen_id:
                plan["estado"] = "descartado"
                return
            plan["estado"] = "generando"
            ctx = self.contexto(act, sig, fin, perfil, plan)
            ins = self.cfg["instrucciones"]
            cola = []
            if plan["clave"] == "tanda":
                t = self.cfg["tandas"]
                cola += [self._voz("pre_tanda", ins["pre_tanda"], ctx)]
                cola += [{"tipo": "cortinilla", "ruta": t["cortinilla_entrada"], "reg": False}] if t["cortinilla_entrada"] else []
                cola += [{"tipo": "comercial", "nombre": c["nombre"], "texto": c.get("texto", ""), "ruta": r, "reg": True} for c, r in spots]
                cola += [{"tipo": "cortinilla", "ruta": t["cortinilla_salida"], "reg": False}] if t["cortinilla_salida"] else []
                cola += [self._voz("post_tanda", ins["post_tanda"], ctx)]
            else:
                if plan["clave"] == "orden" and not self.cerebro.cliente():
                    for s_ in plan["saludos"]:
                        self.sal.parchar(s_["id"], {"estado": "fallido"})
                    plan["estado"] = "falló"
                    self.log("aviso", "Las órdenes al locutor necesitan la clave de Claude (Ajustes → Claves). Quedaron marcadas como fallidas.")
                    return
                it = self._voz(plan["clave"], plan["instruccion"], ctx, self._texto_saludos(plan.get("saludos", [])), plan.get("saludos"))
                if it and plan.get("patrocinador"):
                    it["tipo"], it["nombre"] = "comercial", plan["patrocinador"]["nombre"] + " (mención)"
                cola = [it]
            cola = [x for x in cola if x and x.get("ruta") and Path(x["ruta"]).exists()]
            if not cola:
                plan["estado"] = "falló"
                return
            self._insertar(gid, plan, act, sig, cola)
        except Exception as e:
            self.log("aviso", f"Error preparando la intervención: {e}")
            logger.exception("trabajo")

    def _insertar(self, gid, plan, act, sig, cola):
        regs = [x for x in cola if x.get("reg")]
        rb = self.rb()
        info = rb.info()
        a, s = info["actual"] or {}, info["siguiente"] or {}
        if gid != self.gen_id or a.get("archivo") != act["archivo"] or s.get("archivo") != (sig or {}).get("archivo"):
            plan["estado"] = "descartado"
            plan["detalle"] = "cambió la lista mientras se generaba"
            self.log("aviso", "La lista de RadioBOSS cambió mientras generaba; lo descarto (no pasa nada al aire).")
            for x in regs:
                self.db.registrar(x["tipo"], x["nombre"], x.get("texto", ""), x["ruta"], "descartado")
            return
        if self.cfg["sistema"]["ensayo"]:
            plan["estado"] = "ensayo"
            for x in regs:
                self.db.registrar(x["tipo"], x["nombre"], x.get("texto", ""), x["ruta"], "ensayo")
            self.log("info", f"ENSAYO: habría insertado {len(cola)} archivo(s). Desactiva el modo ensayo para salir al aire.")
            return
        if not rb.insertar_en_orden([x["ruta"] for x in cola], self.cfg["estacion"]["nombre"]):
            plan["estado"] = "falló"
            self.log("aviso", "RadioBOSS rechazó la inserción.")
            return
        plan["estado"] = "insertado"
        for x in regs:
            i = self.db.registrar(x["tipo"], x["nombre"], x.get("texto", ""), x["ruta"], "insertado")
            self.pendientes.setdefault(_norm(x["ruta"]), []).append(i)
            self.etiquetas[_norm(x["ruta"])] = ("📢 Comercial: " + x["nombre"]) if x["tipo"] == "comercial" else "🎙️ Locutor IA"
        for x in cola:
            if not x.get("reg"):
                self.etiquetas[_norm(x["ruta"])] = "🎵 Cortinilla"
        for s_ in plan.get("saludos", []):
            self.sal.parchar(s_["id"], {"estado": "leido", "leido": datetime.now().strftime("%Y-%m-%d %H:%M")})
        self.log("ok", f"Insertado en RadioBOSS: {len(cola)} archivo(s) tras «{plan['despues']}».")

    def _emitido(self, archivo):
        ids = self.pendientes.get(_norm(archivo))
        if ids:
            self.db.emitido(ids.pop(0))
            if not ids:
                del self.pendientes[_norm(archivo)]

    # --- vigilancia -----------------------------------------------------------------------------------------------
    def tick(self):
        try:
            info = self.rb().info()
        except (requests.RequestException, Exception) as e:
            if self.conectado or self.error is None:
                self.log("aviso", "No hay conexión con RadioBOSS (¿abierto, API activada, puerto y contraseña correctos?).")
            self.conectado, self.error = False, str(e)[:160]
            return
        if not self.conectado:
            self.log("ok", "Conectado a RadioBOSS.")
        self.conectado, self.error, self.info = True, None, info
        act = info["actual"]
        if info["estado"] != "play" or not act:
            return
        nuevo = act["archivo"] != self.ult_fn or info["pos"] + 2 < self.ult_pos
        self.ult_fn, self.ult_pos = act["archivo"], info["pos"]
        if not nuevo:
            return
        self.gen_id += 1
        self._emitido(act["archivo"])
        if self.primera:
            self.primera = False
            return
        if self.pausado or not self.es_musica(act):
            return
        threading.Thread(target=self.trabajo, args=(self.gen_id, act, info["siguiente"], time.time()), daemon=True).start()

    # --- para la interfaz -----------------------------------------------------------------------------------------
    def _rotular(self, t):
        e = self.etiquetas.get(_norm(t["archivo"])) if t else None
        return {**t, "titulo": e, "artista": ""} if e else t

    def snapshot(self):
        info = self.info or {}
        p = self.plan
        return {"corriendo": self.corriendo, "pausado": self.pausado, "ensayo": self.cfg["sistema"]["ensayo"],
                "conectado": self.conectado, "error": self.error, "reproduciendo": info.get("estado"),
                "actual": self._rotular(info.get("actual")), "siguiente": self._rotular(info.get("siguiente")),
                "plan": {k: p.get(k) for k in ("clave", "nombre", "estado", "fin", "despues", "detalle")} if p else None,
                "desde": self.desde, "objetivo": self.objetivo, "perfil": self.perfil_en(datetime.now())["nombre"],
                "proxima_tanda": self.proxima_tanda(), "hoy": self.db.hoy(), "ahora": time.time(),
                "tanda_forzada": self.forzar_tanda}

    def generar_prueba(self, clave):
        tp = next((t for t in self.cfg["tipos"] if t["id"] == clave), None)
        instruccion = tp["instruccion"] if tp else self.cfg["instrucciones"].get(clave, "Haz una intervención breve.")
        info = self.info or {}
        act = info.get("actual") or {"titulo": "Canción de ejemplo", "artista": "Artista Uno", "dur": 200, "archivo": "x"}
        sig = info.get("siguiente") or {"titulo": "Otra canción", "artista": "Artista Dos", "dur": 200, "archivo": "y"}
        now = datetime.now()
        ctx = {"dia": DIAS[now.weekday()], "hora": hora_hablada(now), "saludo": saludo(now), "clima": extras.clima(self.cfg),
               "ant": etiqueta(act), "sig": etiqueta(sig), "estilo": self.perfil_en(now)["estilo"], "fecha_especial": self.fecha_especial(now)}
        if clave == "noticias":
            ctx["noticias"] = extras.titulares(self.cfg)
        texto, origen = self.cerebro.guion(clave, instruccion, ctx)
        return texto, origen

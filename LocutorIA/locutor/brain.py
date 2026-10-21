"""Cerebro: escribe lo que dice el locutor.
Cadena de IAs gratis con respaldo automático (Groq → Gemini → Ollama…) y, si ninguna responde,
un banco de frases editable que funciona sin internet ni claves."""
import logging
import os
import random
import re
import time
from collections import deque

import requests

from .store import RETIRADOS

log = logging.getLogger("locutor.brain")

PROVEEDORES = {
    "groq": ("Groq (gratis)", "https://api.groq.com/openai/v1", "groq"),
    "gemini": ("Google Gemini (gratis)", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini"),
    "openrouter": ("OpenRouter (modelos :free)", "https://openrouter.ai/api/v1", "openrouter"),
    "ollama": ("Ollama (en tu PC, gratis)", "http://localhost:11434/v1", None),
    "personalizado": ("Otro compatible con OpenAI (LM Studio, Mistral…)", None, "personalizado"),
    "anthropic": ("Claude (de pago)", None, "anthropic"),
}


PREFERIDOS = {      # si el modelo configurado desaparece, se elige uno de estos (en este orden) entre los disponibles
    "groq": [r"gpt-oss-120b", r"gpt-oss-20b", r"qwen.*3", r"llama-4", r"llama-3\.3"],
    "gemini": [r"gemini-[\d.]+-flash-lite", r"gemini-[\d.]+-flash"],
    "openrouter": [r"gpt-oss-20b:free", r":free"],
    "ollama": [r"qwen2\.5", r"llama3", r"."],
    "personalizado": [r"."],
    "anthropic": [r"haiku", r"sonnet"],
}
NO_CHAT = re.compile(r"whisper|tts|guard|orpheus|embed|moderation|safeguard|image|dall|rerank|transcri|speech|audio|vision", re.I)


class ModeloError(Exception):
    pass


class LimiteError(Exception):
    def __init__(self, espera):
        super().__init__("límite de uso alcanzado")
        self.espera = espera


def depurar(t):
    t = re.sub(r"[\U00010000-\U0010ffff]", "", t or "")           # emojis
    t = re.sub(r"[*_#`\"“”«»<>]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def hablado(etiqueta):
    """'Título (artista: X)' -> 'Título de X'"""
    m = re.match(r"(.*?) \(artista: (.*)\)$", etiqueta or "")
    return f"{m[1]} de {m[2]}" if m else (etiqueta or "")


class Cerebro:
    def __init__(self, ajustes):
        self.aj = ajustes
        self.hist = deque()
        self.recientes = deque(maxlen=14)       # plantillas usadas hace poco
        self.enfriar = {}                       # (proveedor, modelo) -> hasta cuándo no usarlo
        self.alias = {}                         # (proveedor, modelo) -> modelo que lo reemplaza porque ya no existe
        self._modelos = {}                      # proveedor -> (hora, lista)
        self.ultimo_error = ""

    @property
    def cfg(self):
        return self.aj.datos

    # ------------------------------------------------------------------ proveedores
    def clave(self, nombre):
        return self.cfg["claves"].get(nombre) or os.getenv(nombre.upper() + "_API_KEY") or ""

    def _usable(self, p):
        if p == "ollama":
            return True
        if p == "personalizado":
            return bool(self.cfg["llm"].get("base_url"))
        return bool(self.clave(p))

    def cadena(self):
        out = []
        for e in self.cfg["llm"]["cadena"]:
            p, m = e.get("proveedor"), (e.get("modelo") or "").strip()
            if p in PROVEEDORES and m and self._usable(p):
                m = RETIRADOS.get((p, m)) or self.alias.get((p, m)) or m
                out.append((p, m))
        return out

    def modelos(self, p, forzar=False):
        """Lista de modelos de chat disponibles en ese proveedor (GET /models)."""
        t, lista = self._modelos.get(p, (0, None))
        if lista is not None and not forzar and time.time() - t < 1800:
            return lista
        base = self.cfg["llm"].get("base_url") if p == "personalizado" else PROVEEDORES[p][1]
        if not base:
            raise RuntimeError("Falta la dirección base de este proveedor.")
        h = {"Authorization": "Bearer " + self.clave(p)} if self.clave(p) else {}
        r = requests.get(base.rstrip("/") + "/models", headers=h, timeout=15)
        r.raise_for_status()
        ids = sorted({re.sub(r"^models/", "", x["id"]) for x in r.json().get("data", []) if x.get("id")})
        lista = [i for i in ids if not NO_CHAT.search(i)]
        self._modelos[p] = (time.time(), lista)
        return lista

    def _sustituto(self, p, malo):
        try:
            disp = [m for m in self.modelos(p, True) if m != malo]
        except Exception:
            return None
        for patron in PREFERIDOS.get(p, []):
            for m in disp:
                if re.search(patron, m):
                    return m
        return None

    def hay_ia(self):
        return bool(self.cadena())

    def _una(self, p, modelo, sistema, usuario, tokens):
        if p == "anthropic":
            import anthropic
            c = anthropic.Anthropic(api_key=self.clave("anthropic"), max_retries=0)
            r = c.messages.create(model=modelo, max_tokens=tokens, timeout=25, system=sistema, messages=[{"role": "user", "content": usuario}])
            return "".join(b.text for b in r.content if b.type == "text")
        base = self.cfg["llm"].get("base_url") if p == "personalizado" else PROVEEDORES[p][1]
        h = {"Content-Type": "application/json"}
        if self.clave(p):
            h["Authorization"] = "Bearer " + self.clave(p)
        cuerpo = {"model": modelo, "max_tokens": max(tokens, 1000 if "gpt-oss" in modelo else 700), "temperature": 0.9,
                  "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]}
        if p == "groq" and "gpt-oss" in modelo:
            cuerpo["reasoning_effort"] = "low"       # que "piense" poco: respuesta rápida y menos consumo de cupo
        r = requests.post(base.rstrip("/") + "/chat/completions", headers=h, timeout=30, json=cuerpo)
        if r.status_code == 429:
            try:
                espera = min(int(float(r.headers.get("retry-after", 300))), 3600)
            except ValueError:
                espera = 300
            raise LimiteError(max(espera, 30))
        if r.status_code in (401, 403):
            raise PermissionError(f"clave rechazada ({r.status_code})")
        if r.status_code in (400, 404) and re.search(r"model|decommission|not.?found|does not exist", r.text, re.I):
            raise ModeloError(self._msg(r))
        if r.status_code >= 400:
            raise RuntimeError(f"{r.status_code}: {self._msg(r)}")
        t = (r.json()["choices"][0]["message"].get("content") or "").strip()
        if not t:
            raise RuntimeError("respuesta vacía")
        return t

    @staticmethod
    def _msg(r):
        try:
            e = r.json()
            e = e.get("error", e) if isinstance(e, dict) else e
            return str(e.get("message") if isinstance(e, dict) else e)[:200]
        except Exception:
            return r.text[:200]

    def _generar(self, sistema, usuario, tokens=300):
        """Prueba cada IA de la cadena en orden. Devuelve (texto, 'proveedor/modelo') o lanza RuntimeError."""
        fallos = []
        for p, m in self.cadena():
            if self.enfriar.get((p, m), 0) > time.time():
                fallos.append(f"{p}/{m}: en pausa por límite de uso")
                continue
            try:
                return self._una(p, m, sistema, usuario, tokens), f"{p}/{m}"
            except ModeloError as e:
                nuevo = self._sustituto(p, m)
                if nuevo:
                    try:
                        txt = self._una(p, nuevo, sistema, usuario, tokens)
                        self.alias[(p, m)] = nuevo
                        log.warning("El modelo %s/%s ya no existe: uso %s", p, m, nuevo)
                        return txt, f"{p}/{nuevo}"
                    except Exception:
                        pass
                self.enfriar[(p, m)] = time.time() + 600
                fallos.append(f"{p}/{m}: el modelo ya no existe ({e})")
            except LimiteError as e:
                self.enfriar[(p, m)] = time.time() + e.espera
                fallos.append(f"{p}/{m}: límite diario/por minuto alcanzado")
            except PermissionError as e:
                self.enfriar[(p, m)] = time.time() + 3600
                fallos.append(f"{p}/{m}: {e}")
            except Exception as e:
                self.enfriar[(p, m)] = time.time() + 60
                fallos.append(f"{p}/{m}: {str(e)[:100]}")
        raise RuntimeError("; ".join(fallos) or "No hay ninguna IA configurada")

    def probar(self):
        """Prueba cada eslabón de la cadena (ignora las pausas por límite)."""
        res = []
        for e in self.cfg["llm"]["cadena"]:
            p, m = e.get("proveedor"), (e.get("modelo") or "").strip()
            if p not in PROVEEDORES or not m:
                continue
            m = RETIRADOS.get((p, m)) or self.alias.get((p, m)) or m
            if not self._usable(p):
                res.append({"proveedor": p, "modelo": m, "ok": False, "mensaje": "Falta la clave de este proveedor."})
                continue
            try:
                t0 = time.time()
                self._una(p, m, "Responde solo con la palabra: ok", "ping", 10)
                self.enfriar.pop((p, m), None)
                res.append({"proveedor": p, "modelo": m, "ok": True, "mensaje": f"Responde bien ({time.time() - t0:.1f} s)."})
            except LimiteError:
                res.append({"proveedor": p, "modelo": m, "ok": False, "mensaje": "Límite de uso alcanzado ahora mismo (la clave es válida)."})
            except ModeloError as ex:
                nuevo = self._sustituto(p, m)
                try:
                    disp = ", ".join(self.modelos(p)[:8])
                except Exception:
                    disp = "(no pude pedir la lista)"
                if nuevo:
                    try:
                        self._una(p, nuevo, "Responde solo con la palabra: ok", "ping", 10)
                        self.alias[(p, m)] = nuevo
                        res.append({"proveedor": p, "modelo": m, "ok": True, "mensaje": f"«{m}» ya no existe: usaré «{nuevo}» automáticamente. Para fijarlo, escríbelo en Modelo."})
                        continue
                    except Exception:
                        pass
                res.append({"proveedor": p, "modelo": m, "ok": False, "mensaje": f"El modelo ya no existe ({ex}). Disponibles: {disp}"})
            except Exception as ex:
                res.append({"proveedor": p, "modelo": m, "ok": False, "mensaje": str(ex)[:200]})
        return res

    # ------------------------------------------------------------------ guiones con IA
    def _sistema(self, estilo_perfil):
        e, l = self.cfg["estacion"], self.cfg["locutor"]
        recientes = "\n".join(f"- {h}" for h in self.hist) or "(ninguna todavía)"
        curios = ("Puedes dar un dato curioso SOLO si estás 100% seguro de que es cierto." if l.get("curiosidades") else
                  "NO inventes datos: nada de curiosidades, fechas, premios ni historias del artista o la canción. "
                  "Di artista y título tal cual te los doy.")
        return (
            f"Eres {l['nombre']}, locutor de {e['nombre']} ({e['eslogan']}), en {e['ciudad']}. "
            f"Hablas en {l['dialecto']}. Personalidad: {l['personalidad']}.\n"
            f"Tu forma de ser y de opinar: {l['opiniones']}\n"
            f"TEMAS PROHIBIDOS (jamás los toques): {l['prohibido']}\n"
            f"Estilo del horario actual: {estilo_perfil or 'natural'}.\n"
            "Escribes SOLO lo que dirás al aire, listo para que lo lea un sintetizador de voz. Escribe siempre en español.\n"
            f"Reglas:\n- Entre {l['palabras_min']} y {l['palabras_max']} palabras.\n"
            "- Sin emojis, hashtags, markdown, comillas ni acotaciones entre paréntesis.\n"
            "- Frases cortas, como se habla, no como se escribe. Usa '...' o comas para pausas breves.\n"
            "- Escribe números como se dicen en voz alta.\n"
            f"- {curios}\n"
            "- Varía cómo empiezas y cómo cierras. No repitas ninguna de estas intervenciones recientes ni su estructura:\n"
            f"{recientes}")

    def _usuario(self, instruccion, ctx, extra):
        e = self.cfg["estacion"]
        partes = [f"Día: {ctx['dia']}. Momento: {ctx['saludo']}. Hora al salir al aire: {ctx['hora']}."]
        if ctx.get("fecha_especial"):
            partes.append(f"Fecha especial de hoy: {ctx['fecha_especial']} (menciónala solo si encaja natural).")
        partes += [f"Clima: {ctx.get('clima') or 'no disponible (no lo menciones)'}.",
                   f"Canción que termina: {ctx['ant']}.",
                   f"Canción que sigue: {ctx['sig'] or 'ninguna (no presentes canción)'}.",
                   f"Contacto de la estación: {e.get('contacto', '')} {e.get('web', '')}."]
        if ctx.get("noticias"):
            partes.append("Titulares disponibles (úsalos tal cual): " + " | ".join(ctx["noticias"]))
        if ctx.get("patrocinador"):
            partes.append("Patrocinador a mencionar: " + ctx["patrocinador"])
        partes += [f"Qué debes hacer: {instruccion}", extra, "Escribe solo el texto a decir."]
        return "\n".join(p for p in partes if p)

    # ------------------------------------------------------------------ banco de frases (sin IA)
    def _vars(self, ctx, saludos):
        e, hora = self.cfg["estacion"], ctx["hora"]
        sal = " ".join(f"Un saludo de {s.get('de') or 'un oyente'} para {s.get('para') or 'alguien especial'}: {s['mensaje']}." for s in saludos or [])
        return {"ant": hablado(ctx["ant"]), "sig": hablado(ctx["sig"]) if ctx.get("sig") else "", "est": e["nombre"], "eslogan": e["eslogan"],
                "hora": hora, "clima": ctx.get("clima") or "", "dia": ctx["dia"], "contacto": e.get("contacto", ""), "buenas": ctx["saludo"].capitalize(),
                "son": "Es" if hora.startswith("la una") else "Son", "van": "Va" if hora.startswith("la una") else "Van",
                "noticia": (ctx.get("noticias") or [""])[0], "patrocinador": (ctx.get("patrocinador") or "").split(". Datos")[0],
                "fecha_especial": ctx.get("fecha_especial") or "", "saludos": sal}

    def _plantilla(self, clave, ctx, saludos=None):
        banco = self.cfg.get("frases", {})
        frases = banco.get(clave) or banco.get("transicion") or ["Seguimos con {sig}."]
        v = self._vars(ctx, saludos)
        validas = [f for f in frases if all(v.get(c) for c in re.findall(r"{(\w+)}", f))]
        if not validas:
            return v["sig"] and f"Seguimos con {v['sig']}." or f"Estás en {v['est']}."
        frescas = [f for f in validas if f not in self.recientes] or validas
        f = random.choice(frescas)
        self.recientes.append(f)
        return re.sub(r"{(\w+)}", lambda m: v.get(m[1], ""), f)

    # ------------------------------------------------------------------ API para el motor
    def guion(self, clave, instruccion, ctx, extra="", saludos=None):
        """Devuelve (texto, origen). Nunca lanza excepción: si ninguna IA responde usa el banco de frases."""
        txt, origen = None, "frases"
        if self.hay_ia():
            try:
                bruto, origen = self._generar(self._sistema(ctx.get("estilo")), self._usuario(instruccion, ctx, extra))
                txt = depurar(bruto)
                self.ultimo_error = ""
            except Exception as e:
                self.ultimo_error = str(e)[:300]
                log.warning("IA no disponible: %s", e)
        if not txt:
            txt, origen = self._plantilla(clave, ctx, saludos), "frases"
        self.hist.append(txt)
        while len(self.hist) > int(self.cfg["locutor"].get("memoria", 12)):
            self.hist.popleft()
        return txt, origen

    def escribir_spot(self, nombre, brief, categoria=""):
        """Redacta un comercial a partir de un brief. Lanza excepción si no hay IA (la interfaz lo muestra)."""
        if not self.hay_ia():
            raise RuntimeError("Para redactar con IA configura una IA gratis en Ajustes → IA gratis (por ejemplo Groq).")
        sistema = ("Eres redactor de comerciales de radio. Escribe un spot hablado de 20 a 30 segundos (55 a 75 palabras) para un solo "
                   f"locutor, en {self.cfg['locutor']['dialecto']}, con gancho y llamada a la acción. Usa los datos de contacto "
                   "EXACTAMENTE como se dan. No inventes precios, promociones, direcciones ni teléfonos. Escribe en español. "
                   "Sin emojis ni acotaciones. Devuelve solo el texto del spot.")
        return depurar(self._generar(sistema, f"Cliente: {nombre}\nRubro: {categoria}\nBrief: {brief}", 500)[0])

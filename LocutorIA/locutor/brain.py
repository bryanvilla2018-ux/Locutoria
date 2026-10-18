"""Cerebro: escribe lo que dice el locutor (Claude), con plantillas de respaldo si no hay IA."""
import logging
import os
import random
import re
from collections import deque

log = logging.getLogger("locutor.brain")

PLANTILLAS = {
    "transicion": ["Eso fue {ant}. Y ahora, {sig}.", "{ant}, aquí en {est}. Seguimos con {sig}.", "Qué tema... Ahora, {sig}."],
    "hora_clima": ["Son las {hora}. Seguimos con {sig}.", "Van las {hora} en {est}. Ahora, {sig}."],
    "id_estacion": ["Estás en {est}, {eslogan}. Ahora, {sig}."],
    "interaccion": ["Escríbenos al {contacto} y manda tu saludo. Mientras, {sig}."],
    "pre_tanda": ["Hacemos una pausa y ya volvemos.", "Nos vamos a una breve pausa, no te vayas que ya regresamos."],
    "post_tanda": ["De vuelta en {est}. Seguimos con {sig}.", "Regresamos con {sig}."],
    "_otro": ["Seguimos con {sig}.", "Ahora, {sig}."],
}


def depurar(t):
    t = re.sub(r"[\U00010000-\U0010ffff]", "", t or "")           # emojis
    t = re.sub(r"[*_#`\"“”«»<>]", "", t)
    return re.sub(r"\s+", " ", t).strip()


class Cerebro:
    def __init__(self, ajustes):
        self.aj = ajustes
        self.hist = deque()
        self._cliente, self._clave = None, None

    @property
    def cfg(self):
        return self.aj.datos

    def clave(self):
        return self.cfg["claves"].get("anthropic") or os.getenv("ANTHROPIC_API_KEY") or ""

    def cliente(self):
        k = self.clave()
        if not k:
            return None
        if k != self._clave:
            try:
                import anthropic
            except ImportError:
                log.warning("Falta el paquete 'anthropic'.")
                return None
            self._cliente, self._clave = anthropic.Anthropic(api_key=k, max_retries=1), k
        return self._cliente

    def _llamar(self, sistema, usuario, max_tokens=300):
        r = self.cliente().messages.create(model=self.cfg["llm"]["modelo"], max_tokens=max_tokens, timeout=20,
                                           system=sistema, messages=[{"role": "user", "content": usuario}])
        return "".join(b.text for b in r.content if b.type == "text")

    def probar(self):
        if not self.cliente():
            return False, "No hay clave de Anthropic (o falta instalar el paquete)."
        try:
            self._llamar("Responde solo: ok", "ping", 5)
            return True, f"Claude responde ({self.cfg['llm']['modelo']})."
        except Exception as e:
            return False, str(e)[:300]

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
            "Escribes SOLO lo que dirás al aire, listo para que lo lea un sintetizador de voz.\n"
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

    def _plantilla(self, clave, ctx, extra, saludos=None):
        if clave == "saludo":
            partes = [f"Un saludo de {s.get('de') or 'un oyente'} para {s.get('para') or 'alguien especial'}: {s['mensaje']}." for s in saludos or []]
            return " ".join(partes) + (f" Y ahora, {ctx['sig'].split(' (')[0]}." if ctx["sig"] else "")
        pl = PLANTILLAS.get(clave, PLANTILLAS["_otro"])
        return random.choice(pl).format(
            ant=ctx["ant"].split(" (")[0], sig=(ctx["sig"] or "la siguiente canción").split(" (")[0],
            est=self.cfg["estacion"]["nombre"], eslogan=self.cfg["estacion"]["eslogan"], hora=ctx["hora"],
            contacto=self.cfg["estacion"].get("contacto", ""))

    def guion(self, clave, instruccion, ctx, extra="", saludos=None):
        """Devuelve (texto, origen). Nunca lanza excepción: si Claude falla usa una plantilla."""
        txt, origen = None, "plantilla"
        if self.cliente():
            try:
                txt = depurar(self._llamar(self._sistema(ctx.get("estilo")), self._usuario(instruccion, ctx, extra)))
                origen = "claude"
            except Exception as e:
                log.warning("Claude falló (%s); uso plantilla.", e)
        txt = txt or self._plantilla(clave, ctx, extra, saludos)
        self.hist.append(txt)
        while len(self.hist) > int(self.cfg["locutor"].get("memoria", 12)):
            self.hist.popleft()
        return txt, origen

    def escribir_spot(self, nombre, brief, categoria=""):
        """Redacta un comercial a partir de un brief. Lanza excepción si no se puede (la interfaz lo muestra)."""
        if not self.cliente():
            raise RuntimeError("Falta la clave de Anthropic (Ajustes → Claves).")
        sistema = ("Eres redactor de comerciales de radio. Escribe un spot hablado de 20 a 30 segundos (55 a 75 palabras) para un solo "
                   f"locutor, en {self.cfg['locutor']['dialecto']}, con gancho y llamada a la acción. Usa los datos de contacto "
                   "EXACTAMENTE como se dan. No inventes precios, promociones, direcciones ni teléfonos. "
                   "Sin emojis ni acotaciones. Devuelve solo el texto del spot.")
        return depurar(self._llamar(sistema, f"Cliente: {nombre}\nRubro: {categoria}\nBrief: {brief}", 400))

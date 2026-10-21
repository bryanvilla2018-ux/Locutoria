"""Ajustes por defecto y almacenamiento en JSON (editable desde la interfaz)."""
import copy
import json
import threading
import uuid

from .paths import data_dir

TIPOS = [
    {"id": "transicion", "nombre": "Transición entre canciones", "peso": 6, "activo": True, "necesita_siguiente": True,
     "instruccion": "Cierra la canción que termina con un comentario breve y presenta la que sigue. Es la intervención más común."},
    {"id": "hora_clima", "nombre": "Hora y clima", "peso": 2, "activo": True, "necesita_siguiente": True,
     "instruccion": "Di la hora exactamente como te la doy y, si hay clima, menciónalo de forma natural. Luego presenta la canción que sigue."},
    {"id": "id_estacion", "nombre": "Identificación de la estación", "peso": 1, "activo": True, "necesita_siguiente": True,
     "instruccion": "Menciona el nombre de la estación y su eslogan de forma natural y presenta la canción que sigue."},
    {"id": "interaccion", "nombre": "Invitación a participar", "peso": 1, "activo": True, "necesita_siguiente": True,
     "instruccion": "Invita a los oyentes a mandar saludos o pedir canciones por el contacto que te doy, y presenta la canción que sigue."},
    {"id": "noticias", "nombre": "Titular breve (RSS)", "peso": 1, "activo": False, "necesita_siguiente": True,
     "instruccion": "Comenta UN titular de los que te doy, en una frase, sin añadir ningún dato que no esté en el titular. Luego presenta la canción que sigue."},
    {"id": "mencion", "nombre": "Mención de patrocinador", "peso": 1, "activo": False, "necesita_siguiente": True,
     "instruccion": "Menciona al patrocinador de forma natural y breve, como recomendación de un amigo, usando solo los datos que te doy. Luego presenta la canción que sigue."},
]

FRASES = {
    "transicion": ["Eso fue {ant}. Y ahora, {sig}.", "{ant}, aquí en {est}. Seguimos con {sig}.", "Qué temazo... Ahora le toca a {sig}.",
                   "Gracias por acompañarnos. Sigue {sig}.", "Así se siente {est}. Escucha ahora {sig}.", "Y seguimos con buena música: {sig}.",
                   "Qué rico sonó eso. Ahora, {sig}.", "Vamos con otra, esta vez {sig}.", "No te vayas, que sigue {sig}.",
                   "Eso era {ant}. Atento, que viene {sig}."],
    "hora_clima": ["{son} {hora}. Seguimos con {sig}.", "{van} {hora} aquí en {est}. Ahora, {sig}.", "{son} {hora}. Afuera tenemos {clima}. Ahora, {sig}.",
                   "{buenas} desde {est}. {son} {hora}. Sigue {sig}.", "Con {clima} afuera, qué mejor que {sig}.",
                   "{son} {hora}, y la música sigue con {sig}.", "{buenas}. Marcan {hora}. Escucha {sig}."],
    "id_estacion": ["Estás en {est}, {eslogan}. Ahora, {sig}.", "{est}, {eslogan}. Sigue {sig}.", "Sintonizas {est}. Esto es {sig}.",
                    "Aquí {est}, {eslogan}. Vamos con {sig}.", "Gracias por elegir {est}. Ahora, {sig}.", "{est}: {eslogan}. Y suena {sig}."],
    "interaccion": ["Escríbenos al {contacto} y manda tu saludo. Mientras, {sig}.", "Mándanos tu saludo al {contacto}. Ahora, {sig}.",
                    "¿Quieres pedir una canción? Escríbenos al {contacto}. Suena {sig}.", "Tu saludo cuenta: {contacto}. Y ahora, {sig}.",
                    "Dedica una canción al {contacto}. Mientras tanto, {sig}."],
    "noticias": ["Titular de hoy: {noticia}. Y ahora, {sig}.", "Por si no lo sabías: {noticia}. Seguimos con {sig}."],
    "mencion": ["Te recomendamos {patrocinador}. Ahora, {sig}.", "Este momento lo acompaña {patrocinador}. Sigue {sig}."],
    "pre_tanda": ["Hacemos una pausa y ya volvemos.", "Nos vamos a una breve pausa, no te vayas que ya regresamos.", "Un momento, que ya volvemos con más música.",
                  "Pausa comercial, y enseguida seguimos en {est}.", "Quédate por aquí, que regresamos en un instante.", "Hacemos una pausa corta. ¡Ya volvemos!"],
    "post_tanda": ["De vuelta en {est}. Seguimos con {sig}.", "Regresamos con {sig}.", "Gracias por esperar. Sigue {sig}.", "Seguimos con la música: {sig}.",
                   "Aquí estamos otra vez. Ahora, {sig}.", "Y volvemos a la música con {sig}.", "De vuelta en {est}.", "Gracias por esperar, seguimos con buena música."],
    "saludo": ["{saludos} Y ahora, {sig}.", "{saludos} Seguimos con {sig}.", "{saludos}"],
}

AJUSTES = {
    "estacion": {"nombre": "Mi Radio", "eslogan": "la música que te acompaña", "ciudad": "San Salvador, El Salvador",
                 "latitud": 13.6929, "longitud": -89.2182, "contacto": "WhatsApp 7000 0000", "web": ""},
    "locutor": {
        "nombre": "Dani",
        "dialecto": "español de El Salvador, cercano y natural; puedes usar 'vos' con moderación, sin exagerar la jerga",
        "personalidad": "cálido, con buen humor y energía media; nunca grita ni habla de más",
        "opiniones": "Le gustan la buena música, el café y las tardes tranquilas. Habla como un amigo, nunca como un vendedor. "
                     "Sobre las canciones da comentarios de ambiente y gusto personal ('qué temazo', 'para cantar en el carro'), nunca datos técnicos.",
        "prohibido": "Política, religión, partidos, sexo, violencia, críticas a otras emisoras, promesas de premios y consejos de salud. No hables mal de ningún artista.",
        "palabras_min": 8, "palabras_max": 28, "memoria": 12, "max_saludos": 3, "curiosidades": False},
    "tipos": TIPOS,
    "instrucciones": {
        "pre_tanda": "Anuncia que vamos a pausa comercial y que ya regresamos. Una o dos frases cortas, distintas cada vez.",
        "post_tanda": "Da la bienvenida de regreso de la pausa comercial y presenta la canción que sigue (si hay).",
        "saludo": "Lee los saludos de los oyentes de forma cálida y natural, conservando los nombres exactos, y presenta la canción que sigue.",
        "orden": "Cumple la instrucción del operador al pie de la letra, con tu estilo."},
    "perfiles": [
        {"nombre": "Mañanero", "desde": "05:00", "hasta": "10:00", "estilo": "Energía alta, ánimo para empezar el día, ritmo ágil.", "cada_min": 2, "cada_max": 3, "habla": True},
        {"nombre": "Tarde", "desde": "10:00", "hasta": "19:00", "estilo": "Energía media, cercano y relajado.", "cada_min": 2, "cada_max": 4, "habla": True},
        {"nombre": "Noche", "desde": "19:00", "hasta": "23:00", "estilo": "Más tranquilo y cálido, como acompañando a alguien.", "cada_min": 3, "cada_max": 5, "habla": True},
        {"nombre": "Madrugada", "desde": "23:00", "hasta": "05:00", "estilo": "Voz baja y suave, pocas palabras.", "cada_min": 4, "cada_max": 7, "habla": True}],
    "fechas": [
        {"fecha": "01-01", "nota": "Hoy es Año Nuevo"}, {"fecha": "02-14", "nota": "Hoy es el Día del Amor y la Amistad"},
        {"fecha": "05-01", "nota": "Hoy es el Día del Trabajo"}, {"fecha": "05-10", "nota": "Hoy es el Día de la Madre"},
        {"fecha": "06-17", "nota": "Hoy es el Día del Padre"}, {"fecha": "09-15", "nota": "Hoy es el Día de la Independencia"},
        {"fecha": "11-02", "nota": "Hoy es el Día de los Difuntos"}, {"fecha": "12-25", "nota": "Hoy es Navidad"}],
    "pronunciacion": [{"palabra": "DJ", "como": "di yei"}, {"palabra": "FM", "como": "efe eme"}],
    "radioboss": {"host": "127.0.0.1", "puerto": 9001, "usuario": "", "password": "", "posicion": -2,
                  "intervalo_seg": 2, "anticipacion_seg": 45, "min_cancion_seg": 60},
    "llm": {"cadena": [{"proveedor": "groq", "modelo": "llama-3.3-70b-versatile"},
                       {"proveedor": "groq", "modelo": "llama-3.1-8b-instant"},
                       {"proveedor": "gemini", "modelo": "gemini-2.5-flash-lite"}],
            "base_url": "http://localhost:1234/v1"},
    "tts": {"proveedor": "edge",
            "edge": {"voz_locutor": "es-SV-RodrigoNeural", "voz_comercial": "es-SV-LorenaNeural", "rate": 0, "pitch": 0},
            "elevenlabs": {"voz_locutor": "", "voz_comercial": "", "modelo": "eleven_multilingual_v2",
                           "stability": 0.45, "similarity": 0.8, "style": 0.3},
            "openai": {"voz_locutor": "ash", "voz_comercial": "coral", "modelo": "gpt-4o-mini-tts",
                       "instrucciones": "Locutor de radio musical latinoamericano. Tono cálido, cercano, ritmo natural, sonrisa en la voz."}},
    "audio": {"procesar": True, "compresor": True, "loudness": -16, "pad_ini_ms": 150, "pad_fin_ms": 250},
    "claves": {"groq": "", "gemini": "", "openrouter": "", "personalizado": "", "anthropic": "", "elevenlabs": "", "openai": ""},
    "tandas": {"activas": True, "minutos": [15, 45], "hora_desde": "06:00", "hora_hasta": "23:00", "cantidad": 3,
               "separar_categorias": True, "cortinilla_entrada": "", "cortinilla_salida": ""},
    "carpetas": {"voces": "", "spots": "", "youtube": "", "ignorar": []},
    "noticias": {"activo": False, "feeds": [], "max_titulares": 3},
    "clima": {"activo": True},
    "sistema": {"ensayo": True, "autoiniciar": False, "horas_audio": 24, "puerto_ui": 8765, "historial_dias": 90,
                "yt_cookies": "", "yt_autoactualizar": True},
    "frases": FRASES,
}


def mezclar(base, nuevo):
    out = copy.deepcopy(base)
    for k, v in (nuevo or {}).items():
        out[k] = mezclar(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def nuevo_id():
    return uuid.uuid4().hex[:10]


class Almacen:
    """JSON en disco con candado. Para dict (ajustes) o lista de dicts con 'id' (comerciales, saludos)."""

    def __init__(self, nombre, defecto):
        self.ruta = data_dir() / f"{nombre}.json"
        self.defecto, self.lock = defecto, threading.RLock()
        self.datos = copy.deepcopy(defecto)
        self.cargar()

    def cargar(self):
        with self.lock:
            if not self.ruta.exists():
                return
            try:
                crudo = json.loads(self.ruta.read_text("utf-8"))
            except Exception:
                self.ruta.rename(self.ruta.with_suffix(".corrupto.json"))
                return
            self.datos = mezclar(self.defecto, crudo) if isinstance(self.defecto, dict) else crudo

    def guardar(self):
        with self.lock:
            tmp = self.ruta.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.datos, ensure_ascii=False, indent=2), "utf-8")
            tmp.replace(self.ruta)

    # --- ajustes (dict) ---
    def poner(self, ruta, valor):
        with self.lock:
            d = self.datos
            *ks, k = ruta.split(".")
            for p in ks:
                d = d.setdefault(p, {})
            d[k] = valor
            self.guardar()

    # --- listas ---
    def lista(self):
        with self.lock:
            return copy.deepcopy(self.datos)

    def buscar(self, id_):
        return next((x for x in self.datos if x.get("id") == id_), None)

    def agregar(self, item):
        with self.lock:
            item = {**item, "id": item.get("id") or nuevo_id()}
            self.datos.append(item)
            self.guardar()
            return copy.deepcopy(item)

    def parchar(self, id_, cambios):
        with self.lock:
            it = self.buscar(id_)
            if it is None:
                return None
            it.update(cambios)
            self.guardar()
            return copy.deepcopy(it)

    def borrar(self, id_):
        with self.lock:
            self.datos[:] = [x for x in self.datos if x.get("id") != id_]
            self.guardar()


COMERCIAL = {"nombre": "Nuevo comercial", "categoria": "", "modo": "texto", "texto": "", "brief": "", "archivo": "",
             "voz": "comercial", "peso": 1, "activo": True, "uso": "tanda", "desde": "", "hasta": "",
             "dias": [1, 1, 1, 1, 1, 1, 1], "hora_desde": "00:00", "hora_hasta": "23:59", "max_por_dia": 0,
             "cama": "", "cama_volumen": 0.25}
SALUDO = {"tipo": "saludo", "de": "", "para": "", "mensaje": "", "prioridad": "normal", "no_antes": "",
          "estado": "pendiente", "creado": "", "leido": ""}

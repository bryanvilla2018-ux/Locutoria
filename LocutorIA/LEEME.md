# Locutor IA para RadioBOSS

Programa de escritorio (ventana propia, se abre con doble clic en `LocutorIA.exe`) que añade un **locutor con IA** a tu emisora.
RadioBOSS sigue sacando el audio al aire; Locutor IA vigila lo que suena y, justo antes de que termine cada canción,
inserta lo que corresponda: una intervención del locutor, saludos de oyentes o una tanda comercial completa.

> **Si algo falla (internet, IA, voz), no pasa nada al aire:** simplemente suena la siguiente canción. Cerrar el programa tampoco corta la música.

## Cómo conseguir el `.exe`

No pude compilar un `.exe` de Windows desde mi entorno (es Linux), así que incluyo dos caminos que lo hacen por ti:

| Opción | Pasos |
|---|---|
| **A. En tu PC con Windows** | Instala **Python 3.11 o 3.12** (marca *Add python.exe to PATH*), descomprime esta carpeta y haz doble clic en **`build_exe.bat`**. En unos minutos queda `dist\LocutorIA\LocutorIA.exe` con ffmpeg, ffprobe, yt-dlp y Deno incluidos. Copia esa carpeta completa donde quieras. |
| **B. Automática en GitHub** | Sube la carpeta a un repositorio, ve a *Actions → Compilar para Windows → Run workflow* y descarga el resultado. |
| **Probar sin compilar** | Doble clic en `ejecutar_sin_compilar.bat`. |

## Puesta en marcha (6 pasos)
1. **RadioBOSS → Settings → API**: activa el control remoto, anota puerto y contraseña. (El programa debe correr en el mismo PC.)
2. **Ajustes → RadioBOSS** → «Probar conexión».
3. **Ajustes → IA gratis**: crea una clave gratis y sin tarjeta en `console.groq.com/keys` y pégala en Groq; pulsa «Probar la cadena». (Opcional: Gemini de respaldo.) **Sin ninguna clave el locutor igual funciona** con el banco de frases editable (Locutor → Frases).
4. **Voz**: elige proveedor y pruébala. ElevenLabs es la más natural; Edge es gratis (voces `es-SV` de El Salvador incluidas) para probar.
5. **Locutor**: define personalidad, opiniones, temas prohibidos, horarios y tipos de pausa. Usa la pestaña **Probar**.
6. **Panel → Iniciar** en **MODO ENSAYO** (genera todo pero no inserta nada). Revisa el Historial; cuando suene bien, apaga el ensayo en *Ajustes → Sistema*.

## Qué contiene cada sección
| Sección | Para qué sirve |
|---|---|
| **Panel** | Estado en vivo: qué suena, qué sigue, qué planea el locutor y cuánto falta, contadores del día, registro, «decir algo ahora», tanda inmediata, modo ensayo. |
| **Locutor** | Personalidad, dialecto, **opiniones**, temas prohibidos, largo y memoria anti‑repetición · **tipos de pausa** editables con peso (puedes crear los tuyos) · **horarios y perfiles** (mañanero, noche, madrugada…) · **fechas especiales** · **banco de frases sin IA** · prueba de guiones. |
| **Voz** | ElevenLabs / OpenAI / Edge, voces por rol (locutor y comerciales), parámetros de expresividad, **masterizado de radio** (compresión y volumen), **diccionario de pronunciación**, prueba de voz. |
| **Comerciales** | Tus anunciantes: texto exacto, brief que redacta la IA (revisable) o audio ya grabado · **cama musical** · peso, vigencia, días, horas, máximo diario, categoría (no repite rubro en una tanda) · uso en tanda y/o **mención** del locutor · tandas por minuto, ventana horaria y cortinillas. |
| **Saludos** | Cola de dedicatorias que el locutor lee con sus palabras (con hora mínima y prioridad) y órdenes directas al locutor. |
| **YouTube** | Busca o pega un enlace, baja a mp3 y mándalo como siguiente tema / al final de RadioBOSS. Incluye **«Comprobar YouTube»** (diagnóstico real) y actualización automática de yt-dlp. |
| **Historial y reportes** | Todo lo dicho (con audio para reescuchar) y **reporte de comerciales con emisión confirmada** (el programa ve sonar el spot en RadioBOSS) exportable a CSV/Excel. |
| **Ajustes** | Conexión, tiempos, **IA gratis (cadena con respaldo automático)**, carpetas, clima y titulares RSS, cookies de YouTube, respaldo/restauración (sin claves), sistema. |
| **Ayuda** | Guía y **diagnóstico** de todo el sistema. |

Todo se guarda al instante. Los datos viven en `%APPDATA%\LocutorIA`.

## IA gratis: cómo funciona
El locutor prueba hasta 3 IAs **en orden** (por defecto Groq gpt-oss-120b → Groq gpt-oss-20b → Gemini). Si una se queda sin cupo gratis, se salta sola (y no la vuelve a molestar un rato); si ninguna responde, usa el **banco de frases** (editable, sin internet, evita repetir las últimas). Nunca hay silencio.
Límites gratis publicados en 2026 (pueden cambiar): Groq gpt-oss ≈ 1.000 consultas y 200.000 tokens al día cada modelo (unas 150–250 intervenciones); Gemini ya no publica su límite gratis y puede ser bajo. Ollama corre en tu PC sin límites. Claude sigue disponible como opción de pago.
**Los modelos gratis cambian seguido** (Groq retiró sus Llama el 16-ago-2026). Si un modelo desaparece, el programa elige solo otro disponible y avisa; *Ajustes → IA gratis → «Ver modelos disponibles»* muestra la lista real de tu proveedor.

## Para que suene natural
- Intervenciones cortas (8–28 palabras). Un locutor real no da discursos entre canciones.
- Lo que más cambia el resultado: **«Opiniones y forma de ser»** y **«Temas prohibidos»**.
- Usa perfiles por horario y agrega al diccionario los nombres que la voz pronuncie mal.
- Datos reales (hora de salida al aire, clima, fecha especial) hacen que no suene genérico. La IA tiene prohibido inventar datos de artistas.
- Revisa el Historial las primeras semanas y ajusta las instrucciones según lo que oigas.

## Límites honestos
- La voz entra **entre canciones**; no «pisa» la intro como un humano. Con el crossfade de RadioBOSS (2–3 s) la transición es suave.
- La API de RadioBOSS no entrega los segundos restantes con unidades documentadas: el programa estima el final con la duración de la pista. Si tus canciones tienen outro/fade recortado, sube *«Generar la voz N seg antes…»*.
- **Verificado aquí:** interfaz completa en un navegador real sin pantalla, y el flujo completo (saludos, pausas, tandas, orden de inserción, emisión confirmada, reportes, respaldo, YouTube con yt-dlp simulado) contra un **RadioBOSS simulado** con voz de relleno: 70 comprobaciones automáticas + recorrido de la interfaz.
- **No verificado aquí** (requiere tus claves o tu PC): llamadas reales a Groq/Gemini/ElevenLabs/OpenAI/Edge (la cadena de IA se probó con servidores falsos que simulan límite de uso y clave rechazada), YouTube real, y la ventana nativa (WebView2). Empieza siempre en modo ensayo.
- Se comunica con RadioBOSS solo por su API HTTP; comprueba que tu edición incluya el control remoto.
- YouTube exige desde finales de 2025 un motor de JavaScript: el compilado ya incluye **Deno**, ffmpeg, ffprobe y yt-dlp en la carpeta `herramientas`. Si aun así falla: *YouTube → Comprobar YouTube* (te dice la causa), *Actualizar yt-dlp*, o elige un navegador en *Ajustes → Sistema → Cookies de YouTube* (Firefox es el que mejor funciona).

## Música y licencias
Descargar de YouTube va contra sus términos de servicio, y emitir música requiere las licencias de comunicación pública de tu país (o música libre de derechos / con permiso). Úsalo solo con lo que tengas derecho a transmitir. Los comerciales redactados por IA deben **revisarse** antes de salir al aire; para clientes reales usa el copy aprobado en modo «Texto exacto».

## Probar sin RadioBOSS
`python herramientas/radioboss_simulado.py` levanta un RadioBOSS falso (puerto 9001) con canciones de 70 s. Deja los ajustes por defecto y pulsa Iniciar.

## Estructura
```
main.py                 arranque (ventana nativa)
build_windows.ps1       compila el .exe y baja ffmpeg, ffprobe, yt-dlp, deno
locutor/engine.py       motor: vigila RadioBOSS, planea e inserta
locutor/brain.py        guiones: cadena de IAs gratis + banco de frases
locutor/voice.py        TTS + masterizado ffmpeg + cama musical
locutor/server.py       API local (solo 127.0.0.1)
locutor/static/         interfaz (HTML/JS/CSS)
tests/                  prueba_backend.py · prueba_ui.py (navegador automático)
```

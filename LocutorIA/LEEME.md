# Locutor IA para RadioBOSS

Programa de escritorio (ventana propia, se abre con doble clic en `LocutorIA.exe`) que añade un **locutor con IA** a tu emisora.
RadioBOSS sigue sacando el audio al aire; Locutor IA vigila lo que suena y, justo antes de que termine cada canción,
inserta lo que corresponda: una intervención del locutor, saludos de oyentes o una tanda comercial completa.

> **Si algo falla (internet, IA, voz), no pasa nada al aire:** simplemente suena la siguiente canción. Cerrar el programa tampoco corta la música.

## Cómo conseguir el `.exe`

No pude compilar un `.exe` de Windows desde mi entorno (es Linux), así que incluyo dos caminos que lo hacen por ti:

| Opción | Pasos |
|---|---|
| **A. En tu PC con Windows** | Instala **Python 3.11 o 3.12** (marca *Add python.exe to PATH*), descomprime esta carpeta y haz doble clic en **`build_exe.bat`**. En unos minutos queda `dist\LocutorIA\LocutorIA.exe` con ffmpeg y yt-dlp incluidos. Copia esa carpeta completa donde quieras. |
| **B. Automática en GitHub** | Sube la carpeta a un repositorio, ve a *Actions → Compilar para Windows → Run workflow* y descarga el resultado. |
| **Probar sin compilar** | Doble clic en `ejecutar_sin_compilar.bat`. |

## Puesta en marcha (6 pasos)
1. **RadioBOSS → Settings → API**: activa el control remoto, anota puerto y contraseña. (El programa debe correr en el mismo PC.)
2. **Ajustes → RadioBOSS** → «Probar conexión».
3. **Ajustes → Claves y modelo de IA**: pega tu clave de Anthropic (guiones). Sin ella el locutor usa frases de plantilla y suena repetitivo.
4. **Voz**: elige proveedor y pruébala. ElevenLabs es la más natural; Edge es gratis (voces `es-SV` de El Salvador incluidas) para probar.
5. **Locutor**: define personalidad, opiniones, temas prohibidos, horarios y tipos de pausa. Usa la pestaña **Probar**.
6. **Panel → Iniciar** en **MODO ENSAYO** (genera todo pero no inserta nada). Revisa el Historial; cuando suene bien, apaga el ensayo en *Ajustes → Sistema*.

## Qué contiene cada sección
| Sección | Para qué sirve |
|---|---|
| **Panel** | Estado en vivo: qué suena, qué sigue, qué planea el locutor y cuánto falta, contadores del día, registro, «decir algo ahora», tanda inmediata, modo ensayo. |
| **Locutor** | Personalidad, dialecto, **opiniones**, temas prohibidos, largo y memoria anti‑repetición · **tipos de pausa** editables con peso (puedes crear los tuyos) · **horarios y perfiles** (mañanero, noche, madrugada…) · **fechas especiales** · prueba de guiones. |
| **Voz** | ElevenLabs / OpenAI / Edge, voces por rol (locutor y comerciales), parámetros de expresividad, **masterizado de radio** (compresión y volumen), **diccionario de pronunciación**, prueba de voz. |
| **Comerciales** | Tus anunciantes: texto exacto, brief que redacta la IA (revisable) o audio ya grabado · **cama musical** · peso, vigencia, días, horas, máximo diario, categoría (no repite rubro en una tanda) · uso en tanda y/o **mención** del locutor · tandas por minuto, ventana horaria y cortinillas. |
| **Saludos** | Cola de dedicatorias que el locutor lee con sus palabras (con hora mínima y prioridad) y órdenes directas al locutor. |
| **YouTube** | Busca o pega un enlace, baja a mp3 y mándalo como siguiente tema / al final de RadioBOSS. |
| **Historial y reportes** | Todo lo dicho (con audio para reescuchar) y **reporte de comerciales con emisión confirmada** (el programa ve sonar el spot en RadioBOSS) exportable a CSV/Excel. |
| **Ajustes** | Conexión, tiempos, carpetas, clima y titulares RSS, respaldo/restauración (sin claves), sistema. |
| **Ayuda** | Guía y **diagnóstico** de todo el sistema. |

Todo se guarda al instante. Los datos viven en `%APPDATA%\LocutorIA`.

## Para que suene natural
- Intervenciones cortas (8–28 palabras). Un locutor real no da discursos entre canciones.
- Lo que más cambia el resultado: **«Opiniones y forma de ser»** y **«Temas prohibidos»**.
- Usa perfiles por horario y agrega al diccionario los nombres que la voz pronuncie mal.
- Datos reales (hora de salida al aire, clima, fecha especial) hacen que no suene genérico. La IA tiene prohibido inventar datos de artistas.
- Revisa el Historial las primeras semanas y ajusta las instrucciones según lo que oigas.

## Límites honestos
- La voz entra **entre canciones**; no «pisa» la intro como un humano. Con el crossfade de RadioBOSS (2–3 s) la transición es suave.
- La API de RadioBOSS no entrega los segundos restantes con unidades documentadas: el programa estima el final con la duración de la pista. Si tus canciones tienen outro/fade recortado, sube *«Generar la voz N seg antes…»*.
- **Verificado aquí:** interfaz completa en un navegador real sin pantalla, y el flujo completo (saludos, pausas, tandas, orden de inserción, emisión confirmada, reportes, respaldo, YouTube con yt-dlp simulado) contra un **RadioBOSS simulado** con voz de relleno: 43 comprobaciones automáticas + recorrido de la interfaz.
- **No verificado aquí** (requiere tus claves o tu PC): llamadas reales a Claude/ElevenLabs/OpenAI/Edge, YouTube real, tu RadioBOSS real, la ventana nativa (WebView2) y el `.exe` compilado. Empieza siempre en modo ensayo.
- Se comunica con RadioBOSS solo por su API HTTP; comprueba que tu edición incluya el control remoto.
- Si YouTube cambia y las descargas fallan: *YouTube → Actualizar yt-dlp*.

## Música y licencias
Descargar de YouTube va contra sus términos de servicio, y emitir música requiere las licencias de comunicación pública de tu país (o música libre de derechos / con permiso). Úsalo solo con lo que tengas derecho a transmitir. Los comerciales redactados por IA deben **revisarse** antes de salir al aire; para clientes reales usa el copy aprobado en modo «Texto exacto».

## Probar sin RadioBOSS
`python herramientas/radioboss_simulado.py` levanta un RadioBOSS falso (puerto 9001) con canciones de 70 s. Deja los ajustes por defecto y pulsa Iniciar.

## Estructura
```
main.py                 arranque (ventana nativa)
locutor/engine.py       motor: vigila RadioBOSS, planea e inserta
locutor/brain.py        guiones con Claude + plantillas de respaldo
locutor/voice.py        TTS + masterizado ffmpeg + cama musical
locutor/server.py       API local (solo 127.0.0.1)
locutor/static/         interfaz (HTML/JS/CSS)
tests/                  prueba_backend.py · prueba_ui.py (navegador automático)
```

"""Locutor IA — punto de entrada. Abre la aplicación en su propia ventana."""
import sys
import threading
import time
import webbrowser

from locutor.app import configurar_logs, construir, puerto_libre, servir


class Puente:
    """Funciones nativas (diálogos de Windows) que la interfaz puede llamar."""

    def _dialogo(self, tipo, **kw):
        import webview
        FD = getattr(webview, "FileDialog", None)
        modo = getattr(FD, tipo) if FD else getattr(webview, tipo + "_DIALOG")
        r = webview.windows[0].create_file_dialog(modo, **kw)
        return r[0] if r else ""

    def elegir_archivo(self):
        return self._dialogo("OPEN", file_types=("Audio (*.mp3;*.wav;*.m4a;*.flac;*.ogg)", "Todos los archivos (*.*)"))

    def elegir_carpeta(self):
        return self._dialogo("FOLDER")

    def guardar(self, nombre, contenido):
        ruta = self._dialogo("SAVE", save_filename=nombre)
        if ruta:
            with open(ruta, "w", encoding="utf-8-sig", newline="") as f:
                f.write(contenido)
        return bool(ruta)


def main():
    configurar_logs()
    ctx, app = construir()
    puerto = puerto_libre(int(ctx["aj"].datos["sistema"]["puerto_ui"]))
    servir(app, puerto)
    url = f"http://127.0.0.1:{puerto}"
    threading.Thread(target=ctx["yt"].actualizar_auto, daemon=True).start()
    if ctx["aj"].datos["sistema"]["autoiniciar"]:
        ctx["motor"].iniciar()
    try:
        import webview
        webview.create_window("Locutor IA", url, width=1320, height=860, min_size=(1050, 680), js_api=Puente(), background_color="#0f1115")
        webview.start()
    except Exception as e:  # sin pywebview/WebView2: se abre en el navegador
        import logging
        logging.getLogger("locutor").exception("No se pudo abrir la ventana nativa")
        print("No se pudo abrir la ventana nativa (%s). Abriendo en el navegador: %s" % (e, url))
        webbrowser.open(url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    ctx["motor"].detener()
    sys.exit(0)


if __name__ == "__main__":
    main()

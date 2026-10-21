"""Ensamblaje de la aplicación (se usa desde main.py y desde las pruebas)."""
import logging
import socket
import threading

from werkzeug.serving import make_server

from . import paths
from .brain import Cerebro
from .db import DB
from .engine import Motor
from .extras import YouTube
from .server import crear_app
from .store import AJUSTES, Almacen
from .voice import Voz


def construir():
    aj, com, sal = Almacen("ajustes", AJUSTES), Almacen("comerciales", []), Almacen("saludos", [])
    db, voz, cerebro = DB(), Voz(aj), Cerebro(aj)
    motor = Motor(aj, com, sal, db, voz, cerebro)
    yt = YouTube(aj, voz, motor.rb, motor.log)
    ctx = dict(aj=aj, com=com, sal=sal, db=db, motor=motor, voz=voz, cerebro=cerebro, yt=yt)
    return ctx, crear_app(ctx)


def puerto_libre(preferido):
    for p in [preferido, *range(preferido + 1, preferido + 30)]:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    return 0


def servir(app, puerto):
    srv = make_server("127.0.0.1", puerto, app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def configurar_logs():
    d = paths.data_dir() / "logs"
    d.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s",
                        handlers=[logging.FileHandler(d / "locutor.log", encoding="utf-8")])
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

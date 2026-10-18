"""Historial de lo que dijo/insertó el locutor y registro de comerciales (para reportes)."""
import sqlite3
import threading
from datetime import datetime, timedelta

from .paths import data_dir

AHORA = lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class DB:
    def __init__(self):
        self.ruta = str(data_dir() / "locutor.db")
        self.lock = threading.Lock()
        with self._c() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS eventos(
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, tipo TEXT, nombre TEXT, texto TEXT,
                archivo TEXT, estado TEXT, ts_emitido TEXT)""")
            c.execute("CREATE INDEX IF NOT EXISTS i_ev ON eventos(tipo, nombre, estado, ts)")

    def _c(self):
        c = sqlite3.connect(self.ruta, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    def registrar(self, tipo, nombre, texto, archivo, estado):
        with self.lock, self._c() as c:
            return c.execute("INSERT INTO eventos(ts,tipo,nombre,texto,archivo,estado) VALUES(?,?,?,?,?,?)",
                             (AHORA(), tipo, nombre, texto, str(archivo or ""), estado)).lastrowid

    def estado(self, id_, estado):
        with self.lock, self._c() as c:
            c.execute("UPDATE eventos SET estado=? WHERE id=?", (estado, id_))

    def emitido(self, id_):
        with self.lock, self._c() as c:
            c.execute("UPDATE eventos SET estado='emitido', ts_emitido=? WHERE id=?", (AHORA(), id_))

    def listar(self, tipo="", estado="", desde="", hasta="", q="", limite=300):
        sql, p = "SELECT * FROM eventos WHERE 1=1", []
        for cond, val in (("tipo=?", tipo), ("estado=?", estado), ("date(ts)>=?", desde), ("date(ts)<=?", hasta)):
            if val:
                sql += f" AND {cond}"
                p.append(val)
        if q:
            sql += " AND (texto LIKE ? OR nombre LIKE ?)"
            p += [f"%{q}%"] * 2
        with self._c() as c:
            return [dict(r) for r in c.execute(sql + " ORDER BY id DESC LIMIT ?", p + [limite])]

    def contar_hoy(self, nombre):
        with self._c() as c:
            return c.execute("SELECT COUNT(*) FROM eventos WHERE tipo='comercial' AND nombre=? AND date(ts)=date('now','localtime') "
                             "AND estado IN ('insertado','emitido')", (nombre,)).fetchone()[0]

    def hoy(self):
        with self._c() as c:
            q = lambda w: c.execute(f"SELECT COUNT(*) FROM eventos WHERE date(ts)=date('now','localtime') AND {w}").fetchone()[0]
            return {"voces": q("tipo!='comercial' AND estado IN ('insertado','emitido')"),
                    "spots_insertados": q("tipo='comercial' AND estado IN ('insertado','emitido')"),
                    "spots_emitidos": q("tipo='comercial' AND estado='emitido'")}

    def reporte(self, desde, hasta):
        with self._c() as c:
            return [dict(r) for r in c.execute(
                "SELECT nombre, SUM(estado IN ('insertado','emitido')) AS insertados, SUM(estado='emitido') AS emitidos, "
                "MAX(ts_emitido) AS ultimo FROM eventos WHERE tipo='comercial' AND date(ts)>=? AND date(ts)<=? "
                "GROUP BY nombre ORDER BY emitidos DESC", (desde, hasta))]

    def detalle(self, desde, hasta):
        with self._c() as c:
            return [dict(r) for r in c.execute(
                "SELECT nombre, ts AS insertado, ts_emitido AS emitido, estado FROM eventos WHERE tipo='comercial' "
                "AND date(ts)>=? AND date(ts)<=? ORDER BY ts", (desde, hasta))]

    def purgar(self, dias):
        lim = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d")
        with self.lock, self._c() as c:
            c.execute("DELETE FROM eventos WHERE date(ts)<?", (lim,))

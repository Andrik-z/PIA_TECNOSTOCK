import json
import time
import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from src.domain.actor import Actor, Producto
from src.domain.apartado import Apartado, LineaApartado
from src.domain.errores import NoEncontradoError
from src.domain.estados import EstadoApartado
from src.domain.eventos import EventoDeDominio
from src.domain.inventario import Inventario
from src.domain.monedero import Monedero

ACTIVOS = (EstadoApartado.RESERVA_TEMPORAL.value, EstadoApartado.CONFIRMADO.value)


def _dt(v): return datetime.fromisoformat(v) if v else None
def _iso(v): return v.isoformat() if v else None


class _Repo:
    def __init__(self, db, conn):
        self.db, self.conn = db, conn

    def _x(self, sql, params=()):
        return self.db.execute(self.conn, sql, params)

    def _upsert(self, tabla, pk, cols, vals):
        sets = ", ".join(f"{c}=excluded.{c}" for c in cols[1:])
        self._x(f"INSERT INTO {tabla} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
                f"ON CONFLICT({pk}) DO UPDATE SET {sets}", vals)


class ActoresRepo(_Repo):
    def guardar(self, a: Actor):
        self._upsert("actores", "actor_id", ["actor_id", "nombre", "es_preferente", "activo", "ciudad"],
                     (a.actor_id, a.nombre, int(a.es_preferente), int(a.activo), a.ciudad))

    def _mk(self, r): return Actor(r[0], r[1], bool(r[2]), bool(r[3]), r[4])

    def obtener(self, actor_id) -> Actor:
        r = self._x("SELECT actor_id,nombre,es_preferente,activo,ciudad FROM actores WHERE actor_id=?", (actor_id,)).fetchone()
        if not r:
            raise NoEncontradoError(f"Actor {actor_id} no encontrado.")
        return self._mk(r)

    def listar(self) -> List[Actor]:
        return [self._mk(r) for r in self._x(
            "SELECT actor_id,nombre,es_preferente,activo,ciudad FROM actores ORDER BY actor_id").fetchall()]


class ProductosRepo(_Repo):
    def guardar(self, p: Producto):
        self._upsert("productos", "recurso_id", ["recurso_id", "descripcion", "precio", "habilitado"],
                     (p.recurso_id, p.descripcion, str(p.precio), int(p.habilitado)))

    def _mk(self, r): return Producto(r[0], r[1], Decimal(r[2]), bool(r[3]))

    def obtener(self, rid) -> Producto:
        r = self._x("SELECT recurso_id,descripcion,precio,habilitado FROM productos WHERE recurso_id=?", (rid,)).fetchone()
        if not r:
            raise NoEncontradoError(f"Producto {rid} no encontrado.")
        return self._mk(r)

    def listar(self) -> List[Producto]:
        return [self._mk(r) for r in self._x(
            "SELECT recurso_id,descripcion,precio,habilitado FROM productos ORDER BY recurso_id").fetchall()]


class InventariosRepo(_Repo):
    def guardar(self, inv: Inventario):
        self._upsert("inventarios", "sucursal_id", ["sucursal_id", "data"],
                     (inv.sucursal_id, json.dumps({"existencias": inv.existencias, "reservas": inv.reservas})))

    def _mk(self, sid, data):
        d = json.loads(data)
        return Inventario(sid, d["existencias"], d["reservas"])

    def obtener(self, sucursal_id) -> Inventario:
        r = self._x("SELECT sucursal_id,data FROM inventarios WHERE sucursal_id=?", (sucursal_id,)).fetchone()
        if not r:
            raise NoEncontradoError(f"Sucursal {sucursal_id} no encontrada.")
        return self._mk(*r)

    def listar(self) -> List[Inventario]:
        return [self._mk(*r) for r in self._x("SELECT sucursal_id,data FROM inventarios ORDER BY sucursal_id").fetchall()]


class ApartadosRepo(_Repo):
    @staticmethod
    def a_json(a: Apartado) -> str:
        return json.dumps({
            "sucursal_id": a.sucursal_id, "creado_en": _iso(a.creado_en), "autorizado": a.autorizado,
            "promocion_activa": a.promocion_activa, "referencia": a.referencia,
            "lineas": [[l.recurso_id, l.cantidad, str(l.precio_unitario)] for l in a.lineas],
            "anticipo_pagado": str(a.anticipo_pagado), "pago_liquidacion": str(a.pago_liquidacion),
            "reserva_expira_en": _iso(a.reserva_expira_en), "vence_en": _iso(a.vence_en),
            "comprobante": a.comprobante, "numeros_serie": a.numeros_serie})

    @staticmethod
    def de_json(aid, cid, estado, data) -> Apartado:
        d = json.loads(data)
        a = Apartado(aid, cid, d["sucursal_id"],
                     [LineaApartado(r, q, Decimal(p)) for r, q, p in d["lineas"]],
                     creado_en=_dt(d["creado_en"]), autorizado=d["autorizado"],
                     promocion_activa=d["promocion_activa"], referencia=d["referencia"])
        a.estado = EstadoApartado(estado)
        a.anticipo_pagado = Decimal(d["anticipo_pagado"])
        a.pago_liquidacion = Decimal(d["pago_liquidacion"])
        a.reserva_expira_en = _dt(d["reserva_expira_en"])
        a.vence_en = _dt(d["vence_en"])
        a.comprobante = d["comprobante"]
        a.numeros_serie = d["numeros_serie"]
        return a

    def guardar(self, a: Apartado):
        self._upsert("apartados", "apartado_id", ["apartado_id", "cliente_id", "estado", "data"],
                     (a.apartado_id, a.cliente_id, a.estado.value, self.a_json(a)))

    def obtener(self, apartado_id) -> Apartado:
        r = self._x("SELECT apartado_id,cliente_id,estado,data FROM apartados WHERE apartado_id=?", (apartado_id,)).fetchone()
        if not r:
            raise NoEncontradoError(f"Apartado {apartado_id} no encontrado.")
        return self.de_json(*r)

    def existe(self, apartado_id) -> bool:
        return self._x("SELECT 1 FROM apartados WHERE apartado_id=?", (apartado_id,)).fetchone() is not None

    def listar(self, cliente_id: Optional[str] = None, estado: Optional[str] = None) -> List[Apartado]:
        sql, p = "SELECT apartado_id,cliente_id,estado,data FROM apartados WHERE 1=1", []
        if cliente_id:
            sql += " AND cliente_id=?"; p.append(cliente_id)
        if estado:
            sql += " AND estado=?"; p.append(estado)
        return [self.de_json(*r) for r in self._x(sql + " ORDER BY apartado_id", p).fetchall()]

    def listar_por_estado(self, estados) -> List[Apartado]:
        out = []
        for e in estados:
            out += self.listar(estado=e.value if hasattr(e, "value") else e)
        return out

    def contar_articulos_activos(self, cliente_id: str, excluir: Optional[str] = None) -> int:
        """Artículos en reserva temporal o confirmados (ADR-04)."""
        total = 0
        for e in ACTIVOS:
            for a in self.listar(cliente_id=cliente_id, estado=e):
                if a.apartado_id != excluir:
                    total += a.articulos
        return total


class MonederosRepo(_Repo):
    def obtener_o_crear(self, cliente_id) -> Monedero:
        r = self._x("SELECT cliente_id,data FROM monederos WHERE cliente_id=?", (cliente_id,)).fetchone()
        if not r:
            return Monedero(cliente_id)
        d = json.loads(r[1])
        return Monedero(cliente_id, Decimal(d["saldo"]), {k: Decimal(v) for k, v in d["abonos"].items()})

    def guardar(self, m: Monedero):
        self._upsert("monederos", "cliente_id", ["cliente_id", "data"],
                     (m.cliente_id, json.dumps({"saldo": str(m.saldo), "abonos": {k: str(v) for k, v in m.abonos.items()}})))


class EventosRepo(_Repo):
    def registrar(self, e: EventoDeDominio):
        self._x("INSERT INTO eventos (id,ocurrido_en,tipo,payload) VALUES (?,?,?,?)",
                (f"{time.time_ns():020d}-{uuid.uuid4().hex[:6]}", e.ocurrido_en.isoformat(), e.tipo, json.dumps(e.a_dict())))

    def listar(self, limite: int = 200) -> List[dict]:
        rows = self._x("SELECT ocurrido_en,tipo,payload FROM eventos ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
        return [{"ocurrido_en": r[0], "tipo": r[1], "payload": json.loads(r[2])} for r in rows]

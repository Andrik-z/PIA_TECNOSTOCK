"""Importa los CSV del paquete del PIA a la BD (actores, catálogo, operaciones, detalle)."""
import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from src.domain.actor import Actor, Producto
from src.domain.apartado import Apartado, LineaApartado
from src.domain.inventario import Inventario


def leer(ruta: Path):
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def cargar_datos(uow_factory, data_dir, sucursal_id: str = "SUC-01") -> dict:
    d = Path(data_dir)
    with uow_factory() as uow:
        for r in leer(d / "actores.csv"):
            uow.actores.guardar(Actor(r["actor_id"], r["nombre"], r["es_preferente"] == "1",
                                      r["activo"] == "1", r["ciudad"]))
        inv = Inventario(sucursal_id)
        precios = {}
        for r in leer(d / "catalogo.csv"):
            p = Producto(r["recurso_id"], r["descripcion"], Decimal(r["precio_mxn"]), r["habilitado"] == "1")
            precios[p.recurso_id] = p.precio
            uow.productos.guardar(p)
            inv.registrar_producto(p.recurso_id, int(r["capacidad_o_stock"]))
        uow.inventarios.guardar(inv)
        detalle = {}
        for r in leer(d / "detalle_operaciones.csv"):
            detalle.setdefault(r["operacion_id"], []).append(
                LineaApartado(r["recurso_id"], int(r["cantidad"]), precios[r["recurso_id"]]))
        n = 0
        for r in leer(d / "operaciones.csv"):
            ap = Apartado(r["operacion_id"], r["actor_id"], sucursal_id, detalle.get(r["operacion_id"], []),
                          creado_en=datetime.fromisoformat(r["fecha_solicitud"]),
                          autorizado=r["autorizado"] == "1", promocion_activa=r["promocion_activa"] == "1",
                          referencia=r["referencia"])
            uow.apartados.guardar(ap)
            n += 1
    return {"actores": len(leer(d / "actores.csv")), "productos": len(precios), "operaciones": n}

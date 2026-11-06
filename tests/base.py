import os
import tempfile
import unittest
from datetime import datetime, timedelta

from src.domain.actor import Actor, Producto
from src.domain.inventario import Inventario
from src.tools_run_csv import construir
from decimal import Decimal

T0 = datetime(2026, 11, 6, 12, 0, 0)


class BaseConBD(unittest.TestCase):
    politica = None

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.url = f"sqlite:///{os.path.join(self._tmp.name, 't.db')}"
        self.svc, self.consultas = construir(self.url, self.politica)
        with self.svc.uow_factory() as uow:
            uow.actores.guardar(Actor("C1", "Ana", True, True, "MTY"))
            uow.actores.guardar(Actor("C2", "Beto", False, True, "MTY"))
            uow.actores.guardar(Actor("C4", "Dani", False, True, "MTY"))
            uow.actores.guardar(Actor("C3", "Inactivo", False, False, "MTY"))
            uow.productos.guardar(Producto("P1", "Laptop", Decimal("1000.00"), True))
            uow.productos.guardar(Producto("P2", "Mouse", Decimal("250.00"), True))
            uow.productos.guardar(Producto("P3", "Descontinuado", Decimal("90.00"), False))
            inv = Inventario("SUC-01")
            inv.registrar_producto("P1", 6)
            inv.registrar_producto("P2", 10)
            inv.registrar_producto("P3", 5)
            uow.inventarios.guardar(inv)

    def tearDown(self):
        self._tmp.cleanup()

    def disponible(self, rid):
        with self.svc.uow_factory() as uow:
            return uow.inventarios.obtener("SUC-01").disponible(rid)

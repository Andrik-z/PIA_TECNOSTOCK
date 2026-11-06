"""Pruebas de integración de la API (requieren fastapi + httpx; corren en CI/Docker)."""
import os
import tempfile
import unittest

try:
    from fastapi.testclient import TestClient
except Exception:  # pragma: no cover
    TestClient = None

from src.config import Settings


@unittest.skipIf(TestClient is None, "fastapi/httpx no instalados")
class TestAPI(unittest.TestCase):
    def setUp(self):
        from src.api.main import create_app
        self.tmp = tempfile.TemporaryDirectory()
        self.c = TestClient(create_app(Settings(database_url=f"sqlite:///{os.path.join(self.tmp.name, 'a.db')}",
                                                data_dir="data")))

    def tearDown(self):
        self.tmp.cleanup()

    def crear(self, cliente="TEC-C001", rid="TEC-P001", n=2, **kw):
        return self.c.post("/api/apartados", json={"cliente_id": cliente, "items": [{"recurso_id": rid, "cantidad": n}], **kw})

    def test_health_y_consultas(self):
        self.assertEqual(self.c.get("/health").status_code, 200)
        self.assertEqual(len(self.c.get("/api/productos").json()), 20)
        self.assertEqual(len(self.c.get("/api/actores").json()), 40)
        self.assertEqual(self.c.get("/api/productos/TEC-P001/disponibilidad").status_code, 200)
        self.assertEqual(self.c.get("/api/config").json()["limite_articulos"], 5)
        self.assertEqual(self.c.get("/").status_code, 200)

    def test_codigos_http(self):
        r = self.crear(apartado_id="X1")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.crear(n=0).status_code, 400)
        self.assertEqual(self.crear(cliente="NOPE").status_code, 404)
        self.assertEqual(self.crear(n=9).status_code, 422)                 # límite de 5
        self.assertEqual(self.crear(apartado_id="X1").status_code, 409)    # duplicado
        self.assertEqual(self.c.post("/api/apartados/X1/anticipo", json={"monto": "1"}).status_code, 422)
        self.assertEqual(self.c.post("/api/apartados/X1/liquidar", json={"monto": "1"}).status_code, 409)
        self.assertEqual(self.c.get("/api/apartados/NOPE").status_code, 404)
        self.assertEqual(self.c.post("/api/apartados", json={}).status_code, 422)   # validación pydantic

    def test_flujo_completo(self):
        a = self.crear(apartado_id="X2").json()
        self.assertEqual(a["estado"], "RESERVA_TEMPORAL")
        self.assertEqual(self.c.post("/api/apartados/X2/anticipo", json={"monto": a["anticipo_minimo"]}).json()["estado"], "CONFIRMADO")
        r = self.c.post("/api/apartados/X2/liquidar", json={"monto": self.c.get("/api/apartados/X2").json()["saldo"]})
        self.assertEqual(r.json()["estado"], "LIQUIDADO")
        self.assertEqual(self.c.post("/api/apartados/X2/entregar", json={"numeros_serie": ["S1", "S2"]}).json()["estado"], "ENTREGADO")
        self.assertTrue(self.c.get("/api/apartados/X2/evaluacion").json()["puede_procesarse"]["cumple"])
        self.assertGreater(len(self.c.get("/api/eventos").json()), 0)
        # El cliente ya trae operaciones BORRADOR de los CSV: se verifica que el apartado nuevo aparece.
        propios = self.c.get("/api/apartados", params={"cliente_id": "TEC-C001"}).json()
        self.assertIn(a["apartado_id"], [x["apartado_id"] for x in propios])

    def test_vencimiento_y_monedero(self):
        self.crear(apartado_id="X3")
        self.c.post("/api/apartados/X3/anticipo", json={"monto": "200"})
        r = self.c.post("/api/mantenimiento/vencimientos", json={"ahora": "2099-01-01T00:00:00"})
        self.assertEqual(r.json()["apartados_vencidos"], ["X3"])
        self.assertEqual(self.c.get("/api/monederos/TEC-C001").json()["saldo"], "200.00")

    def test_borrador_csv_reservar_cancelar_y_pruebas(self):
        self.assertEqual(self.c.post("/api/apartados/TEC-O002/reservar").status_code in (200, 422), True)
        self.assertEqual(self.c.post("/api/apartados/TEC-O003/cancelar").json()["estado"], "CANCELADO")
        self.assertEqual(self.c.post("/api/mantenimiento/cargar-csv").json()["operaciones"], 60)
        r = self.c.post("/api/pruebas/ejecutar").json()
        self.assertEqual((len(r["casos"]), len(r["transiciones"])), (120, 20))

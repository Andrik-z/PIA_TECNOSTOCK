import tempfile
import os
from datetime import timedelta
from decimal import Decimal

from src.application.apartado_service import ConsultasService
from src.application.pruebas_csv import ejecutar_casos, ejecutar_transiciones, escribir_csv
from src.domain.errores import (ConflictoError, NoEncontradoError, ReglaNegocioError,
                                TransicionInvalidaError, ValidacionError)
from src.domain.estados import EstadoApartado
from src.infrastructure.carga_csv import cargar_datos
from src.infrastructure.unit_of_work import UnitOfWork
from tests.base import BaseConBD, T0


class TestCasosDeUso(BaseConBD):
    def test_cu01_disponibilidad(self):                      # US-01 / US-02
        d = self.consultas.disponibilidad_global("P1")
        self.assertEqual(d["total_disponible"], 6)
        self.assertEqual(len(self.consultas.productos()), 3)
        self.assertEqual(len(self.consultas.actores()), 4)
        with self.assertRaises(NoEncontradoError):
            self.consultas.disponibilidad_global("NOPE")

    def test_cu02_iniciar_apartado_bloquea_stock(self):      # US-08
        a = self.svc.iniciar_apartado("C1", [{"recurso_id": "P1", "cantidad": 2}], ahora=T0)
        self.assertEqual(a.estado, EstadoApartado.RESERVA_TEMPORAL)
        self.assertEqual(self.disponible("P1"), 4)
        self.assertEqual(self.svc.acciones_validas(a), ["confirmar", "expirar", "cancelar"])

    def test_limite_5_global_por_cliente(self):              # ADR-04
        self.svc.iniciar_apartado("C1", [{"recurso_id": "P2", "cantidad": 3}], ahora=T0)
        with self.assertRaisesRegex(ReglaNegocioError, "Límite"):
            self.svc.iniciar_apartado("C1", [{"recurso_id": "P2", "cantidad": 3}], ahora=T0)
        self.assertEqual(self.disponible("P2"), 7)           # rollback: nada quedó bloqueado
        self.svc.iniciar_apartado("C1", [{"recurso_id": "P2", "cantidad": 2}], ahora=T0)
        self.svc.iniciar_apartado("C2", [{"recurso_id": "P2", "cantidad": 5}], ahora=T0)

    def test_rechazos_de_creacion(self):
        casos = [(NoEncontradoError, "NOPE", [{"recurso_id": "P1", "cantidad": 1}]),
                 (NoEncontradoError, "C1", [{"recurso_id": "NOPE", "cantidad": 1}]),
                 (ValidacionError, "C1", []),
                 (ValidacionError, "C1", [{"recurso_id": "P1", "cantidad": 0}]),
                 (ReglaNegocioError, "C1", [{"recurso_id": "P3", "cantidad": 1}]),
                 (ReglaNegocioError, "C3", [{"recurso_id": "P1", "cantidad": 1}]),
                 (ReglaNegocioError, "C1", [{"recurso_id": "P1", "cantidad": 6}])]
        for exc, cliente, items in casos:
            with self.subTest(cliente=cliente, items=items), self.assertRaises(exc):
                self.svc.iniciar_apartado(cliente, items, ahora=T0)
        self.assertEqual(self.disponible("P1"), 6)

    def test_stock_insuficiente_409(self):
        self.svc.iniciar_apartado("C1", [{"recurso_id": "P1", "cantidad": 5}], ahora=T0)
        with self.assertRaises(ConflictoError):
            self.svc.iniciar_apartado("C2", [{"recurso_id": "P1", "cantidad": 2}], ahora=T0)
        self.assertEqual(self.disponible("P1"), 1)

    def test_id_duplicado(self):
        self.svc.iniciar_apartado("C1", [{"recurso_id": "P1", "cantidad": 1}], apartado_id="X", ahora=T0)
        with self.assertRaises(ConflictoError):
            self.svc.iniciar_apartado("C1", [{"recurso_id": "P1", "cantidad": 1}], apartado_id="X", ahora=T0)

    def test_no_se_vende_lo_apartado(self):                  # BRD 5.2
        self.svc.iniciar_apartado("C1", [{"recurso_id": "P1", "cantidad": 5}], ahora=T0)
        self.svc.iniciar_apartado("C2", [{"recurso_id": "P1", "cantidad": 1}], ahora=T0)
        with self.assertRaises(ConflictoError):      # ya no queda nada disponible
            self.svc.iniciar_apartado("C4", [{"recurso_id": "P1", "cantidad": 1}], ahora=T0)

    def test_flujo_completo_y_salida_fisica(self):           # CU-02,03,05
        a = self.svc.iniciar_apartado("C1", [{"recurso_id": "P1", "cantidad": 2}], apartado_id="A1", ahora=T0)
        self.svc.confirmar_anticipo("A1", "400", T0 + timedelta(minutes=5))
        self.svc.liquidar("A1", "1600", T0 + timedelta(days=3))
        self.svc.entregar("A1", ["S1", "S2"], T0 + timedelta(days=4))
        with self.svc.uow_factory() as uow:
            inv = uow.inventarios.obtener("SUC-01")
        self.assertEqual((inv.disponible("P1"), inv.apartada("P1"), inv.vendida("P1")), (4, 0, 2))
        self.assertEqual(self.svc.obtener("A1").numeros_serie, ["S1", "S2"])
        tipos = [e["tipo"] for e in self.consultas.eventos()]
        self.assertIn("SalidaFisicaRegistrada", tipos)
        with self.assertRaises(TransicionInvalidaError):     # salida física una sola vez
            self.svc.entregar("A1", ["S1", "S2"], T0)

    def test_us09_reserva_expirada_libera(self):
        self.svc.iniciar_apartado("C1", [{"recurso_id": "P1", "cantidad": 2}], apartado_id="A1", ahora=T0)
        r = self.svc.procesar_vencimientos(T0 + timedelta(minutes=14))
        self.assertEqual(r["reservas_expiradas"], [])
        r = self.svc.procesar_vencimientos(T0 + timedelta(minutes=16))
        self.assertEqual(r["reservas_expiradas"], ["A1"])
        self.assertEqual(self.disponible("P1"), 6)
        self.assertEqual(self.svc.obtener("A1").estado, EstadoApartado.CANCELADO)

    def test_pago_tardio_cancela_y_rechaza(self):
        self.svc.iniciar_apartado("C1", [{"recurso_id": "P1", "cantidad": 2}], apartado_id="A1", ahora=T0)
        with self.assertRaisesRegex(ReglaNegocioError, "ReservaExpirada"):
            self.svc.confirmar_anticipo("A1", "400", T0 + timedelta(minutes=20))
        self.assertEqual(self.svc.obtener("A1").estado, EstadoApartado.CANCELADO)
        self.assertEqual(self.disponible("P1"), 6)

    def test_anticipo_insuficiente_no_cambia_nada(self):
        self.svc.iniciar_apartado("C1", [{"recurso_id": "P1", "cantidad": 2}], apartado_id="A1", ahora=T0)
        with self.assertRaisesRegex(ReglaNegocioError, "AnticipoInsuficiente"):
            self.svc.confirmar_anticipo("A1", "100", T0)
        self.assertEqual(self.svc.obtener("A1").estado, EstadoApartado.RESERVA_TEMPORAL)

    def test_us12_vencimiento_monedero_idempotente(self):
        self.svc.iniciar_apartado("C1", [{"recurso_id": "P1", "cantidad": 2}], apartado_id="A1", ahora=T0)
        self.svc.confirmar_anticipo("A1", "500", T0)
        r = self.svc.procesar_vencimientos(T0 + timedelta(days=31))
        self.assertEqual(r["apartados_vencidos"], ["A1"])
        self.assertEqual(self.disponible("P1"), 6)
        self.assertEqual(self.consultas.monedero("C1").saldo, Decimal("500.00"))
        self.svc.procesar_vencimientos(T0 + timedelta(days=40))   # no vuelve a abonar
        self.assertEqual(self.consultas.monedero("C1").saldo, Decimal("500.00"))
        self.assertIn("SaldoAFavorGenerado", [e["tipo"] for e in self.consultas.eventos()])
        with self.assertRaises(NoEncontradoError):
            self.consultas.monedero("NOPE")

    def test_cancelar_libera_stock(self):
        self.svc.iniciar_apartado("C1", [{"recurso_id": "P1", "cantidad": 2}], apartado_id="A1", ahora=T0)
        self.svc.cancelar("A1", T0)
        self.assertEqual(self.disponible("P1"), 6)
        with self.assertRaises(TransicionInvalidaError):
            self.svc.cancelar("A1", T0)
        with self.assertRaises(NoEncontradoError):
            self.svc.cancelar("NOPE")

    def test_evaluar_y_listar(self):
        self.svc.iniciar_apartado("C1", [{"recurso_id": "P1", "cantidad": 2}], apartado_id="A1", ahora=T0)
        ev = self.svc.evaluar("A1")
        self.assertTrue(ev["puede_procesarse"]["cumple"])
        self.assertTrue(ev["beneficio_referencia"]["cumple"])    # C1 preferente, 2000 >= 1500
        self.assertEqual(len(self.svc.listar("C1")), 1)
        self.assertEqual(len(self.svc.listar(estado="CONFIRMADO")), 0)

    def test_reservar_borrador_y_rollback_uow(self):
        with self.svc.uow_factory() as uow:
            from src.domain.apartado import Apartado
            uow.apartados.guardar(Apartado("B1", "C3", "SUC-01", []))
        with self.assertRaises(ReglaNegocioError):
            self.svc.reservar("B1", T0)
        with self.assertRaises(RuntimeError):
            with UnitOfWork(self.svc.uow_factory().db) as uow:
                from src.domain.apartado import Apartado
                uow.apartados.guardar(Apartado("B2", "C1", "SUC-01", []))
                raise RuntimeError("boom")
        self.assertEqual([a.apartado_id for a in self.svc.listar()], ["B1"])


class TestCargaYCsv(BaseConBD):
    def test_runner_csv(self):
        from src.application.pruebas_csv import politica_modelo_de_pruebas
        from src.tools_run_csv import construir
        with tempfile.TemporaryDirectory() as t:
            svc, _ = construir(f"sqlite:///{os.path.join(t, 'c.db')}", politica_modelo_de_pruebas())
            r = cargar_datos(svc.uow_factory, "data")
            self.assertEqual(r, {"actores": 40, "productos": 20, "operaciones": 60})
            casos = ejecutar_casos(svc, "data")
            self.assertEqual(len(casos), 120)
            self.assertTrue(all(c["resultado_alumno"] != "PENDIENTE" for c in casos))
            trans = ejecutar_transiciones(svc, "data")
            self.assertEqual(len(trans), 20)
            self.assertTrue(any("TransicionInvalidaError" in f["resultado_alumno"] for f in trans))
            escribir_csv(trans, os.path.join(t, "o", "x.csv"))
            self.assertTrue(os.path.exists(os.path.join(t, "o", "x.csv")))

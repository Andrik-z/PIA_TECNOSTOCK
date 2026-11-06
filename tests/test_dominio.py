import unittest
from datetime import timedelta
from decimal import Decimal

from src.domain.actor import Actor, Producto
from src.domain.apartado import Apartado, LineaApartado
from src.domain.errores import (ConflictoError, NoEncontradoError, ReglaNegocioError,
                                TransicionInvalidaError, ValidacionError)
from src.domain.estados import Accion, EstadoApartado, MAQUINA_APARTADO
from src.domain.inventario import Inventario
from src.domain.monedero import Monedero
from src.domain.politicas import PoliticaApartado
from src.domain.specifications import (ActorActivo, AnticipoMinimo, Contexto, MaximoArticulosPorCliente,
                                       OperacionConLineas, PromocionActiva, beneficio_referencia, explicar,
                                       puede_procesarse)
from tests.base import T0

ANA = Actor("C1", "Ana", True, True)


def ap(qty=2, precio="1000.00", **kw):
    return Apartado("A1", "C1", "SUC-01", [LineaApartado("P1", qty, Decimal(precio))], **kw)


class TestSpecifications(unittest.TestCase):          # US-08
    def test_puede_procesarse_and(self):
        c = Contexto(actor=ANA, apartado=ap())
        self.assertTrue(puede_procesarse().is_satisfied_by(c))
        c.actor = Actor("x", "x", False, False)
        self.assertFalse(puede_procesarse().is_satisfied_by(c))
        self.assertFalse(puede_procesarse().is_satisfied_by(Contexto(actor=ANA, apartado=ap(autorizado=False))))
        self.assertFalse(puede_procesarse().is_satisfied_by(
            Contexto(actor=ANA, apartado=Apartado("A", "C1", "S"))))

    def test_beneficio_and_not(self):
        self.assertTrue(beneficio_referencia().is_satisfied_by(Contexto(actor=ANA, apartado=ap())))
        self.assertFalse(beneficio_referencia().is_satisfied_by(
            Contexto(actor=ANA, apartado=ap(promocion_activa=True))))
        self.assertFalse(beneficio_referencia().is_satisfied_by(
            Contexto(actor=ANA, apartado=ap(qty=1, precio="1499.99"))))
        self.assertTrue(beneficio_referencia().is_satisfied_by(
            Contexto(actor=ANA, apartado=ap(qty=1, precio="1500.00"))))

    def test_or_y_explicar(self):
        spec = ActorActivo() | PromocionActiva()
        c = Contexto(actor=Actor("x", "x", False, False), apartado=ap(promocion_activa=True))
        self.assertTrue(spec.is_satisfied_by(c))
        self.assertEqual(explicar(spec, c), {"actor_activo": False, "promocion_activa": True})
        self.assertIn("OR", spec.nombre)

    def test_limite_articulos(self):
        c = Contexto(actor=ANA, apartado=ap(qty=2), articulos_activos=3)
        self.assertTrue(MaximoArticulosPorCliente().is_satisfied_by(c))
        c.articulos_activos = 4
        self.assertFalse(MaximoArticulosPorCliente().is_satisfied_by(c))
        c.politica = PoliticaApartado(limite_articulos=None)
        self.assertTrue(MaximoArticulosPorCliente().is_satisfied_by(c))

    def test_anticipo_minimo(self):
        a = ap()  # total 2000 -> minimo 400
        self.assertFalse(AnticipoMinimo().is_satisfied_by(Contexto(apartado=a, monto_anticipo=Decimal("399.99"))))
        self.assertTrue(AnticipoMinimo().is_satisfied_by(Contexto(apartado=a, monto_anticipo=Decimal("400"))))
        self.assertFalse(AnticipoMinimo().is_satisfied_by(Contexto(apartado=a)))
        self.assertFalse(OperacionConLineas().is_satisfied_by(Contexto(apartado=Apartado("z", "c", "s"))))


class TestMaquinaEstados(unittest.TestCase):            # BRD 5.2, US-09..US-12
    def test_flujo_feliz(self):
        a = ap()
        a.reservar(T0, ANA, 0)
        self.assertEqual(a.estado, EstadoApartado.RESERVA_TEMPORAL)
        a.confirmar_anticipo("400", T0 + timedelta(minutes=14))
        self.assertEqual(a.vence_en, T0 + timedelta(minutes=14, days=30))
        a.liquidar(a.saldo, T0 + timedelta(days=5))
        self.assertEqual(a.comprobante["folio"], "TKT-A1")
        a.entregar(["S1", "S2"], T0 + timedelta(days=6))
        self.assertEqual(a.estado, EstadoApartado.ENTREGADO)
        self.assertEqual([e.tipo for e in a.pull_events()],
                         ["ReservaTemporalCreada", "ApartadoConfirmado", "ApartadoLiquidado", "SalidaFisicaRegistrada"])
        self.assertEqual(a.pull_events(), [])

    def test_transiciones_invalidas(self):
        a = ap()
        for fn in (lambda: a.liquidar(0, T0), lambda: a.confirmar_anticipo(400, T0),
                   lambda: a.entregar(["a", "b"], T0)):
            with self.assertRaises(TransicionInvalidaError):
                fn()
        a.reservar(T0, ANA, 0)
        with self.assertRaises(TransicionInvalidaError):
            a.reservar(T0, ANA, 0)
        self.assertEqual(sorted(MAQUINA_APARTADO.acciones_validas(EstadoApartado.RESERVA_TEMPORAL)),
                         ["cancelar", "confirmar", "expirar"])

    def test_reserva_y_anticipo_reglas(self):
        a = ap(); a.reservar(T0, ANA, 0)
        with self.assertRaisesRegex(ReglaNegocioError, "AnticipoInsuficiente"):
            a.confirmar_anticipo("399.99", T0)
        with self.assertRaises(ValidacionError):
            a.confirmar_anticipo("-1", T0)
        with self.assertRaises(ValidacionError):
            a.confirmar_anticipo("2000.01", T0)
        with self.assertRaises(ValidacionError):
            a.confirmar_anticipo("abc", T0)
        with self.assertRaisesRegex(ReglaNegocioError, "ReservaExpirada"):
            a.confirmar_anticipo("400", T0 + timedelta(minutes=15))

    def test_reservar_rechazos(self):
        with self.assertRaisesRegex(ReglaNegocioError, "actor_activo"):
            ap().reservar(T0, Actor("x", "x", False, False), 0)
        with self.assertRaisesRegex(ReglaNegocioError, "Límite"):
            ap(qty=2).reservar(T0, ANA, 4)

    def test_liquidar_reglas(self):
        a = ap(); a.reservar(T0, ANA, 0); a.confirmar_anticipo("400", T0)
        with self.assertRaisesRegex(ReglaNegocioError, "saldo completo"):
            a.liquidar("100", T0)
        with self.assertRaisesRegex(ReglaNegocioError, "ApartadoVencido"):
            a.liquidar("1600", a.vence_en)

    def test_expirar_y_vencer(self):
        a = ap(); a.reservar(T0, ANA, 0)
        self.assertFalse(a.expirar_reserva(T0 + timedelta(minutes=14)))
        self.assertTrue(a.expirar_reserva(T0 + timedelta(minutes=15)))
        self.assertEqual(a.estado, EstadoApartado.CANCELADO)
        b = ap(); b.reservar(T0, ANA, 0); b.confirmar_anticipo("400", T0)
        self.assertFalse(b.vencer(T0 + timedelta(days=29)))
        self.assertTrue(b.vencer(T0 + timedelta(days=30)))
        self.assertEqual(b.estado, EstadoApartado.VENCIDO)
        self.assertFalse(b.vencer(T0 + timedelta(days=31)))

    def test_cancelar(self):
        a = ap(); a.cancelar(T0)
        self.assertEqual(a.pull_events()[0].estaba_reservado, False)
        b = ap(); b.reservar(T0, ANA, 0); b.cancelar(T0)
        self.assertTrue(b.pull_events()[-1].estaba_reservado)
        with self.assertRaises(TransicionInvalidaError):
            b.cancelar(T0)

    def test_entrega_series(self):
        a = ap(); a.reservar(T0, ANA, 0); a.confirmar_anticipo("400", T0); a.liquidar("1600", T0)
        with self.assertRaises(ValidacionError):
            a.entregar(["S1"], T0)
        with self.assertRaises(ValidacionError):
            a.entregar(["S1", "S1"], T0)

    def test_lineas_validas(self):
        with self.assertRaises(ValidacionError):
            LineaApartado("P1", 0, Decimal("1"))
        with self.assertRaises(ValidacionError):
            LineaApartado("P1", 1.5, Decimal("1"))
        with self.assertRaises(ValidacionError):
            LineaApartado("P1", 1, Decimal("0"))
        with self.assertRaises(ValidacionError):
            Producto("P", "x", Decimal("0"))
        a = ap(qty=1); a.agregar_linea(LineaApartado("P1", 2, Decimal("1000")))
        self.assertEqual(a.articulos, 3)
        a.reservar(T0, ANA, 0)
        with self.assertRaises(ConflictoError):
            a.agregar_linea(LineaApartado("P2", 1, Decimal("1")))

    def test_total_decimal_exacto(self):
        a = Apartado("A", "C", "S", [LineaApartado("P", 3, Decimal("0.10"))])
        self.assertEqual(a.total, Decimal("0.30"))
        self.assertEqual(a.anticipo_minimo(), Decimal("0.06"))


class TestInventarioMonedero(unittest.TestCase):          # BRD 5.2: nunca vender lo apartado
    def inv(self):
        i = Inventario("S"); i.registrar_producto("P1", 3); return i

    def test_apartar_liberar_vender(self):
        i = self.inv()
        i.apartar("A", {"P1": 2})
        self.assertEqual((i.disponible("P1"), i.apartada("P1")), (1, 2))
        with self.assertRaisesRegex(ConflictoError, "insuficiente"):
            i.apartar("B", {"P1": 2})
        with self.assertRaises(ConflictoError):
            i.apartar("A", {"P1": 1})
        self.assertTrue(i.liberar("A")); self.assertFalse(i.liberar("A"))
        i.apartar("C", {"P1": 3}); i.descontar_por_venta("C")
        self.assertEqual((i.disponible("P1"), i.vendida("P1")), (0, 3))
        with self.assertRaises(ConflictoError):
            i.descontar_por_venta("C")

    def test_errores(self):
        i = self.inv()
        with self.assertRaises(NoEncontradoError):
            i.disponible("X")
        with self.assertRaises(ValidacionError):
            i.apartar("A", {"P1": 0})
        with self.assertRaises(ValidacionError):
            i.registrar_producto("P2", -1)

    def test_monedero_idempotente(self):
        m = Monedero("C1")
        self.assertIsNotNone(m.abonar_anticipo("A", Decimal("400"), T0))
        self.assertIsNone(m.abonar_anticipo("A", Decimal("400"), T0))
        self.assertEqual(m.saldo, Decimal("400.00"))
        m.descontar("100"); self.assertEqual(m.saldo, Decimal("300.00"))
        with self.assertRaises(ReglaNegocioError):
            m.descontar("301")
        with self.assertRaises(ValidacionError):
            m.descontar("0")
        with self.assertRaises(ValidacionError):
            m.abonar_anticipo("B", 0, T0)


if __name__ == "__main__":
    unittest.main()

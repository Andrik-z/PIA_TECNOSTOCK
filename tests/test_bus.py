import unittest
from datetime import datetime

from src.application.eventos import EventBus
from src.domain.eventos import ApartadoCancelado


class TestBus(unittest.TestCase):
    def test_handler_fallido_no_rompe(self):
        bus, vistos = EventBus(), []
        def malo(e): raise RuntimeError("x")
        bus.suscribir(ApartadoCancelado, malo)
        bus.suscribir(ApartadoCancelado, lambda e: vistos.append(e.tipo))
        with self.assertLogs("tecnostock.eventos", level="ERROR"):
            bus.publicar([ApartadoCancelado(datetime.now(), "A", True)])
        self.assertEqual(vistos, ["ApartadoCancelado"])
        d = ApartadoCancelado(datetime(2026, 1, 1), "A", False).a_dict()
        self.assertEqual(d["ocurrido_en"], "2026-01-01T00:00:00")

"""Reacciones a eventos: cada una corre en su propia transacción."""
from src.domain.eventos import (ApartadoCancelado, ApartadoVencido, ReservaTemporalExpirada)


def registrar_handlers(bus, uow_factory):
    def bitacora(e):
        with uow_factory() as uow:
            uow.eventos.registrar(e)

    def liberar_stock(e):
        if isinstance(e, ApartadoCancelado) and not e.estaba_reservado:
            return
        with uow_factory() as uow:
            ap = uow.apartados.obtener(e.apartado_id)
            inv = uow.inventarios.obtener(ap.sucursal_id)
            if inv.liberar(e.apartado_id):
                uow.inventarios.guardar(inv)

    def abonar_monedero(e: ApartadoVencido):
        with uow_factory() as uow:
            m = uow.monederos.obtener_o_crear(e.cliente_id)
            ev = m.abonar_anticipo(e.apartado_id, e.anticipo, e.ocurrido_en)
            uow.monederos.guardar(m)
        return [ev] if ev else []

    bus.suscribir("*", bitacora)
    for t in (ReservaTemporalExpirada, ApartadoCancelado, ApartadoVencido):
        bus.suscribir(t, liberar_stock)
    bus.suscribir(ApartadoVencido, abonar_monedero)

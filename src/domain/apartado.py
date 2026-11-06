"""Aggregate Root Apartado (en el modelo de pruebas del PIA: 'operación')."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from .dinero import dinero, redondear_arriba
from .errores import ConflictoError, ReglaNegocioError, ValidacionError
from .estados import Accion, EstadoApartado, MAQUINA_APARTADO
from .eventos import (ApartadoCancelado, ApartadoConfirmado, ApartadoLiquidado, ApartadoVencido,
                      EventoDeDominio, ReservaTemporalCreada, ReservaTemporalExpirada,
                      SalidaFisicaRegistrada)
from .politicas import PoliticaApartado
from .specifications import (AnticipoMinimo, Contexto, MaximoArticulosPorCliente, explicar,
                             puede_procesarse)


@dataclass(frozen=True)
class LineaApartado:
    recurso_id: str
    cantidad: int
    precio_unitario: Decimal

    def __post_init__(self):
        if not isinstance(self.cantidad, int) or isinstance(self.cantidad, bool) or self.cantidad <= 0:
            raise ValidacionError("La cantidad debe ser un entero mayor a cero.")
        if Decimal(self.precio_unitario) <= 0:
            raise ValidacionError("El precio unitario debe ser mayor a cero.")

    @property
    def subtotal(self) -> Decimal:
        return dinero(Decimal(self.precio_unitario) * self.cantidad)


class Apartado:
    def __init__(self, apartado_id: str, cliente_id: str, sucursal_id: str,
                 lineas: Optional[List[LineaApartado]] = None, creado_en: Optional[datetime] = None,
                 autorizado: bool = True, promocion_activa: bool = False, referencia: str = ""):
        self.apartado_id = apartado_id
        self.cliente_id = cliente_id
        self.sucursal_id = sucursal_id
        self.lineas: List[LineaApartado] = []
        for l in lineas or []:
            self.agregar_linea(l)
        self.estado = EstadoApartado.BORRADOR
        self.creado_en = creado_en or datetime.now(timezone.utc).replace(tzinfo=None)
        self.autorizado = autorizado
        self.promocion_activa = promocion_activa
        self.referencia = referencia
        self.anticipo_pagado = Decimal("0.00")
        self.pago_liquidacion = Decimal("0.00")
        self.reserva_expira_en: Optional[datetime] = None
        self.vence_en: Optional[datetime] = None
        self.comprobante: Optional[Dict[str, str]] = None
        self.numeros_serie: List[str] = []
        self._eventos: List[EventoDeDominio] = []

    # ---- consultas ----
    @property
    def total(self) -> Decimal:
        return dinero(sum((l.subtotal for l in self.lineas), Decimal("0")))

    @property
    def articulos(self) -> int:
        return sum(l.cantidad for l in self.lineas)

    def anticipo_minimo(self, politica: PoliticaApartado = PoliticaApartado()) -> Decimal:
        return redondear_arriba(self.total * politica.porcentaje_anticipo)

    @property
    def saldo(self) -> Decimal:
        return dinero(self.total - self.anticipo_pagado - self.pago_liquidacion)

    def pull_events(self) -> List[EventoDeDominio]:
        ev, self._eventos = self._eventos, []
        return ev

    # ---- comportamiento ----
    def agregar_linea(self, linea: LineaApartado) -> None:
        if self.estado_es_borrador_o_nuevo():
            for i, l in enumerate(self.lineas):
                if l.recurso_id == linea.recurso_id:
                    self.lineas[i] = LineaApartado(l.recurso_id, l.cantidad + linea.cantidad, l.precio_unitario)
                    return
            self.lineas.append(linea)
        else:
            raise ConflictoError("Solo se pueden modificar líneas de un borrador.")

    def estado_es_borrador_o_nuevo(self) -> bool:
        return getattr(self, "estado", EstadoApartado.BORRADOR) == EstadoApartado.BORRADOR

    def reservar(self, ahora: datetime, actor, articulos_activos_cliente: int,
                 politica: PoliticaApartado = PoliticaApartado()) -> None:
        """US-08: valida reglas y abre la reserva temporal de 15 min."""
        ctx = Contexto(actor=actor, apartado=self, articulos_activos=articulos_activos_cliente,
                       politica=politica)
        spec = puede_procesarse()
        if not spec.is_satisfied_by(ctx):
            fallas = [k for k, v in explicar(spec, ctx).items() if not v]
            raise ReglaNegocioError(f"La operación no puede procesarse: incumple {', '.join(fallas)}.")
        if not MaximoArticulosPorCliente().is_satisfied_by(ctx):
            raise ReglaNegocioError(
                f"Límite de {politica.limite_articulos} artículos por cliente excedido "
                f"(activos: {articulos_activos_cliente}, nuevos: {self.articulos}).")
        nuevo = MAQUINA_APARTADO.siguiente(self.estado, Accion.RESERVAR)
        self.estado = nuevo
        self.reserva_expira_en = ahora + timedelta(minutes=politica.minutos_reserva)
        self._eventos.append(ReservaTemporalCreada(ahora, self.apartado_id, self.cliente_id,
                                                   self.reserva_expira_en))

    def confirmar_anticipo(self, monto, ahora: datetime, politica: PoliticaApartado = PoliticaApartado()) -> None:
        """US-10: anticipo >= 20% dentro de la reserva temporal."""
        nuevo = MAQUINA_APARTADO.siguiente(self.estado, Accion.CONFIRMAR)
        monto = self._monto(monto)
        if ahora >= self.reserva_expira_en:
            raise ReglaNegocioError("ReservaExpirada: pasaron más de 15 minutos sin pagar el anticipo.")
        if monto > self.total:
            raise ValidacionError("El anticipo no puede exceder el total del apartado.")
        if not AnticipoMinimo().is_satisfied_by(Contexto(apartado=self, monto_anticipo=monto, politica=politica)):
            raise ReglaNegocioError(
                f"AnticipoInsuficiente: se requiere al menos {self.anticipo_minimo(politica)} MXN "
                f"({politica.porcentaje_anticipo * 100:.0f}% de {self.total}).")
        self.anticipo_pagado = monto
        self.estado = nuevo
        self.vence_en = ahora + timedelta(days=politica.dias_vigencia)
        self._eventos.append(ApartadoConfirmado(ahora, self.apartado_id, monto, self.vence_en))

    def liquidar(self, monto, ahora: datetime) -> None:
        """US-11: pago del saldo completo antes del vencimiento; genera ticket QR."""
        nuevo = MAQUINA_APARTADO.siguiente(self.estado, Accion.LIQUIDAR)
        monto = self._monto(monto)
        if ahora >= self.vence_en:
            raise ReglaNegocioError("ApartadoVencido: ya pasó el plazo para liquidar.")
        if monto != self.saldo:
            raise ReglaNegocioError(f"La liquidación debe cubrir el saldo completo: {self.saldo} MXN.")
        self.pago_liquidacion = monto
        self.estado = nuevo
        folio = f"TKT-{self.apartado_id}"
        self.comprobante = {"folio": folio, "codigo_qr": f"QR|{self.apartado_id}|{self.total}"}
        self._eventos.append(ApartadoLiquidado(ahora, self.apartado_id, self.total, folio,
                                               self.comprobante["codigo_qr"]))

    def entregar(self, numeros_serie: List[str], ahora: datetime) -> None:
        """US-15/16: una serie única por unidad; salida física una sola vez."""
        nuevo = MAQUINA_APARTADO.siguiente(self.estado, Accion.ENTREGAR)
        series = [s.strip() for s in numeros_serie if s and s.strip()]
        if len(series) != self.articulos:
            raise ValidacionError(f"Se requieren {self.articulos} números de serie (uno por unidad).")
        if len(set(series)) != len(series):
            raise ValidacionError("Los números de serie no pueden repetirse.")
        self.numeros_serie = series
        self.estado = nuevo
        self._eventos.append(SalidaFisicaRegistrada(ahora, self.apartado_id, tuple(series)))

    def cancelar(self, ahora: datetime) -> None:
        estaba_reservado = self.estado == EstadoApartado.RESERVA_TEMPORAL
        self.estado = MAQUINA_APARTADO.siguiente(self.estado, Accion.CANCELAR)
        self._eventos.append(ApartadoCancelado(ahora, self.apartado_id, estaba_reservado))

    def expirar_reserva(self, ahora: datetime) -> bool:
        """US-09: a los 15 min sin pago se cancela y se libera el stock."""
        if self.estado != EstadoApartado.RESERVA_TEMPORAL or ahora < self.reserva_expira_en:
            return False
        self.estado = MAQUINA_APARTADO.siguiente(self.estado, Accion.EXPIRAR)
        self._eventos.append(ReservaTemporalExpirada(ahora, self.apartado_id))
        return True

    def vencer(self, ahora: datetime) -> bool:
        """US-12: a los 30 días sin liquidar vence; el anticipo pasa al monedero."""
        if self.estado != EstadoApartado.CONFIRMADO or ahora < self.vence_en:
            return False
        self.estado = MAQUINA_APARTADO.siguiente(self.estado, Accion.VENCER)
        self._eventos.append(ApartadoVencido(ahora, self.apartado_id, self.cliente_id, self.anticipo_pagado))
        return True

    @staticmethod
    def _monto(valor) -> Decimal:
        try:
            m = dinero(valor)
        except Exception:
            raise ValidacionError("Monto inválido.")
        if m < 0:
            raise ValidacionError("El monto no puede ser negativo.")
        return m

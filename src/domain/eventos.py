"""Domain Events: hechos inmutables nombrados en pasado."""
from dataclasses import dataclass, fields
from datetime import datetime
from decimal import Decimal
from typing import Tuple


@dataclass(frozen=True)
class EventoDeDominio:
    ocurrido_en: datetime

    @property
    def tipo(self) -> str:
        return type(self).__name__

    def a_dict(self) -> dict:
        out = {}
        for f in fields(self):
            v = getattr(self, f.name)
            if isinstance(v, datetime):
                v = v.isoformat()
            elif isinstance(v, Decimal):
                v = str(v)
            elif isinstance(v, tuple):
                v = list(v)
            out[f.name] = v
        return out


@dataclass(frozen=True)
class ReservaTemporalCreada(EventoDeDominio):
    apartado_id: str
    cliente_id: str
    expira_en: datetime


@dataclass(frozen=True)
class ReservaTemporalExpirada(EventoDeDominio):
    apartado_id: str


@dataclass(frozen=True)
class ApartadoConfirmado(EventoDeDominio):
    apartado_id: str
    anticipo: Decimal
    vence_en: datetime


@dataclass(frozen=True)
class ApartadoLiquidado(EventoDeDominio):
    apartado_id: str
    total: Decimal
    folio: str
    codigo_qr: str


@dataclass(frozen=True)
class ApartadoVencido(EventoDeDominio):
    apartado_id: str
    cliente_id: str
    anticipo: Decimal


@dataclass(frozen=True)
class ApartadoCancelado(EventoDeDominio):
    apartado_id: str
    estaba_reservado: bool


@dataclass(frozen=True)
class SalidaFisicaRegistrada(EventoDeDominio):
    apartado_id: str
    numeros_serie: Tuple[str, ...]


@dataclass(frozen=True)
class SaldoAFavorGenerado(EventoDeDominio):
    cliente_id: str
    apartado_id: str
    monto: Decimal

from decimal import Decimal
from typing import Dict, Optional

from .dinero import dinero
from .errores import ReglaNegocioError, ValidacionError
from .eventos import SaldoAFavorGenerado


class Monedero:
    """Saldo a favor del cliente. Abona una sola vez por apartado (idempotente)."""

    def __init__(self, cliente_id: str, saldo: Decimal = Decimal("0.00"),
                 abonos: Optional[Dict[str, Decimal]] = None):
        self.cliente_id = cliente_id
        self.saldo = dinero(saldo)
        self.abonos: Dict[str, Decimal] = dict(abonos or {})

    def abonar_anticipo(self, apartado_id: str, monto: Decimal, ahora) -> Optional[SaldoAFavorGenerado]:
        monto = dinero(monto)
        if monto <= 0:
            raise ValidacionError("El abono debe ser mayor a cero.")
        if apartado_id in self.abonos:
            return None
        self.abonos[apartado_id] = monto
        self.saldo += monto
        return SaldoAFavorGenerado(ocurrido_en=ahora, cliente_id=self.cliente_id,
                                   apartado_id=apartado_id, monto=monto)

    def descontar(self, monto: Decimal) -> None:
        monto = dinero(monto)
        if monto <= 0:
            raise ValidacionError("El monto a descontar debe ser mayor a cero.")
        if monto > self.saldo:
            raise ReglaNegocioError("El saldo del monedero no puede quedar negativo.")
        self.saldo -= monto

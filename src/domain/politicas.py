from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class PoliticaApartado:
    """Parámetros del negocio (BRD 5.1 / US-08 a US-12). Inyectables para pruebas."""
    porcentaje_anticipo: Decimal = Decimal("0.20")
    limite_articulos: Optional[int] = 5          # por cliente, todos sus apartados activos
    minutos_reserva: int = 15
    dias_vigencia: int = 30
    total_minimo_beneficio: Decimal = Decimal("1500")

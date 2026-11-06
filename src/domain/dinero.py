from decimal import Decimal, ROUND_HALF_UP, ROUND_UP

CENTAVO = Decimal("0.01")


def dinero(valor) -> Decimal:
    """Convierte a Decimal MXN con 2 decimales (nunca float directo)."""
    return Decimal(str(valor)).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def redondear_arriba(valor: Decimal) -> Decimal:
    return Decimal(valor).quantize(CENTAVO, rounding=ROUND_UP)

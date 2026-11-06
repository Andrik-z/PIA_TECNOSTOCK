"""State Machine genérica + tabla de transiciones del Apartado."""
from enum import Enum
from typing import Dict, Tuple

from .errores import TransicionInvalidaError


class EstadoApartado(str, Enum):
    BORRADOR = "BORRADOR"
    RESERVA_TEMPORAL = "RESERVA_TEMPORAL"
    CONFIRMADO = "CONFIRMADO"
    LIQUIDADO = "LIQUIDADO"
    ENTREGADO = "ENTREGADO"
    VENCIDO = "VENCIDO"
    CANCELADO = "CANCELADO"


class Accion(str, Enum):
    RESERVAR = "reservar"
    CONFIRMAR = "confirmar"
    LIQUIDAR = "liquidar"
    ENTREGAR = "entregar"
    VENCER = "vencer"
    EXPIRAR = "expirar"
    CANCELAR = "cancelar"


class MaquinaEstados:
    def __init__(self, tabla: Dict[Tuple[Enum, Enum], Enum]):
        self._tabla = dict(tabla)

    def siguiente(self, estado, accion):
        try:
            return self._tabla[(estado, accion)]
        except KeyError:
            raise TransicionInvalidaError(
                f"Transición inválida: no se puede '{getattr(accion, 'value', accion)}' "
                f"desde {getattr(estado, 'value', estado)}."
            )

    def acciones_validas(self, estado):
        return [a for (e, a) in self._tabla if e == estado]


E, A = EstadoApartado, Accion
MAQUINA_APARTADO = MaquinaEstados({
    (E.BORRADOR, A.RESERVAR): E.RESERVA_TEMPORAL,
    (E.BORRADOR, A.CANCELAR): E.CANCELADO,
    (E.RESERVA_TEMPORAL, A.CONFIRMAR): E.CONFIRMADO,
    (E.RESERVA_TEMPORAL, A.EXPIRAR): E.CANCELADO,
    (E.RESERVA_TEMPORAL, A.CANCELAR): E.CANCELADO,
    (E.CONFIRMADO, A.LIQUIDAR): E.LIQUIDADO,
    (E.CONFIRMADO, A.VENCER): E.VENCIDO,
    (E.LIQUIDADO, A.ENTREGAR): E.ENTREGADO,
})

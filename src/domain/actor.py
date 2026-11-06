from dataclasses import dataclass
from decimal import Decimal

from .errores import ValidacionError


@dataclass
class Actor:
    """Comprador / cliente."""
    actor_id: str
    nombre: str
    es_preferente: bool = False
    activo: bool = True
    ciudad: str = ""


@dataclass
class Producto:
    """Equipo tecnológico (dato de catálogo)."""
    recurso_id: str
    descripcion: str
    precio: Decimal
    habilitado: bool = True

    def __post_init__(self):
        if Decimal(self.precio) <= 0:
            raise ValidacionError("El precio de un producto debe ser mayor a cero.")

"""Patrón Specification: reglas composables con AND / OR / NOT (operadores &, |, ~)."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Optional

from .politicas import PoliticaApartado


@dataclass
class Contexto:
    """Candidato sobre el que se evalúan las reglas."""
    actor: Any = None
    apartado: Any = None
    articulos_activos: int = 0                 # artículos ya activos del cliente (ADR-04)
    monto_anticipo: Optional[Decimal] = None   # anticipo que se intenta pagar
    politica: PoliticaApartado = field(default_factory=PoliticaApartado)


class Specification(ABC):
    nombre = "spec"
    hijos: tuple = ()

    @abstractmethod
    def is_satisfied_by(self, c: Contexto) -> bool: ...

    def and_(self, otra): return AndSpecification(self, otra)
    def or_(self, otra): return OrSpecification(self, otra)
    def not_(self): return NotSpecification(self)
    __and__, __or__, __invert__ = and_, or_, not_


class AndSpecification(Specification):
    def __init__(self, a, b): self.hijos = (a, b); self.nombre = f"({a.nombre} AND {b.nombre})"
    def is_satisfied_by(self, c): return all(h.is_satisfied_by(c) for h in self.hijos)


class OrSpecification(Specification):
    def __init__(self, a, b): self.hijos = (a, b); self.nombre = f"({a.nombre} OR {b.nombre})"
    def is_satisfied_by(self, c): return any(h.is_satisfied_by(c) for h in self.hijos)


class NotSpecification(Specification):
    def __init__(self, a): self.hijos = (a,); self.nombre = f"NOT {a.nombre}"
    def is_satisfied_by(self, c): return not self.hijos[0].is_satisfied_by(c)


# ---- Reglas hoja ----------------------------------------------------------
class ActorActivo(Specification):
    nombre = "actor_activo"
    def is_satisfied_by(self, c): return bool(c.actor and c.actor.activo)


class ActorPreferente(Specification):
    nombre = "actor_preferente"
    def is_satisfied_by(self, c): return bool(c.actor and c.actor.es_preferente)


class OperacionConLineas(Specification):
    nombre = "detalle_no_vacio"
    def is_satisfied_by(self, c): return bool(c.apartado and len(c.apartado.lineas) > 0)


class OperacionAutorizada(Specification):
    nombre = "autorizada"
    def is_satisfied_by(self, c): return bool(c.apartado and c.apartado.autorizado)


class PromocionActiva(Specification):
    nombre = "promocion_activa"
    def is_satisfied_by(self, c): return bool(c.apartado and c.apartado.promocion_activa)


class TotalMinimo(Specification):
    def __init__(self, minimo: Decimal = Decimal("1500")):
        self.minimo = Decimal(minimo)
        self.nombre = f"total>={self.minimo}"
    def is_satisfied_by(self, c): return bool(c.apartado and c.apartado.total >= self.minimo)


class MaximoArticulosPorCliente(Specification):
    """US-08 / ADR-04: tope global de artículos activos por cliente."""
    nombre = "maximo_articulos"
    def is_satisfied_by(self, c):
        limite = c.politica.limite_articulos
        return limite is None or (c.articulos_activos + c.apartado.articulos) <= limite


class AnticipoMinimo(Specification):
    """US-08 / US-10: el anticipo cubre al menos el 20% del total."""
    nombre = "anticipo_minimo"
    def is_satisfied_by(self, c):
        total = c.apartado.total
        if total <= 0 or c.monto_anticipo is None:
            return False
        return Decimal(c.monto_anticipo) >= total * c.politica.porcentaje_anticipo


# ---- Composiciones nombradas ----------------------------------------------
def puede_procesarse() -> Specification:
    """actor activo AND detalle no vacío AND autorización."""
    return ActorActivo() & OperacionConLineas() & OperacionAutorizada()


def beneficio_referencia(minimo: Decimal = Decimal("1500")) -> Specification:
    """actor preferente AND total >= 1500 AND NOT promoción activa."""
    return ActorPreferente() & TotalMinimo(minimo) & ~PromocionActiva()


def explicar(spec: Specification, c: Contexto) -> Dict[str, bool]:
    """Resultado de cada regla hoja (para evidencia y mensajes de error)."""
    if not spec.hijos:
        return {spec.nombre: spec.is_satisfied_by(c)}
    out: Dict[str, bool] = {}
    for h in spec.hijos:
        out.update(explicar(h, c))
    return out

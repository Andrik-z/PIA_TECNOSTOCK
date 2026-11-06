"""Aggregate Inventario (uno por sucursal). Protege: nunca vender lo apartado."""
from typing import Dict, Optional

from .errores import ConflictoError, NoEncontradoError, ValidacionError


class Inventario:
    def __init__(self, sucursal_id: str,
                 existencias: Optional[Dict[str, Dict[str, int]]] = None,
                 reservas: Optional[Dict[str, Dict[str, int]]] = None):
        self.sucursal_id = sucursal_id
        self.existencias = existencias or {}   # recurso -> {"disponible": n, "vendida": n}
        self.reservas = reservas or {}         # apartado_id -> {recurso: cantidad}

    def registrar_producto(self, recurso_id: str, cantidad: int) -> None:
        if cantidad < 0:
            raise ValidacionError("La existencia no puede ser negativa.")
        self.existencias[recurso_id] = {"disponible": cantidad, "vendida": 0}

    def _ex(self, recurso_id):
        if recurso_id not in self.existencias:
            raise NoEncontradoError(f"Recurso {recurso_id} no existe en la sucursal {self.sucursal_id}.")
        return self.existencias[recurso_id]

    def disponible(self, recurso_id: str) -> int:
        return self._ex(recurso_id)["disponible"]

    def vendida(self, recurso_id: str) -> int:
        return self._ex(recurso_id)["vendida"]

    def apartada(self, recurso_id: str) -> int:
        return sum(r.get(recurso_id, 0) for r in self.reservas.values())

    def apartar(self, apartado_id: str, cantidades: Dict[str, int]) -> None:
        if apartado_id in self.reservas:
            raise ConflictoError(f"El apartado {apartado_id} ya tiene unidades reservadas.")
        for rid, qty in cantidades.items():
            if qty <= 0:
                raise ValidacionError("Las cantidades deben ser mayores a cero.")
            if self.disponible(rid) < qty:
                raise ConflictoError(
                    f"Stock insuficiente de {rid}: disponible {self.disponible(rid)}, solicitado {qty}.")
        for rid, qty in cantidades.items():
            self.existencias[rid]["disponible"] -= qty
        self.reservas[apartado_id] = dict(cantidades)

    def liberar(self, apartado_id: str) -> bool:
        """Idempotente: si no hay reserva no hace nada."""
        res = self.reservas.pop(apartado_id, None)
        if res is None:
            return False
        for rid, qty in res.items():
            self.existencias[rid]["disponible"] += qty
        return True

    def descontar_por_venta(self, apartado_id: str) -> bool:
        res = self.reservas.pop(apartado_id, None)
        if res is None:
            raise ConflictoError(f"El apartado {apartado_id} no tiene unidades reservadas.")
        for rid, qty in res.items():
            self.existencias[rid]["vendida"] += qty
        return True

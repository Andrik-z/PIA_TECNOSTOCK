"""Errores de dominio. La capa API los traduce a códigos HTTP."""


class ErrorDeDominio(Exception):
    """Base de todos los errores de negocio."""


class ValidacionError(ErrorDeDominio):
    """Dato mal formado (cantidad <= 0, monto negativo...). HTTP 400."""


class ReglaNegocioError(ErrorDeDominio):
    """Se viola una regla del negocio (anticipo < 20%, límite de 5...). HTTP 422."""


class ConflictoError(ErrorDeDominio):
    """El estado actual impide la operación (stock, duplicado...). HTTP 409."""


class TransicionInvalidaError(ConflictoError):
    """La máquina de estados no permite la transición. HTTP 409."""


class NoEncontradoError(ErrorDeDominio):
    """Entidad inexistente. HTTP 404."""

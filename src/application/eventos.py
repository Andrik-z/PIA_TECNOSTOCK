import logging
from collections import defaultdict
from typing import Callable, List

log = logging.getLogger("tecnostock.eventos")


class EventBus:
    """Publica Domain Events a los handlers suscritos (consistencia eventual, ADR-02)."""

    def __init__(self):
        self._handlers = defaultdict(list)

    def suscribir(self, tipo, handler: Callable):
        self._handlers[tipo].append(handler)

    def publicar(self, eventos: List):
        cola = list(eventos)
        while cola:
            e = cola.pop(0)
            for h in self._handlers[type(e)] + self._handlers["*"]:
                try:
                    nuevos = h(e)
                    if nuevos:
                        cola.extend(nuevos)
                except Exception:   # un handler fallido no revierte el hecho ya ocurrido
                    log.exception("Handler falló para %s", e.tipo)

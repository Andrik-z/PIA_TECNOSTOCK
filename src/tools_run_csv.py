"""python -m src.tools_run_csv  -> genera resultados/*.csv con evidencia de los casos del PIA."""
import os
import tempfile
from pathlib import Path

from src.application.apartado_service import ApartadoService, ConsultasService
from src.application.eventos import EventBus
from src.application.handlers import registrar_handlers
from src.application.pruebas_csv import (ejecutar_casos, ejecutar_transiciones, escribir_csv,
                                         politica_modelo_de_pruebas)
from src.infrastructure.carga_csv import cargar_datos
from src.infrastructure.db import Database
from src.infrastructure.unit_of_work import UnitOfWork


def construir(url, politica=None):
    db = Database(url)
    uow = lambda: UnitOfWork(db)
    bus = EventBus()
    registrar_handlers(bus, uow)
    kw = {"politica": politica} if politica else {}
    return ApartadoService(uow, bus, **kw), ConsultasService(uow)


def main(data_dir="data", out_dir="resultados"):
    with tempfile.TemporaryDirectory() as t:
        url = f"sqlite:///{os.path.join(t, 'runner.db')}"
        service, _ = construir(url, politica_modelo_de_pruebas())
        cargar_datos(service.uow_factory, data_dir)
        casos = ejecutar_casos(service, data_dir)
        trans = ejecutar_transiciones(service, data_dir)
    escribir_csv(casos, Path(out_dir) / "casos_prueba_resultados.csv")
    escribir_csv(trans, Path(out_dir) / "transiciones_prueba_resultados.csv")
    return casos, trans


if __name__ == "__main__":
    c, t = main()
    print(f"{len(c)} casos y {len(t)} transiciones ejecutados -> resultados/")

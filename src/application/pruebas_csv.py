"""Ejecuta casos_prueba.csv y transiciones_prueba.csv y genera la evidencia (resultado_alumno)."""
import csv
from datetime import datetime
from pathlib import Path

from src.domain.errores import ErrorDeDominio
from src.domain.politicas import PoliticaApartado
from src.domain.specifications import Contexto, beneficio_referencia, explicar, puede_procesarse
from src.infrastructure.carga_csv import leer

AHORA = datetime(2026, 11, 6, 12, 0, 0)

# acción sugerida del CSV -> pasos sobre la state machine propia (ver docs/architecture/diferencias)
PASOS = {
    "aprobar": ["reservar", "confirmar"],
    "completar": ["reservar", "confirmar", "liquidar", "entregar"],
    "cancelar": ["cancelar"],
    "repetir_aprobacion": ["reservar", "confirmar", "reservar"],   # la 2ª aprobación debe rechazarse
    "saltar_estado": ["liquidar"],                                 # BORRADOR -> LIQUIDADO no existe
}


def ejecutar_casos(service, data_dir):
    filas = leer(Path(data_dir) / "casos_prueba.csv")
    for f in filas:
        with service.uow_factory() as uow:
            ap = uow.apartados.obtener(f["operacion_id"])
            actor = uow.actores.obtener(ap.cliente_id)
        ctx = Contexto(actor=actor, apartado=ap, politica=service.politica)
        spec = puede_procesarse() if f["tipo_prueba"] == "validar_operacion" else beneficio_referencia()
        ok = spec.is_satisfied_by(ctx)
        det = "; ".join(f"{k}={v}" for k, v in explicar(spec, ctx).items())
        f["resultado_alumno"] = f"{'CUMPLE' if ok else 'NO_CUMPLE'} | total={ap.total} | {det}"
    return filas


def _paso(service, aid, paso, ahora):
    ap = service.obtener(aid)
    if paso == "reservar":
        return service.reservar(aid, ahora)
    if paso == "confirmar":
        return service.confirmar_anticipo(aid, ap.anticipo_minimo(service.politica), ahora)
    if paso == "liquidar":
        return service.liquidar(aid, ap.saldo, ahora)
    if paso == "entregar":
        return service.entregar(aid, [f"SN-{aid}-{i}" for i in range(ap.articulos)], ahora)
    return service.cancelar(aid, ahora)


def ejecutar_transiciones(service, data_dir):
    filas = leer(Path(data_dir) / "transiciones_prueba.csv")
    for f in filas:
        aid, accion, excepcion = f["operacion_id"], f["accion_sugerida"], "ninguna"
        try:
            for paso in PASOS[accion]:
                _paso(service, aid, paso, AHORA)
        except ErrorDeDominio as e:
            excepcion = f"{type(e).__name__}: {e}"
        ap = service.obtener(aid)
        with service.uow_factory() as uow:
            eventos = [e["tipo"] for e in uow.eventos.listar(500) if e["payload"].get("apartado_id") == aid][::-1]
        f["resultado_alumno"] = (f"estado_final={ap.estado.value} | eventos={','.join(eventos) or 'ninguno'} "
                                 f"| excepcion={excepcion}")
    return filas


def escribir_csv(filas, ruta):
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)


def politica_modelo_de_pruebas() -> PoliticaApartado:
    """El CSV trae operaciones de hasta 9 piezas; se desactiva el tope de 5 solo para esta corrida."""
    return PoliticaApartado(limite_articulos=None)

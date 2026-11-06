"""API REST (FastAPI). Swagger UI en /docs, OpenAPI en /openapi.json."""
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from src.application.apartado_service import ApartadoService, ConsultasService
from src.application.eventos import EventBus
from src.application.handlers import registrar_handlers
from src.application.pruebas_csv import (ejecutar_casos, ejecutar_transiciones, politica_modelo_de_pruebas)
from src.config import Settings
from src.domain.errores import (ConflictoError, ErrorDeDominio, NoEncontradoError, ReglaNegocioError,
                                ValidacionError)
from src.domain.politicas import PoliticaApartado
from src.infrastructure.carga_csv import cargar_datos
from src.infrastructure.db import Database
from src.infrastructure.unit_of_work import UnitOfWork

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


# ---------- esquemas ----------
class ItemIn(BaseModel):
    recurso_id: str
    cantidad: int = Field(description="Entero > 0 (si no, 400)")


class CrearApartadoIn(BaseModel):
    cliente_id: str
    items: List[ItemIn]
    apartado_id: Optional[str] = None
    referencia: str = ""
    autorizado: bool = True
    promocion_activa: bool = False
    ahora: Optional[datetime] = Field(None, description="Solo demo/pruebas: reloj simulado")


class PagoIn(BaseModel):
    monto: str = Field(description="Monto MXN como texto decimal, p. ej. '400.00'")
    ahora: Optional[datetime] = None


class EntregaIn(BaseModel):
    numeros_serie: List[str]
    ahora: Optional[datetime] = None


class AhoraIn(BaseModel):
    ahora: Optional[datetime] = None


def ap_dto(a, svc):
    return {
        "apartado_id": a.apartado_id, "cliente_id": a.cliente_id, "sucursal_id": a.sucursal_id,
        "estado": a.estado.value, "referencia": a.referencia, "autorizado": a.autorizado,
        "promocion_activa": a.promocion_activa,
        "lineas": [{"recurso_id": l.recurso_id, "cantidad": l.cantidad,
                    "precio_unitario": str(l.precio_unitario), "subtotal": str(l.subtotal)} for l in a.lineas],
        "articulos": a.articulos, "total": str(a.total),
        "anticipo_minimo": str(a.anticipo_minimo(svc.politica)), "anticipo_pagado": str(a.anticipo_pagado),
        "saldo": str(a.saldo), "creado_en": a.creado_en.isoformat(),
        "reserva_expira_en": a.reserva_expira_en.isoformat() if a.reserva_expira_en else None,
        "vence_en": a.vence_en.isoformat() if a.vence_en else None,
        "comprobante": a.comprobante, "numeros_serie": a.numeros_serie,
        "acciones_validas": svc.acciones_validas(a),
    }


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    cfg = settings or Settings.desde_entorno()
    db = Database(cfg.database_url)
    uow_factory = lambda: UnitOfWork(db)
    bus = EventBus()
    registrar_handlers(bus, uow_factory)
    politica = PoliticaApartado(porcentaje_anticipo=cfg.porcentaje_anticipo, limite_articulos=cfg.limite_articulos,
                                minutos_reserva=cfg.minutos_reserva, dias_vigencia=cfg.dias_vigencia)
    svc = ApartadoService(uow_factory, bus, politica, cfg.sucursal_id)
    q = ConsultasService(uow_factory)

    if cfg.seed_data:
        with uow_factory() as uow:
            vacio = not uow.actores.listar()
        if vacio and Path(cfg.data_dir).exists():
            cargar_datos(uow_factory, cfg.data_dir, cfg.sucursal_id)

    app = FastAPI(title="TecnoStock API", version="1.0.0",
                  description="Inventario, apartados y ventas de TecnoStock (PIA Componentes de Lógica de Negocio). "
                              "Códigos: 200/201 éxito, 400 dato inválido, 404 no existe, 409 conflicto "
                              "(stock/transición), 422 regla de negocio.")

    # ---------- errores de dominio -> HTTP ----------
    @app.exception_handler(ErrorDeDominio)
    async def _dominio(_: Request, exc: ErrorDeDominio):
        codigo = (400 if isinstance(exc, ValidacionError) else 404 if isinstance(exc, NoEncontradoError)
                  else 409 if isinstance(exc, ConflictoError) else 422)
        return JSONResponse(status_code=codigo, content={"error": type(exc).__name__, "detail": str(exc)})

    # ---------- sistema / frontend ----------
    @app.get("/health", tags=["Sistema"])
    def health():
        return {"status": "healthy", "project": "TecnoStock PIA"}

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(FRONTEND / "index.html")

    @app.get("/api/config", tags=["Sistema"])
    def config():
        return {"porcentaje_anticipo": str(politica.porcentaje_anticipo), "limite_articulos": politica.limite_articulos,
                "minutos_reserva": politica.minutos_reserva, "dias_vigencia": politica.dias_vigencia,
                "sucursal_id": cfg.sucursal_id}

    # ---------- consultas (CU-01) ----------
    @app.get("/api/actores", tags=["Consultas"])
    def actores():
        return [{"actor_id": a.actor_id, "nombre": a.nombre, "es_preferente": a.es_preferente,
                 "activo": a.activo, "ciudad": a.ciudad} for a in q.actores()]

    @app.get("/api/productos", tags=["Consultas"])
    def productos():
        return [{"recurso_id": x["producto"].recurso_id, "descripcion": x["producto"].descripcion,
                 "precio": str(x["producto"].precio), "habilitado": x["producto"].habilitado,
                 "sucursales": x["sucursales"]} for x in q.productos()]

    @app.get("/api/productos/{recurso_id}/disponibilidad", tags=["Consultas"])
    def disponibilidad(recurso_id: str):
        return q.disponibilidad_global(recurso_id)

    @app.get("/api/monederos/{cliente_id}", tags=["Consultas"])
    def monedero(cliente_id: str):
        m = q.monedero(cliente_id)
        return {"cliente_id": m.cliente_id, "saldo": str(m.saldo), "abonos": {k: str(v) for k, v in m.abonos.items()}}

    @app.get("/api/eventos", tags=["Consultas"])
    def eventos(limite: int = 100):
        return q.eventos(limite)

    # ---------- apartados ----------
    @app.post("/api/apartados", status_code=201, tags=["Apartados"])
    def crear(req: CrearApartadoIn):
        a = svc.iniciar_apartado(req.cliente_id, [i.model_dump() for i in req.items], req.apartado_id,
                                 req.referencia, req.autorizado, req.promocion_activa, req.ahora)
        return ap_dto(a, svc)

    @app.get("/api/apartados", tags=["Apartados"])
    def listar(cliente_id: Optional[str] = None, estado: Optional[str] = None):
        return [ap_dto(a, svc) for a in svc.listar(cliente_id, estado)]

    @app.get("/api/apartados/{apartado_id}", tags=["Apartados"])
    def obtener(apartado_id: str):
        return ap_dto(svc.obtener(apartado_id), svc)

    @app.get("/api/apartados/{apartado_id}/evaluacion", tags=["Apartados"])
    def evaluacion(apartado_id: str):
        return svc.evaluar(apartado_id)

    @app.post("/api/apartados/{apartado_id}/reservar", tags=["Apartados"])
    def reservar(apartado_id: str, req: AhoraIn = AhoraIn()):
        return ap_dto(svc.reservar(apartado_id, req.ahora), svc)

    @app.post("/api/apartados/{apartado_id}/anticipo", tags=["Apartados"])
    def anticipo(apartado_id: str, req: PagoIn):
        return ap_dto(svc.confirmar_anticipo(apartado_id, req.monto, req.ahora), svc)

    @app.post("/api/apartados/{apartado_id}/liquidar", tags=["Apartados"])
    def liquidar(apartado_id: str, req: PagoIn):
        return ap_dto(svc.liquidar(apartado_id, req.monto, req.ahora), svc)

    @app.post("/api/apartados/{apartado_id}/entregar", tags=["Apartados"])
    def entregar(apartado_id: str, req: EntregaIn):
        return ap_dto(svc.entregar(apartado_id, req.numeros_serie, req.ahora), svc)

    @app.post("/api/apartados/{apartado_id}/cancelar", tags=["Apartados"])
    def cancelar(apartado_id: str, req: AhoraIn = AhoraIn()):
        return ap_dto(svc.cancelar(apartado_id, req.ahora), svc)

    # ---------- mantenimiento / evidencia ----------
    @app.post("/api/mantenimiento/vencimientos", tags=["Mantenimiento"])
    def vencimientos(req: AhoraIn = AhoraIn()):
        return svc.procesar_vencimientos(req.ahora)

    @app.post("/api/mantenimiento/cargar-csv", tags=["Mantenimiento"])
    def cargar():
        return cargar_datos(uow_factory, cfg.data_dir, cfg.sucursal_id)

    @app.post("/api/pruebas/ejecutar", tags=["Mantenimiento"])
    def pruebas():
        """Ejecuta casos_prueba.csv y transiciones_prueba.csv en una BD temporal (no toca tus datos)."""
        from src.tools_run_csv import construir
        with tempfile.TemporaryDirectory() as t:
            s, _ = construir(f"sqlite:///{os.path.join(t, 'r.db')}", politica_modelo_de_pruebas())
            cargar_datos(s.uow_factory, cfg.data_dir)
            return {"casos": ejecutar_casos(s, cfg.data_dir), "transiciones": ejecutar_transiciones(s, cfg.data_dir)}

    return app


app = create_app()

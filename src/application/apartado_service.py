import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from src.domain.apartado import Apartado, LineaApartado
from src.domain.errores import ReglaNegocioError, ValidacionError
from src.domain.estados import EstadoApartado, MAQUINA_APARTADO
from src.domain.politicas import PoliticaApartado
from src.domain.specifications import Contexto, beneficio_referencia, explicar, puede_procesarse


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


class ApartadoService:
    """Application Service: coordina repositorios y UoW; las reglas viven en el dominio."""

    def __init__(self, uow_factory, bus, politica: PoliticaApartado = PoliticaApartado(),
                 sucursal_id: str = "SUC-01", reloj=utcnow):
        self.uow_factory, self.bus = uow_factory, bus
        self.politica, self.sucursal_id, self.reloj = politica, sucursal_id, reloj

    # ---------- comandos ----------
    def _armar(self, uow, cliente_id, items, apartado_id, referencia, autorizado, promocion_activa, ahora):
        uow.actores.obtener(cliente_id)  # 404 si no existe
        if not items:
            raise ValidacionError("El apartado debe incluir al menos un artículo.")
        lineas = []
        for it in items:
            p = uow.productos.obtener(it["recurso_id"])
            if not p.habilitado:
                raise ReglaNegocioError(f"El producto {p.recurso_id} está deshabilitado.")
            lineas.append(LineaApartado(it["recurso_id"], it["cantidad"], p.precio))
        return Apartado(apartado_id or f"APT-{uuid.uuid4().hex[:8].upper()}", cliente_id, self.sucursal_id,
                        lineas, creado_en=ahora, autorizado=autorizado,
                        promocion_activa=promocion_activa, referencia=referencia)

    def _reservar(self, uow, ap: Apartado, ahora):
        actor = uow.actores.obtener(ap.cliente_id)
        activos = uow.apartados.contar_articulos_activos(ap.cliente_id, excluir=ap.apartado_id)
        for l in ap.lineas:
            if not uow.productos.obtener(l.recurso_id).habilitado:
                raise ReglaNegocioError(f"El producto {l.recurso_id} está deshabilitado.")
        ap.reservar(ahora, actor, activos, self.politica)
        inv = uow.inventarios.obtener(ap.sucursal_id)
        inv.apartar(ap.apartado_id, {l.recurso_id: l.cantidad for l in ap.lineas})
        uow.inventarios.guardar(inv)

    def iniciar_apartado(self, cliente_id: str, items: List[dict], apartado_id: Optional[str] = None,
                         referencia: str = "", autorizado: bool = True, promocion_activa: bool = False,
                         ahora: Optional[datetime] = None) -> Apartado:
        """CU-02: crea + reserva stock + abre reserva de 15 min (todo atómico)."""
        ahora = ahora or self.reloj()
        with self.uow_factory() as uow:
            if apartado_id and uow.apartados.existe(apartado_id):
                from src.domain.errores import ConflictoError
                raise ConflictoError(f"El apartado {apartado_id} ya existe.")
            ap = self._armar(uow, cliente_id, items, apartado_id, referencia, autorizado, promocion_activa, ahora)
            self._reservar(uow, ap, ahora)
            uow.apartados.guardar(ap)
            eventos = ap.pull_events()
        self.bus.publicar(eventos)
        return ap

    def reservar(self, apartado_id: str, ahora: Optional[datetime] = None) -> Apartado:
        ahora = ahora or self.reloj()
        with self.uow_factory() as uow:
            ap = uow.apartados.obtener(apartado_id)
            self._reservar(uow, ap, ahora)
            uow.apartados.guardar(ap)
            eventos = ap.pull_events()
        self.bus.publicar(eventos)
        return ap

    def confirmar_anticipo(self, apartado_id: str, monto, ahora: Optional[datetime] = None) -> Apartado:
        """CU-02/US-10."""
        ahora = ahora or self.reloj()
        expirada = False
        with self.uow_factory() as uow:
            ap = uow.apartados.obtener(apartado_id)
            if ap.estado == EstadoApartado.RESERVA_TEMPORAL and ap.expirar_reserva(ahora):
                uow.apartados.guardar(ap)   # se cancela y libera, luego se informa el rechazo
                expirada, eventos = True, ap.pull_events()
            else:
                ap.confirmar_anticipo(monto, ahora, self.politica)
                uow.apartados.guardar(ap)
                eventos = ap.pull_events()
        self.bus.publicar(eventos)
        if expirada:
            raise ReglaNegocioError("ReservaExpirada: la reserva temporal venció; el stock fue liberado.")
        return ap

    def liquidar(self, apartado_id: str, monto, ahora: Optional[datetime] = None) -> Apartado:
        """CU-03/US-11."""
        ahora = ahora or self.reloj()
        with self.uow_factory() as uow:
            ap = uow.apartados.obtener(apartado_id)
            ap.liquidar(monto, ahora)
            uow.apartados.guardar(ap)
            eventos = ap.pull_events()
        self.bus.publicar(eventos)
        return ap

    def entregar(self, apartado_id: str, numeros_serie: List[str], ahora: Optional[datetime] = None) -> Apartado:
        """CU-05/US-15,16: asocia series y registra la salida física (atómico con inventario)."""
        ahora = ahora or self.reloj()
        with self.uow_factory() as uow:
            ap = uow.apartados.obtener(apartado_id)
            ap.entregar(numeros_serie, ahora)
            inv = uow.inventarios.obtener(ap.sucursal_id)
            inv.descontar_por_venta(apartado_id)
            uow.inventarios.guardar(inv)
            uow.apartados.guardar(ap)
            eventos = ap.pull_events()
        self.bus.publicar(eventos)
        return ap

    def cancelar(self, apartado_id: str, ahora: Optional[datetime] = None) -> Apartado:
        ahora = ahora or self.reloj()
        with self.uow_factory() as uow:
            ap = uow.apartados.obtener(apartado_id)
            ap.cancelar(ahora)
            uow.apartados.guardar(ap)
            eventos = ap.pull_events()
        self.bus.publicar(eventos)
        return ap

    def procesar_vencimientos(self, ahora: Optional[datetime] = None) -> dict:
        """CU-04/US-09/US-12: tarea periódica; una transacción por apartado."""
        ahora = ahora or self.reloj()
        with self.uow_factory() as uow:
            ids = [(a.apartado_id, a.estado) for a in uow.apartados.listar_por_estado(
                [EstadoApartado.RESERVA_TEMPORAL, EstadoApartado.CONFIRMADO])]
        expiradas, vencidos = [], []
        for aid, estado in ids:
            with self.uow_factory() as uow:
                ap = uow.apartados.obtener(aid)
                ok = ap.expirar_reserva(ahora) if estado == EstadoApartado.RESERVA_TEMPORAL else ap.vencer(ahora)
                if ok:
                    uow.apartados.guardar(ap)
                eventos = ap.pull_events()
            if ok:
                (expiradas if estado == EstadoApartado.RESERVA_TEMPORAL else vencidos).append(aid)
                self.bus.publicar(eventos)
        return {"reservas_expiradas": expiradas, "apartados_vencidos": vencidos}

    # ---------- consultas ----------
    def obtener(self, apartado_id: str) -> Apartado:
        with self.uow_factory() as uow:
            return uow.apartados.obtener(apartado_id)

    def listar(self, cliente_id=None, estado=None) -> List[Apartado]:
        with self.uow_factory() as uow:
            return uow.apartados.listar(cliente_id, estado)

    def acciones_validas(self, ap: Apartado) -> List[str]:
        return [a.value for a in MAQUINA_APARTADO.acciones_validas(ap.estado)]

    def evaluar(self, apartado_id: str) -> dict:
        """Evalúa las reglas de prueba del PIA con Specifications (evidencia por regla)."""
        with self.uow_factory() as uow:
            ap = uow.apartados.obtener(apartado_id)
            actor = uow.actores.obtener(ap.cliente_id)
        ctx = Contexto(actor=actor, apartado=ap, politica=self.politica)
        sp, sb = puede_procesarse(), beneficio_referencia(self.politica.total_minimo_beneficio)
        return {
            "apartado_id": ap.apartado_id, "total": str(ap.total),
            "puede_procesarse": {"cumple": sp.is_satisfied_by(ctx), "regla": sp.nombre, "detalle": explicar(sp, ctx)},
            "beneficio_referencia": {"cumple": sb.is_satisfied_by(ctx), "regla": sb.nombre, "detalle": explicar(sb, ctx)},
        }


class ConsultasService:
    """Lado de lectura (CQRS básico, ADR-03): no instancia agregados de escritura ni modifica estado."""

    def __init__(self, uow_factory):
        self.uow_factory = uow_factory

    def actores(self):
        with self.uow_factory() as uow:
            return uow.actores.listar()

    def productos(self):
        with self.uow_factory() as uow:
            inv = {i.sucursal_id: i for i in uow.inventarios.listar()}
            out = []
            for p in uow.productos.listar():
                por_sucursal = {s: {"disponible": i.disponible(p.recurso_id), "apartada": i.apartada(p.recurso_id),
                                    "vendida": i.vendida(p.recurso_id)}
                                for s, i in inv.items() if p.recurso_id in i.existencias}
                out.append({"producto": p, "sucursales": por_sucursal})
            return out

    def disponibilidad_global(self, recurso_id: str):
        """US-01/US-02."""
        with self.uow_factory() as uow:
            p = uow.productos.obtener(recurso_id)
            suc = {i.sucursal_id: {"disponible": i.disponible(recurso_id), "apartada": i.apartada(recurso_id)}
                   for i in uow.inventarios.listar() if recurso_id in i.existencias}
            return {"recurso_id": recurso_id, "descripcion": p.descripcion, "sucursales": suc,
                    "total_disponible": sum(v["disponible"] for v in suc.values())}

    def monedero(self, cliente_id: str):
        with self.uow_factory() as uow:
            uow.actores.obtener(cliente_id)
            return uow.monederos.obtener_o_crear(cliente_id)

    def eventos(self, limite=200):
        with self.uow_factory() as uow:
            return uow.eventos.listar(limite)

# Diferencias entre el modelo de pruebas del paquete y el diseño del equipo
El paquete propone BORRADOR→APROBADA→SURTIDA→ENTREGADA/CANCELADA. El PIA exige derivar del BRD/US/BPMN propios, así que se conservó el diseño del equipo y se **mapeó**:

| Paquete | Implementación del equipo |
|---|---|
| Operación | Apartado |
| BORRADOR | BORRADOR |
| APROBADA | RESERVA_TEMPORAL → CONFIRMADO (anticipo ≥ 20 %) |
| SURTIDA | LIQUIDADO (ticket QR) |
| ENTREGADA | ENTREGADO (series + salida física) |
| CANCELADA | CANCELADO (cancelación, reserva expirada) · VENCIDO (30 días → monedero) |

Acciones de `transiciones_prueba.csv`: `aprobar`=reservar+confirmar · `completar`=reservar+confirmar+liquidar+entregar · `cancelar` · `repetir_aprobacion`=aprobar y reservar otra vez (debe fallar) · `saltar_estado`=liquidar desde BORRADOR (debe fallar).

Otras diferencias:
- Las operaciones del CSV traen hasta 9 piezas; el tope de 5 por cliente (BRD) las rechazaría. `src/application/pruebas_csv.py` desactiva el tope **solo** en la corrida de evidencia; la API lo aplica siempre.
- El CSV no trae sucursal: se usa una sola (`SUC-01`) con `capacidad_o_stock` como existencia.
- Precondiciones `stock_suficiente` → 409 en Inventario; `credito_valido` no existe en el BRD y no se implementó.
- Devoluciones y transferencias (diseñadas en U3) quedan fuera; se documentan como trabajo futuro.

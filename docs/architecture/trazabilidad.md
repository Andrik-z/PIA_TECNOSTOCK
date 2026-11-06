# Matriz de trazabilidad: BRD → regla → componente → prueba
| BRD / US | Regla | Componente | Prueba |
|---|---|---|---|
| BR1 · US-01/02 | Consulta de disponibilidad | `ConsultasService.disponibilidad_global` | `test_cu01_disponibilidad` |
| BR4 · US-08 | RN-01 anticipo 20 % | `AnticipoMinimo`, `Apartado.confirmar_anticipo` | `test_anticipo_minimo`, `test_reserva_y_anticipo_reglas` |
| US-08 · ADR-04 | RN-02 máx. 5 por cliente | `MaximoArticulosPorCliente`, `ApartadosRepo.contar_articulos_activos` | `test_limite_articulos`, `test_limite_5_global_por_cliente` |
| US-09 | RN-03 reserva 15 min | `Apartado.expirar_reserva`, handler `liberar_stock` | `test_us09_reserva_expirada_libera`, `test_pago_tardio_cancela_y_rechaza` |
| US-10 | Confirmar apartado, vence a 30 días | `Apartado.confirmar_anticipo` | `test_flujo_feliz` |
| US-11 | RN-05 liquidar + QR | `Apartado.liquidar` | `test_liquidar_reglas`, `test_flujo_completo_y_salida_fisica` |
| US-12 | RN-04 vencimiento + monedero | `Apartado.vencer`, `Monedero.abonar_anticipo` | `test_us12_vencimiento_monedero_idempotente` |
| BRD 5.2 | Nunca vender lo apartado | `Inventario.apartar` | `test_no_se_vende_lo_apartado`, `test_apartar_liberar_vender` |
| US-14 | Falla → rollback, stock intacto | `UnitOfWork` | `test_rechazos_de_creacion`, `test_reservar_borrador_y_rollback_uow` |
| US-15/16 · BR3 | RN-06 serie única, salida única | `Apartado.entregar`, `Inventario.descontar_por_venta` | `test_entrega_series`, `test_flujo_completo_y_salida_fisica` |
| Modelo PIA | RN-07 / RN-08 Specifications AND/OR/NOT | `puede_procesarse()`, `beneficio_referencia()` | `TestSpecifications`, `test_runner_csv` |
| BRD 5.2 | State Machine | `MAQUINA_APARTADO` | `test_transiciones_invalidas` |
| API | 201/400/404/409/422 | `src/api/main.py` | `tests/test_api.py` |

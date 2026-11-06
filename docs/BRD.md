# BRD — TecnoStock (Equipo 5)
Rodrigo Noguera Pérez (2136238) · Andrik Hasiel Pérez Limón (2118898) · Erick Antonio Paez Estrada (2120761)
Curso: Componentes de Lógica de Negocio · Profesor: Miguel Ángel Gómez Marroquín

## 1. Contexto
Cadena de 5 tiendas de electrónica (computadoras, celulares, accesorios, componentes) con venta en sucursal y apartados.

## 2. Problema
- El sistema no coincide con el inventario físico.
- Se venden productos ya apartados.
- Difícil rastrear números de serie.
- Criterios inconsistentes de devolución (**fuera del alcance de esta implementación**, ver `architecture/diferencias.md`).

## 3. Alcance implementado
Consulta de inventario, apartados (anticipo, reserva temporal, vencimiento, monedero), liquidación con ticket QR, entrega con número de serie.
Transferencias entre sucursales y devoluciones: diseñadas en U3 pero **no** implementadas en este PIA.

## 4. Stakeholders
Cliente · Vendedor · Cajero · Supervisor · Personal de Almacén.

## 5. Necesidades (BR) y restricciones
BR1 consultar disponibilidad · BR2 cobrar y generar comprobante · BR3 unidad exacta por número de serie · BR4 reservar con anticipo.
Restricción: un producto apartado no se vende a otro cliente (BRD 5.2).

## 6. Reglas de negocio
| ID | Regla | Fuente |
|---|---|---|
| RN-01 | Anticipo mínimo 20 % del total | US-08, US-10 |
| RN-02 | Máx. 5 artículos por cliente sumando apartados activos | US-08, ADR-04 |
| RN-03 | Reserva temporal de 15 min; sin pago se cancela y libera stock | US-09 |
| RN-04 | Confirmado vence a los 30 días; stock se libera y anticipo → monedero (una vez) | US-12 |
| RN-05 | Liquidación solo antes del vencimiento y por el saldo completo; genera ticket QR | US-11 |
| RN-06 | Una serie única por unidad entregada; salida física una sola vez | US-15, US-16 |
| RN-07 | `puede_procesarse` = actor activo AND detalle no vacío AND autorizado | modelo de pruebas PIA |
| RN-08 | `beneficio_referencia` = preferente AND total ≥ 1500 AND NOT promoción | modelo de pruebas PIA |

## 7. Criterios de éxito
Cada necesidad trazada a User Story (Gherkin), regla, componente y prueba: ver `architecture/trazabilidad.md`.
Las 16 User Stories con criterios Dado/Cuando/Entonces y el BPMN se entregan en el reporte PDF del equipo (U2).

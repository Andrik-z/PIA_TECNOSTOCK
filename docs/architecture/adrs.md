# ADRs
**ADR-01 Domain Model.** Contexto: reglas interdependientes con estado (20 %, 15 min, 30 días, series). Alternativas: Transaction Script, Table Module. Decisión: Domain Model. Consecuencia: más diseño inicial, reglas probadas sin BD.

**ADR-02 Unit of Work.** Contexto: apartar modifica Apartado e Inventario; no pueden quedar unidades a medias. Alternativas: guardar por separado, consistencia eventual. Decisión: `UnitOfWork` con commit/rollback; reacciones a eventos (liberar stock, abonar monedero) en transacción propia vía `EventBus`. Consecuencia: ventana breve de consistencia eventual en vencimientos; handlers idempotentes (`Inventario.liberar`, `Monedero` por `apartado_id`).

**ADR-03 CQRS básico.** Las consultas de disponibilidad pasan por `ConsultasService` (solo lectura, sin agregados de escritura). Sin bases separadas.

**ADR-04 Límite de 5 en el dominio con conteo del servicio.** El servicio consulta `contar_articulos_activos` y `Apartado.reservar` decide.

**ADR-05 Specification + State Machine.** Reglas composables (`&`, `|`, `~`) y tabla explícita de transiciones; cualquier transición fuera de la tabla → `TransicionInvalidaError` (409).

**ADR-06 SQLite/PostgreSQL con SQL portable.** Agregados serializados como JSON en TEXT; `ON CONFLICT` para upsert. Un lock por proceso serializa escrituras; en producción multi-réplica habría que usar `SELECT … FOR UPDATE`.

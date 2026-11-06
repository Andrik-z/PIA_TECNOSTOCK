# TecnoStock — Apartados, inventario y ventas (PIA · Componentes de Lógica de Negocio)

Equipo 5 · FIME UANL. Python 3.12 · FastAPI · SQLite/PostgreSQL · DDD + Specification + State Machine + Domain Events.

## Estructura
```
docs/        BRD.md · architecture/ (ADRs, diferencias, trazabilidad) · api/ (OpenAPI)
src/domain/          entidades, VOs, agregados (Apartado, Inventario, Monedero), eventos, specifications, state machine
src/application/     servicios, UoW-orquestación, EventBus + handlers, CQRS de lectura, runner de CSV
src/infrastructure/  BD (SQLite/Postgres), repositorios, Unit of Work, carga de CSV
src/api/             FastAPI (REST + Swagger) y sirve el frontend
frontend/index.html  interfaz web (sin build)
tests/               unitarias + integración   data/  CSV del PIA   resultados/  evidencia de los CSV
```

## Ejecutar local (sin Docker, SQLite)
```bash
pip install -r requirements.txt
uvicorn src.api.main:app --reload      # http://localhost:8000  (frontend)  ·  /docs (Swagger)
pytest                                  # incluye cobertura, falla si < 80 %
python -m src.tools_run_csv            # genera resultados/*.csv (casos y transiciones del PIA)
```

## Docker Compose (DB + App + Tests)
```bash
cp .env.example .env
docker compose up --build                          # db + app en :8000
docker compose --profile tests run --rm tests      # pruebas con cobertura
```

## Despliegue (Render / Railway / Fly.io)
Dockerfile listo. Variables: `DATABASE_URL` (Postgres del proveedor), `SEED_DATA=true`, `PORT` (lo da la plataforma).
Swagger queda en `https://<tu-app>/docs`.

## Reglas (BRD / US) → código
Anticipo 20 % (US-08/10) · máx. 5 artículos por cliente (ADR-04) · reserva 15 min (US-09) · vigencia 30 días (US-12) · monedero idempotente ·
nunca vender lo apartado (BRD 5.2) · serie única por unidad (US-16). Ver `docs/architecture/trazabilidad.md`.

## Códigos HTTP
200/201 éxito · 400 dato inválido · 404 no existe · 409 conflicto (stock, transición, duplicado) · 422 regla de negocio.

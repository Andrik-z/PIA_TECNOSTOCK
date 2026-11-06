import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Configuración 12-Factor: todo viene de variables de entorno."""
    database_url: str = "sqlite:///tecnostock.db"
    seed_data: bool = True
    data_dir: str = "data"
    sucursal_id: str = "SUC-01"
    limite_articulos: int = 5
    porcentaje_anticipo: Decimal = Decimal("0.20")
    minutos_reserva: int = 15
    dias_vigencia: int = 30

    @classmethod
    def desde_entorno(cls):
        e = os.environ
        return cls(
            database_url=e.get("DATABASE_URL", cls.database_url),
            seed_data=e.get("SEED_DATA", "true").lower() == "true",
            data_dir=e.get("DATA_DIR", cls.data_dir),
            sucursal_id=e.get("SUCURSAL_ID", cls.sucursal_id),
            limite_articulos=int(e.get("LIMITE_ARTICULOS", cls.limite_articulos)),
            porcentaje_anticipo=Decimal(e.get("PORCENTAJE_ANTICIPO", str(cls.porcentaje_anticipo))),
            minutos_reserva=int(e.get("MINUTOS_RESERVA", cls.minutos_reserva)),
            dias_vigencia=int(e.get("DIAS_VIGENCIA", cls.dias_vigencia)),
        )

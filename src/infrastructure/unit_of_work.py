from src.infrastructure.repositorios import (ActoresRepo, ApartadosRepo, EventosRepo,
                                             InventariosRepo, MonederosRepo, ProductosRepo)


class UnitOfWork:
    """Commit si todo sale bien; Rollback completo ante cualquier error (ADR-02)."""

    def __init__(self, db):
        self.db = db

    def __enter__(self):
        self.db.lock.acquire()
        try:
            self.conn = self.db.connect()
            for nombre, cls in (("actores", ActoresRepo), ("productos", ProductosRepo),
                                ("inventarios", InventariosRepo), ("apartados", ApartadosRepo),
                                ("monederos", MonederosRepo), ("eventos", EventosRepo)):
                setattr(self, nombre, cls(self.db, self.conn))
        except Exception:
            self.db.lock.release()
            raise
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type:
                self.conn.rollback()
            else:
                self.conn.commit()
        finally:
            self.conn.close()
            self.db.lock.release()
        return False

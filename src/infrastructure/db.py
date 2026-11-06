"""Acceso a BD portable: SQLite (por defecto) o PostgreSQL (psycopg2) según DATABASE_URL."""
import sqlite3
import threading

SCHEMA = [
    "CREATE TABLE IF NOT EXISTS actores (actor_id TEXT PRIMARY KEY, nombre TEXT, es_preferente INTEGER, activo INTEGER, ciudad TEXT)",
    "CREATE TABLE IF NOT EXISTS productos (recurso_id TEXT PRIMARY KEY, descripcion TEXT, precio TEXT, habilitado INTEGER)",
    "CREATE TABLE IF NOT EXISTS inventarios (sucursal_id TEXT PRIMARY KEY, data TEXT)",
    "CREATE TABLE IF NOT EXISTS apartados (apartado_id TEXT PRIMARY KEY, cliente_id TEXT, estado TEXT, data TEXT)",
    "CREATE TABLE IF NOT EXISTS monederos (cliente_id TEXT PRIMARY KEY, data TEXT)",
    "CREATE TABLE IF NOT EXISTS eventos (id TEXT PRIMARY KEY, ocurrido_en TEXT, tipo TEXT, payload TEXT)",
]


class Database:
    def __init__(self, url: str = "sqlite:///tecnostock.db"):
        self.url = url
        self.es_postgres = url.startswith(("postgres://", "postgresql://"))
        self.lock = threading.RLock()   # serializa escrituras dentro del proceso
        self.crear_esquema()

    def connect(self):
        if self.es_postgres:
            import psycopg2  # solo se requiere con PostgreSQL
            return psycopg2.connect(self.url)
        path = self.url.replace("sqlite:///", "", 1)
        return sqlite3.connect(path, timeout=30, check_same_thread=False)

    def sql(self, texto: str) -> str:
        return texto.replace("?", "%s") if self.es_postgres else texto

    def execute(self, conn, texto: str, params=()):
        cur = conn.cursor()
        cur.execute(self.sql(texto), params)
        return cur

    def crear_esquema(self):
        conn = self.connect()
        try:
            for s in SCHEMA:
                self.execute(conn, s)
            conn.commit()
        finally:
            conn.close()

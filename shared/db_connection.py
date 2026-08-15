"""
Shared Database Connection Pool — PostgreSQL (Neon.tech)
Centraliza conexões seguras e resilientes para todos os módulos do ecossistema anime-pipeline.
"""

import os
import logging
from psycopg2 import pool
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("shared.db")

_DATABASE_URL = os.getenv("DATABASE_URL")
_connection_pool = None

def get_pool():
    """Retorna o pool de conexões singleton."""
    global _connection_pool
    if _connection_pool is None or _connection_pool.closed:
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            raise ValueError("DATABASE_URL não configurada no arquivo .env!")
        
        # Cria pool com min 1 e max 20 conexões
        _connection_pool = pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=20,
            dsn=db_url
        )
        logger.info("Pool de conexões PostgreSQL Neon inicializado com sucesso.")
    return _connection_pool

def get_connection():
    """Obtém uma conexão ativa do pool."""
    p = get_pool()
    return p.getconn()

def release_connection(conn):
    """Devolve a conexão ao pool."""
    if conn and _connection_pool and not _connection_pool.closed:
        _connection_pool.putconn(conn)

class DBConnectionContext:
    """Context Manager seguro para uso com 'with'."""
    def __init__(self, autocommit=True):
        self.conn = None
        self.autocommit = autocommit

    def __enter__(self):
        self.conn = get_connection()
        if self.autocommit:
            self.conn.autocommit = True
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            if not self.autocommit and exc_type is not None:
                self.conn.rollback()
            elif not self.autocommit and exc_type is None:
                self.conn.commit()
            release_connection(self.conn)

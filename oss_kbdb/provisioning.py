"""Provisionamento seguro do data plane de uma KB em schema próprio."""
from __future__ import annotations
from pathlib import Path
import re
import psycopg
from psycopg import sql

_SCHEMA = re.compile(r"^kb_[a-z0-9_]{1,58}$")

def provision_kb_database(database_url: str, schema_name: str) -> None:
    """Cria um schema isolado e aplica o modelo medallion naquele schema.

    A extensão pgvector é de instância/database e é criada uma única vez. As tabelas
    e índices sem qualificação do 001 usam o `search_path` desta transação, portanto
    jamais caem em `public`.
    """
    if not _SCHEMA.fullmatch(schema_name):
        raise ValueError("schema de KB inválido")
    migration = (Path(__file__).parents[1] / "sql" / "001_schema.sql").read_text()
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema_name)))
        cur.execute(sql.SQL("SET LOCAL search_path TO {}, public").format(sql.Identifier(schema_name)))
        # A extensão já foi criada acima; o restante é schema-local pelo search_path.
        body = "\n".join(line for line in migration.splitlines() if "CREATE EXTENSION" not in line)
        cur.execute(body)

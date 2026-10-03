"""
app/db/types.py
───────────────
Dialect-aware type helpers.
- Use JSONB on Postgres, JSON on SQLite (for tests).
- Use pgvector Vector on Postgres, Text on SQLite.
Import these instead of postgresql.JSONB / pgvector.Vector directly in models.
"""
from __future__ import annotations

from sqlalchemy import JSON, Text, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator, UserDefinedType


class JSONType(TypeDecorator):
    """Postgres: JSONB. SQLite (tests): JSON."""
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class VectorType(TypeDecorator):
    """Postgres: VECTOR(dim). SQLite (tests): Text (stores nothing useful but lets DDL pass)."""
    impl = Text
    cache_ok = True

    def __init__(self, dim: int = 384):
        self.dim = dim
        super().__init__()

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector
            return dialect.type_descriptor(Vector(self.dim))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if dialect.name == "postgresql":
            return value
        if value is None:
            return None
        import json
        if isinstance(value, (list, tuple)):
            return json.dumps(list(value))
        return str(value)

    def process_result_value(self, value, dialect):
        if dialect.name == "postgresql":
            return value
        if value is None:
            return None
        import json
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return None
        return value

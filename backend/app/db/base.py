"""Declarative base + common column types."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID, uuid4

from sqlalchemy import DateTime, MetaData, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON, TypeDecorator

# Postgres-quality conventions; portable to SQLite for laptop demos.
naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class JSONBOrJSON(TypeDecorator):  # type: ignore[type-arg]
    """JSONB on Postgres, JSON on SQLite — same Python interface."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=naming_convention)
    type_annotation_map: ClassVar[dict[type, JSONBOrJSON]] = {
        dict: JSONBOrJSON,
        list: JSONBOrJSON,
    }


class TimestampMixin:
    """Adds created_at / updated_at — automatically populated."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class IdMixin:
    """ULID-as-string primary key — sortable, URL-safe, and DB-agnostic."""

    id: Mapped[str] = mapped_column(
        String(26), primary_key=True, default=lambda: str(uuid4())
    )


def new_uuid() -> UUID:
    return uuid4()

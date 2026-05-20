"""Audit log — append-only PII access trail."""

from __future__ import annotations

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class AuditLog(Base, IdMixin, TimestampMixin):
    __tablename__ = "audit_log"

    actor_id: Mapped[str] = mapped_column(String(80), index=True)
    actor_role: Mapped[str] = mapped_column(String(40), index=True)
    actor_facility_id: Mapped[str | None] = mapped_column(String(26), index=True)
    resource_type: Mapped[str] = mapped_column(String(40), index=True)
    resource_id: Mapped[str] = mapped_column(String(80), index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    purpose: Mapped[str | None] = mapped_column(String(300))
    consent_id: Mapped[str | None] = mapped_column(String(26))
    extra: Mapped[dict] = mapped_column(default=dict)

    __table_args__ = (
        Index("ix_audit_log_resource", "resource_type", "resource_id"),
        Index("ix_audit_log_actor_time", "actor_id", "created_at"),
    )

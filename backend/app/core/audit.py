"""Immutable audit trail for every PII access — required for HIPAA-equivalent compliance.

Audit entries land in a dedicated table with append-only semantics (no UPDATE,
no DELETE; we enforce this at the application layer and a future migration
will add a Postgres rule to forbid them at the database layer too).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import Principal
from app.db.models.audit_log import AuditLog

logger = get_logger(__name__)


async def record_access(
    session: AsyncSession,
    *,
    principal: Principal,
    resource_type: str,
    resource_id: str | UUID,
    action: str,
    purpose: str | None = None,
    consent_id: str | UUID | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Append an audit entry. The caller owns the transaction."""
    entry = AuditLog(
        actor_id=principal.subject,
        actor_role=principal.role,
        actor_facility_id=principal.facility_id,
        resource_type=resource_type,
        resource_id=str(resource_id),
        action=action,
        purpose=purpose,
        consent_id=str(consent_id) if consent_id else None,
        extra=extra or {},
    )
    session.add(entry)
    # Mirror to structured logs for SIEM ingestion
    logger.info(
        "audit",
        actor=principal.subject,
        role=principal.role,
        resource_type=resource_type,
        resource_id=str(resource_id),
        action=action,
        purpose=purpose,
    )

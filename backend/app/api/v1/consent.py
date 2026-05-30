"""Consent endpoints — grant, list, revoke."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_access
from app.core.security import Principal, get_current_principal, require_role
from app.db.models.consent import Consent
from app.db.models.patient import Patient
from app.db.session import get_db
from app.schemas.consent import ConsentCreate, ConsentOut

router = APIRouter(prefix="/consents", tags=["consents"])


def _to_out(c: Consent) -> ConsentOut:
    return ConsentOut(
        id=c.id,
        patient_id=c.patient_id,
        scope=c.scope,  # type: ignore[arg-type]
        purpose=c.purpose,
        granted_at=c.granted_at,
        expires_at=c.expires_at,
        revoked_at=c.revoked_at,
    )


@router.post(
    "",
    response_model=ConsentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Grant consent",
)
async def grant(
    body: ConsentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_role("worker"))],
) -> ConsentOut:
    if not await db.get(Patient, body.patient_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")

    c = Consent(
        patient_id=body.patient_id,
        scope=body.scope,
        purpose=body.purpose,
        granted_at=datetime.now(UTC),
        expires_at=body.expires_at,
        granted_by=principal.subject,
    )
    db.add(c)
    await db.flush()
    await record_access(
        db,
        principal=principal,
        resource_type="Consent",
        resource_id=c.id,
        action="grant",
        purpose=body.purpose,
    )
    return _to_out(c)


@router.get("/by-patient/{patient_id}", response_model=list[ConsentOut])
async def list_for_patient(
    patient_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> list[ConsentOut]:
    if principal.role == "citizen":
        patient = await db.get(Patient, patient_id)
        if not patient or patient.nin != principal.subject:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your record")

    stmt = (
        select(Consent)
        .where(Consent.patient_id == patient_id)
        .order_by(Consent.granted_at.desc())
    )
    rows = (await db.scalars(stmt)).all()
    return [_to_out(c) for c in rows]


@router.post("/{consent_id}/revoke", response_model=ConsentOut)
async def revoke(
    consent_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> ConsentOut:
    c = await db.get(Consent, consent_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Consent not found")
    # Citizens may only revoke consents tied to their own patient record.
    # Prior to this check, any valid citizen JWT could revoke any consent
    # by guessing IDs — same guard pattern as list_for_patient above.
    if principal.role == "citizen":
        patient = await db.get(Patient, c.patient_id)
        if patient is None or patient.nin != principal.subject:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your consent")
    if c.revoked_at is not None:
        return _to_out(c)
    c.revoked_at = datetime.now(UTC)
    await db.flush()
    await record_access(
        db,
        principal=principal,
        resource_type="Consent",
        resource_id=c.id,
        action="revoke",
        purpose="patient-request",
    )
    return _to_out(c)

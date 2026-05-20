"""FHIR R4-compliant exchange endpoints.

These endpoints accept and return canonical FHIR JSON. They are the surface
external systems integrate with (DHIS2 Tracker, OpenMRS Sync, HAPI FHIR).
Internal APIs are not affected by changes here, so the FHIR contract can
stay stable even as the internal schema evolves.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_access
from app.core.security import Principal, get_current_principal, require_role
from app.db.models.patient import Patient
from app.db.session import get_db
from app.fhir.bundle import Bundle, BundleEntry
from app.fhir.patient import PatientResource
from app.fhir.primitives import Address, ContactPoint, HumanName, Identifier
from app.schemas.common import CodeSystems

fhir_router = APIRouter(tags=["fhir"])


# ── CapabilityStatement (FHIR's "what do you support?" endpoint) ─────────────


@fhir_router.get("/metadata", summary="FHIR R4 CapabilityStatement")
async def capability() -> dict[str, Any]:
    return {
        "resourceType": "CapabilityStatement",
        "status": "active",
        "date": datetime.now(UTC).isoformat(),
        "kind": "instance",
        "fhirVersion": "4.0.1",
        "format": ["application/fhir+json"],
        "implementation": {
            "description": "HealthSync Uganda — Interoperable National Digital Health Platform",
            "url": "/fhir",
        },
        "rest": [
            {
                "mode": "server",
                "resource": [
                    {
                        "type": "Patient",
                        "interaction": [
                            {"code": "read"},
                            {"code": "search-type"},
                            {"code": "create"},
                        ],
                        "searchParam": [
                            {"name": "identifier", "type": "token"},
                            {"name": "family", "type": "string"},
                            {"name": "birthdate", "type": "date"},
                        ],
                    },
                    {
                        "type": "Encounter",
                        "interaction": [{"code": "read"}, {"code": "search-type"}],
                    },
                    {
                        "type": "Observation",
                        "interaction": [{"code": "search-type"}],
                    },
                    {
                        "type": "MedicationDispense",
                        "interaction": [{"code": "search-type"}],
                    },
                ],
            }
        ],
    }


# ── Patient ──────────────────────────────────────────────────────────────────


def _patient_to_fhir(p: Patient) -> PatientResource:
    telecom: list[ContactPoint] = []
    if p.phone:
        telecom.append(ContactPoint(system="phone", value=p.phone, use="mobile"))
    if p.email:
        telecom.append(ContactPoint(system="email", value=p.email))

    return PatientResource(
        id=p.id,
        identifier=[
            Identifier(
                use="official",
                system=CodeSystems.UG_NIN,
                value=p.nin,
            )
        ],
        name=[HumanName(family=p.family_name, given=[p.given_name])],
        telecom=telecom,
        gender=p.gender,  # type: ignore[arg-type]
        birthDate=p.birth_date,
        deceasedBoolean=p.deceased,
        address=[
            Address(
                district=p.district,
                line=[v for v in (p.village, p.parish, p.sub_county) if v],
            )
        ],
    )


@fhir_router.get("/Patient/{patient_id}", summary="Read Patient")
async def read_patient(
    patient_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> dict[str, Any]:
    p = await db.get(Patient, patient_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")
    await record_access(
        db,
        principal=principal,
        resource_type="Patient",
        resource_id=p.id,
        action="fhir-read",
        purpose="interop",
    )
    return _patient_to_fhir(p).model_dump(by_alias=True, mode="json")


@fhir_router.get("/Patient", summary="Search Patient")
async def search_patient(
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_role("worker"))],
    identifier: str | None = Query(
        None,
        description="`system|value` form (e.g. `https://nira.go.ug/identifiers/nin|CM12345…`)",
    ),
    family: str | None = None,
) -> dict[str, Any]:
    stmt = select(Patient)
    if identifier:
        if "|" in identifier:
            _, value = identifier.split("|", 1)
        else:
            value = identifier
        stmt = stmt.where(Patient.nin == value.upper())
    if family:
        stmt = stmt.where(Patient.family_name.ilike(f"%{family}%"))

    rows = (await db.scalars(stmt.limit(50))).all()
    bundle = Bundle(
        type="searchset",
        total=len(rows),
        entry=[
            BundleEntry(
                fullUrl=f"/fhir/Patient/{p.id}",
                resource=_patient_to_fhir(p).model_dump(by_alias=True, mode="json"),
                search={"mode": "match", "score": 1.0},
            )
            for p in rows
        ],
    )
    return bundle.model_dump(by_alias=True, mode="json")

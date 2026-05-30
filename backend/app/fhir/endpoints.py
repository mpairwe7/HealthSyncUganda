"""FHIR R4-compliant exchange endpoints.

These endpoints accept and return canonical FHIR JSON. They are the surface
external systems integrate with (DHIS2 Tracker, OpenMRS Sync, HAPI FHIR).
Internal APIs are not affected by changes here, so the FHIR contract can
stay stable even as the internal schema evolves.

Access control mirrors the REST surface — every read goes through
`app.core.access.can_read_patient` / `can_read_encounter` so a citizen
token can only see their own (or caregiver-linked) records, and a worker
token is scoped to their facility.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clinical.unepi_schedule import CODE_TO_ANTIGEN, SNOMED_SYSTEM
from app.core.access import (
    can_read_encounter,
    can_read_patient,
    patient_visibility_filter,
)
from app.core.audit import record_access
from app.core.security import Principal, get_current_principal
from app.db.models.encounter import Encounter, Observation
from app.db.models.facility import Facility
from app.db.models.patient import Patient
from app.db.models.supply import StockEvent, SupplyItem
from app.db.session import get_db
from app.fhir.bundle import Bundle, BundleEntry
from app.fhir.encounter import EncounterResource, ObservationResource
from app.fhir.immunization import ImmunizationResource
from app.fhir.patient import PatientResource
from app.fhir.primitives import (
    Address,
    CodeableConcept,
    Coding,
    ContactPoint,
    HumanName,
    Identifier,
    Meta,
    Period,
    Quantity,
    Reference,
)
from app.fhir.supply import MedicationDispenseResource
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
                        "searchParam": [
                            {"name": "patient", "type": "reference"},
                            {"name": "date", "type": "date"},
                        ],
                    },
                    {
                        "type": "Observation",
                        "interaction": [
                            {"code": "read"},
                            {"code": "search-type"},
                            {"code": "create"},
                        ],
                        "searchParam": [
                            {"name": "patient", "type": "reference"},
                            {"name": "code", "type": "token"},
                            {"name": "_count", "type": "number"},
                        ],
                    },
                    {
                        "type": "Immunization",
                        "interaction": [{"code": "search-type"}],
                        "searchParam": [{"name": "patient", "type": "reference"}],
                    },
                    {
                        "type": "MedicationDispense",
                        "interaction": [{"code": "search-type"}],
                        "searchParam": [{"name": "patient", "type": "reference"}],
                    },
                ],
            }
        ],
    }


# ── Mappers (internal ORM → FHIR JSON) ───────────────────────────────────────


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


def _encounter_to_fhir(enc: Encounter) -> EncounterResource:
    """ORM → FHIR R4 Encounter projection."""
    period = Period(start=enc.started_at, end=enc.ended_at)
    reason_codes: list[CodeableConcept] = []
    if enc.reason:
        reason_codes.append(CodeableConcept(text=enc.reason))
    # FHIR R4 Encounter.status is one of a fixed set; the internal model
    # uses the same vocabulary so map directly.
    status_value = enc.status if enc.status in {
        "planned", "arrived", "triaged", "in-progress", "onleave", "finished", "cancelled"
    } else "in-progress"
    return EncounterResource(
        id=enc.id,
        meta=Meta(lastUpdated=enc.updated_at),
        status=status_value,  # type: ignore[arg-type]
        subject=Reference(reference=f"Patient/{enc.patient_id}"),
        period=period,
        reasonCode=reason_codes,
        serviceProvider=Reference(reference=f"Organization/{enc.facility_id}"),
    )


def _observation_to_fhir(obs: Observation) -> ObservationResource:
    """ORM → FHIR R4 Observation projection."""
    code = CodeableConcept(
        coding=[Coding(system=obs.code_system, code=obs.code, display=obs.display)],
        text=obs.display,
    )
    value_quantity: Quantity | None = None
    if obs.value_quantity is not None:
        value_quantity = Quantity(value=obs.value_quantity, unit=obs.value_unit)
    return ObservationResource(
        id=obs.id,
        meta=Meta(lastUpdated=obs.updated_at),
        status="final",
        code=code,
        subject=Reference(reference=f"Patient/{obs.patient_id}"),
        encounter=(
            Reference(reference=f"Encounter/{obs.encounter_id}")
            if obs.encounter_id
            else None
        ),
        effectiveDateTime=obs.effective_at,
        valueQuantity=value_quantity,
        valueString=obs.value_string,
    )


def _observation_to_immunization(obs: Observation) -> ImmunizationResource | None:
    """Project a vaccine Observation as an FHIR Immunization.

    Returns None if the observation isn't a SNOMED-coded UNEPI vaccine
    (i.e. shouldn't appear in the Immunization view).
    """
    if obs.code_system != SNOMED_SYSTEM or obs.code not in CODE_TO_ANTIGEN:
        return None
    return ImmunizationResource(
        id=obs.id,
        meta=Meta(lastUpdated=obs.updated_at),
        status="completed",
        vaccineCode=CodeableConcept(
            coding=[Coding(system=obs.code_system, code=obs.code, display=obs.display)],
            text=obs.display,
        ),
        patient=Reference(reference=f"Patient/{obs.patient_id}"),
        encounter=(
            Reference(reference=f"Encounter/{obs.encounter_id}")
            if obs.encounter_id
            else None
        ),
        occurrenceDateTime=obs.effective_at,
    )


def _dispense_to_fhir(
    ev: StockEvent, item: SupplyItem
) -> MedicationDispenseResource:
    """Project a `dispensed` StockEvent as an FHIR MedicationDispense."""
    return MedicationDispenseResource(
        id=ev.id,
        status="completed",
        medicationCodeableConcept=CodeableConcept(
            coding=[Coding(system="urn:ietf:rfc:3986", code=item.code, display=item.name)],
            text=item.name,
        ),
        # Stock events reference a patient via `reference_id` (typically the
        # encounter_id); we surface the encounter in `subject` only when the
        # reference resolves to a known patient at the call site. For now,
        # we leave subject pointing at the facility-anonymous encounter.
        subject=Reference(reference=f"Encounter/{ev.reference_id or 'unknown'}"),
        location=Reference(reference=f"Organization/{ev.facility_id}"),
        quantity=Quantity(value=abs(ev.quantity_delta), unit=item.unit),
        whenHandedOver=ev.occurred_at,
    )


# ── Patient ──────────────────────────────────────────────────────────────────


@fhir_router.get("/Patient/{patient_id}", summary="Read Patient")
async def read_patient(
    patient_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> dict[str, Any]:
    p = await db.get(Patient, patient_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")
    if not await can_read_patient(principal, p, db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your record")
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
    principal: Annotated[Principal, Depends(get_current_principal)],
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

    # SQL-level visibility filter — never returns rows the principal can't
    # see, even if their query matched. Avoids per-row Python authz checks
    # (which would be O(n) round-trips on a 50-row bundle).
    scope = patient_visibility_filter(principal)
    if scope:
        stmt = stmt.where(and_(*scope))

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


# ── Encounter ────────────────────────────────────────────────────────────────


@fhir_router.get("/Encounter/{encounter_id}", summary="Read Encounter")
async def read_encounter(
    encounter_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> dict[str, Any]:
    enc = await db.get(Encounter, encounter_id)
    if not enc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Encounter not found")
    if not await can_read_encounter(principal, enc, db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your encounter")
    await record_access(
        db,
        principal=principal,
        resource_type="Encounter",
        resource_id=enc.id,
        action="fhir-read",
        purpose="interop",
    )
    return _encounter_to_fhir(enc).model_dump(by_alias=True, mode="json")


@fhir_router.get("/Encounter", summary="Search Encounter")
async def search_encounter(
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    patient: str | None = Query(
        None, description="Patient reference (raw id or `Patient/{id}` form)"
    ),
    count: int = Query(50, alias="_count", ge=1, le=200),
) -> dict[str, Any]:
    if not patient:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "`patient` search parameter is required.",
        )
    patient_id = patient.split("/")[-1]
    p = await db.get(Patient, patient_id)
    if p is None:
        return Bundle(type="searchset", total=0, entry=[]).model_dump(
            by_alias=True, mode="json"
        )
    if not await can_read_patient(principal, p, db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your record")

    stmt = (
        select(Encounter)
        .where(Encounter.patient_id == patient_id)
        .order_by(Encounter.started_at.desc())
        .limit(count)
    )
    # Encounter-level facility scoping for workers/pharmacists.
    if principal.role in ("worker", "pharmacist") and principal.facility_id:
        stmt = stmt.where(Encounter.facility_id == principal.facility_id)

    rows = (await db.scalars(stmt)).all()
    bundle = Bundle(
        type="searchset",
        total=len(rows),
        entry=[
            BundleEntry(
                fullUrl=f"/fhir/Encounter/{enc.id}",
                resource=_encounter_to_fhir(enc).model_dump(by_alias=True, mode="json"),
                search={"mode": "match", "score": 1.0},
            )
            for enc in rows
        ],
    )
    return bundle.model_dump(by_alias=True, mode="json")


# ── Observation ──────────────────────────────────────────────────────────────


@fhir_router.get("/Observation/{observation_id}", summary="Read Observation")
async def read_observation(
    observation_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> dict[str, Any]:
    obs = await db.get(Observation, observation_id)
    if not obs:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Observation not found")
    # Resolve owning patient for the auth check.
    p = await db.get(Patient, obs.patient_id)
    if p is None or not await can_read_patient(principal, p, db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your record")
    await record_access(
        db,
        principal=principal,
        resource_type="Observation",
        resource_id=obs.id,
        action="fhir-read",
        purpose="interop",
    )
    return _observation_to_fhir(obs).model_dump(by_alias=True, mode="json")


@fhir_router.get("/Observation", summary="Search Observation")
async def search_observation(
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    patient: str | None = Query(None, description="Patient reference (or raw id)"),
    code: str | None = Query(
        None, description="Token `system|code` or just `code`"
    ),
    count: int = Query(50, alias="_count", ge=1, le=500),
) -> dict[str, Any]:
    if not patient:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "`patient` search parameter is required.",
        )
    patient_id = patient.split("/")[-1]
    p = await db.get(Patient, patient_id)
    if p is None:
        return Bundle(type="searchset", total=0, entry=[]).model_dump(
            by_alias=True, mode="json"
        )
    if not await can_read_patient(principal, p, db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your record")

    stmt = (
        select(Observation)
        .where(Observation.patient_id == patient_id)
        .order_by(Observation.effective_at.desc())
        .limit(count)
    )
    if code:
        if "|" in code:
            system, value = code.split("|", 1)
            stmt = stmt.where(
                Observation.code_system == system, Observation.code == value
            )
        else:
            stmt = stmt.where(Observation.code == code)
    rows = (await db.scalars(stmt)).all()
    bundle = Bundle(
        type="searchset",
        total=len(rows),
        entry=[
            BundleEntry(
                fullUrl=f"/fhir/Observation/{obs.id}",
                resource=_observation_to_fhir(obs).model_dump(by_alias=True, mode="json"),
                search={"mode": "match", "score": 1.0},
            )
            for obs in rows
        ],
    )
    return bundle.model_dump(by_alias=True, mode="json")


@fhir_router.post(
    "/Observation",
    summary="Create Observation",
    status_code=status.HTTP_201_CREATED,
)
async def create_observation(
    body: Annotated[dict[str, Any], Body()],
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> dict[str, Any]:
    """Accept a FHIR-shaped Observation payload and persist it.

    Requires `subject.reference` ("Patient/{id}") and `code.coding[0]`. If no
    `encounter` is supplied, we attach the observation to the patient's most
    recent encounter — or synthesise a 'fhir-direct' encounter at the
    caller's facility (most realistic for external integrations).
    """
    # Validate minimum-required FHIR shape.
    if body.get("resourceType") != "Observation":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "resourceType must be 'Observation'.",
        )
    subject_ref = ((body.get("subject") or {}).get("reference") or "").strip()
    if not subject_ref.startswith("Patient/"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "subject.reference is required and must be Patient/{id}.",
        )
    patient_id = subject_ref.split("/", 1)[1]
    p = await db.get(Patient, patient_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")
    if not await can_read_patient(principal, p, db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your record")

    coding_list = ((body.get("code") or {}).get("coding") or [])
    if not coding_list:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "code.coding[0] is required.",
        )
    coding = coding_list[0]
    if not coding.get("system") or not coding.get("code"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "code.coding[0].system and .code are required.",
        )

    # Resolve or create the parent encounter.
    encounter_id: str | None = None
    enc_ref = ((body.get("encounter") or {}).get("reference") or "").strip()
    if enc_ref.startswith("Encounter/"):
        encounter_id = enc_ref.split("/", 1)[1]
        enc = await db.get(Encounter, encounter_id)
        if enc is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Encounter not found")
        if not await can_read_encounter(principal, enc, db):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Not your encounter"
            )
    else:
        # Pick the patient's most recent encounter; fallback synthesises a
        # 'fhir-direct' encounter so the FK constraint stays intact.
        latest = (
            await db.scalars(
                select(Encounter)
                .where(Encounter.patient_id == p.id)
                .order_by(Encounter.started_at.desc())
                .limit(1)
            )
        ).one_or_none()
        if latest is not None and (
            principal.role in ("district_admin", "ministry_admin")
            or latest.facility_id == principal.facility_id
        ):
            encounter_id = latest.id
        else:
            facility_id = principal.facility_id or p.enrolling_facility_id
            if facility_id is None:
                # Last resort: pick any facility row so the FK is valid.
                any_fac = (await db.scalars(select(Facility).limit(1))).one_or_none()
                if any_fac is None:
                    raise HTTPException(
                        status.HTTP_409_CONFLICT,
                        "No facility available to anchor the observation.",
                    )
                facility_id = any_fac.id
            synth = Encounter(
                patient_id=p.id,
                facility_id=facility_id,
                reason="FHIR-direct observation",
                status="finished",
                started_at=datetime.now(UTC),
                ended_at=datetime.now(UTC),
                recorded_by=principal.subject,
            )
            db.add(synth)
            await db.flush()
            encounter_id = synth.id

    # Extract value.
    vq = body.get("valueQuantity") or {}
    value_quantity = float(vq["value"]) if "value" in vq else None
    value_unit = vq.get("unit")
    value_string = body.get("valueString")

    effective = body.get("effectiveDateTime")
    if effective:
        effective_at = datetime.fromisoformat(effective.replace("Z", "+00:00"))
    else:
        effective_at = datetime.now(UTC)

    obs = Observation(
        encounter_id=encounter_id,
        patient_id=p.id,
        code_system=coding["system"],
        code=coding["code"],
        display=coding.get("display"),
        value_quantity=value_quantity,
        value_unit=value_unit,
        value_string=value_string,
        effective_at=effective_at,
        recorded_by=principal.subject,
    )
    db.add(obs)
    await db.flush()
    await record_access(
        db,
        principal=principal,
        resource_type="Observation",
        resource_id=obs.id,
        action="fhir-create",
        purpose="interop",
        extra={"code": coding["code"], "system": coding["system"]},
    )
    return _observation_to_fhir(obs).model_dump(by_alias=True, mode="json")


# ── Immunization (derived from SNOMED vaccine Observations) ──────────────────


@fhir_router.get("/Immunization", summary="Search Immunization")
async def search_immunization(
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    patient: str | None = Query(None, description="Patient reference (or raw id)"),
    count: int = Query(50, alias="_count", ge=1, le=500),
) -> dict[str, Any]:
    if not patient:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "`patient` search parameter is required.",
        )
    patient_id = patient.split("/")[-1]
    p = await db.get(Patient, patient_id)
    if p is None:
        return Bundle(type="searchset", total=0, entry=[]).model_dump(
            by_alias=True, mode="json"
        )
    if not await can_read_patient(principal, p, db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your record")

    rows = (
        await db.scalars(
            select(Observation)
            .where(
                Observation.patient_id == patient_id,
                Observation.code_system == SNOMED_SYSTEM,
                Observation.code.in_(list(CODE_TO_ANTIGEN.keys())),
            )
            .order_by(Observation.effective_at.desc())
            .limit(count)
        )
    ).all()
    entries: list[BundleEntry] = []
    for obs in rows:
        imm = _observation_to_immunization(obs)
        if imm is None:
            continue
        entries.append(
            BundleEntry(
                fullUrl=f"/fhir/Immunization/{imm.id}",
                resource=imm.model_dump(by_alias=True, mode="json"),
                search={"mode": "match", "score": 1.0},
            )
        )
    bundle = Bundle(type="searchset", total=len(entries), entry=entries)
    return bundle.model_dump(by_alias=True, mode="json")


# ── MedicationDispense (derived from dispensed StockEvents) ──────────────────


@fhir_router.get("/MedicationDispense", summary="Search MedicationDispense")
async def search_medication_dispense(
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    patient: str | None = Query(None, description="Patient reference (or raw id)"),
    count: int = Query(50, alias="_count", ge=1, le=500),
) -> dict[str, Any]:
    """List dispense events. When `patient` is supplied we resolve the
    patient's encounters and surface dispense events that reference them
    via `StockEvent.reference_id`.
    """
    if not patient:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "`patient` search parameter is required.",
        )
    patient_id = patient.split("/")[-1]
    p = await db.get(Patient, patient_id)
    if p is None:
        return Bundle(type="searchset", total=0, entry=[]).model_dump(
            by_alias=True, mode="json"
        )
    if not await can_read_patient(principal, p, db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your record")

    # Encounters this patient owns — supports the StockEvent.reference_id link.
    enc_ids = [
        e_id
        for (e_id,) in (
            await db.execute(
                select(Encounter.id).where(Encounter.patient_id == patient_id)
            )
        ).all()
    ]
    if not enc_ids:
        return Bundle(type="searchset", total=0, entry=[]).model_dump(
            by_alias=True, mode="json"
        )

    events = (
        await db.scalars(
            select(StockEvent)
            .where(
                StockEvent.event_type == "dispensed",
                StockEvent.reference_id.in_(enc_ids),
            )
            .order_by(StockEvent.occurred_at.desc())
            .limit(count)
        )
    ).all()
    if not events:
        return Bundle(type="searchset", total=0, entry=[]).model_dump(
            by_alias=True, mode="json"
        )

    # Bulk-fetch the referenced supply items so we don't re-query per row.
    item_ids = list({ev.supply_item_id for ev in events})
    items = {
        it.id: it
        for it in (
            await db.scalars(select(SupplyItem).where(SupplyItem.id.in_(item_ids)))
        ).all()
    }
    entries: list[BundleEntry] = []
    for ev in events:
        item = items.get(ev.supply_item_id)
        if item is None:
            continue
        md = _dispense_to_fhir(ev, item)
        # Override subject — we have the real patient here, not just an
        # encounter reference, so make the FHIR resource clinically useful.
        md_dict = md.model_dump(by_alias=True, mode="json")
        md_dict["subject"] = {"reference": f"Patient/{patient_id}"}
        entries.append(
            BundleEntry(
                fullUrl=f"/fhir/MedicationDispense/{ev.id}",
                resource=md_dict,
                search={"mode": "match", "score": 1.0},
            )
        )
    bundle = Bundle(type="searchset", total=len(entries), entry=entries)
    return bundle.model_dump(by_alias=True, mode="json")

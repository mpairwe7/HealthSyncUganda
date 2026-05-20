"""Supply-chain FHIR resources: MedicationDispense, SupplyDelivery."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.fhir.primitives import (
    CodeableConcept,
    FhirModel,
    Quantity,
    Reference,
)


class MedicationDispenseResource(FhirModel):
    """https://hl7.org/fhir/R4/medicationdispense.html"""

    resourceType: Literal["MedicationDispense"] = "MedicationDispense"
    id: str | None = None
    status: Literal[
        "preparation",
        "in-progress",
        "cancelled",
        "on-hold",
        "completed",
        "entered-in-error",
        "stopped",
        "declined",
        "unknown",
    ] = "completed"
    medicationCodeableConcept: CodeableConcept
    subject: Reference
    performer: list[Reference] = Field(default_factory=list)
    location: Reference | None = None
    quantity: Quantity
    daysSupply: Quantity | None = None
    whenHandedOver: datetime
    note: list[str] = Field(default_factory=list)


class SupplyDeliveryResource(FhirModel):
    """https://hl7.org/fhir/R4/supplydelivery.html — transfers between facilities."""

    resourceType: Literal["SupplyDelivery"] = "SupplyDelivery"
    id: str | None = None
    status: Literal["in-progress", "completed", "abandoned", "entered-in-error"] = "completed"
    suppliedItem_quantity: Quantity = Field(..., alias="suppliedItem.quantity")
    suppliedItem_itemCodeableConcept: CodeableConcept = Field(
        ..., alias="suppliedItem.itemCodeableConcept"
    )
    occurrenceDateTime: datetime
    supplier: Reference
    destination: Reference

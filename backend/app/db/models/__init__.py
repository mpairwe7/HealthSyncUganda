"""All ORM models. Importing this package registers them with the metadata."""

from app.db.models.audit_log import AuditLog
from app.db.models.caregiver import CaregiverLink
from app.db.models.consent import Consent
from app.db.models.encounter import Encounter, Observation
from app.db.models.facility import Facility
from app.db.models.patient import Patient
from app.db.models.supply import (
    StockBatch,
    StockEvent,
    StockTransfer,
    SupplyItem,
)
from app.db.models.user import User

__all__ = [
    "AuditLog",
    "CaregiverLink",
    "Consent",
    "Encounter",
    "Facility",
    "Observation",
    "Patient",
    "StockBatch",
    "StockEvent",
    "StockTransfer",
    "SupplyItem",
    "User",
]

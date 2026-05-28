"""FHIR R4 resources, normalised for Uganda's national identifiers.

We use FHIR R4 as the wire format for *interoperability*; internally the DB
uses a slimmer relational schema for performance. The mappers in this module
convert between the two so neither side leaks into the other.
"""

from app.fhir.bundle import Bundle, BundleEntry
from app.fhir.encounter import EncounterResource, ObservationResource
from app.fhir.immunization import ImmunizationResource
from app.fhir.patient import PatientResource
from app.fhir.supply import MedicationDispenseResource

__all__ = [
    "Bundle",
    "BundleEntry",
    "EncounterResource",
    "ImmunizationResource",
    "MedicationDispenseResource",
    "ObservationResource",
    "PatientResource",
]

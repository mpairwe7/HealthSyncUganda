"""Validator tests — Uganda NIN, phone, FHIR Patient invariants."""

import pytest
from pydantic import ValidationError

from app.fhir.patient import PatientResource
from app.fhir.primitives import HumanName, Identifier
from app.schemas.common import _validate_nin, _validate_ug_phone


def test_nin_accepts_valid():
    assert _validate_nin("cm85051712345x") == "CM85051712345X"


def test_nin_rejects_invalid():
    with pytest.raises(ValueError):
        _validate_nin("INVALID")


def test_phone_normalises():
    assert _validate_ug_phone("0772 111 222") == "+256772111222"
    assert _validate_ug_phone("+256-772-111-222") == "+256772111222"


def test_fhir_patient_requires_nin_identifier():
    with pytest.raises(ValidationError):
        PatientResource(
            identifier=[Identifier(system="other", value="abc")],
            name=[HumanName(family="Doe", given=["Jane"])],
            gender="female",
            birthDate="1990-01-01",
        )

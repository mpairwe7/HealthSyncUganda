"""FHIR Bundle — used for search responses and batched transactions."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.fhir.primitives import FhirModel


class BundleEntry(FhirModel):
    fullUrl: str | None = None
    resource: dict[str, Any]
    search: dict[str, Any] | None = None  # { mode: "match", score: 1.0 }


class Bundle(FhirModel):
    """https://hl7.org/fhir/R4/bundle.html"""

    resourceType: Literal["Bundle"] = "Bundle"
    type: Literal[
        "document",
        "message",
        "transaction",
        "transaction-response",
        "batch",
        "batch-response",
        "history",
        "searchset",
        "collection",
    ]
    total: int | None = None
    link: list[dict[str, str]] = Field(default_factory=list)
    entry: list[BundleEntry] = Field(default_factory=list)

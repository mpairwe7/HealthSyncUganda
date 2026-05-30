"""v1 API router — assembles versioned endpoints into a single namespace."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    analytics,
    auth,
    consent,
    encounters,
    facilities,
    interop,
    me,
    patients,
    supply,
)

api_v1_router = APIRouter()

api_v1_router.include_router(auth.router)
api_v1_router.include_router(patients.router)
api_v1_router.include_router(encounters.router)
api_v1_router.include_router(consent.router)
api_v1_router.include_router(facilities.router)
api_v1_router.include_router(supply.router)
api_v1_router.include_router(analytics.router)
api_v1_router.include_router(interop.router)
api_v1_router.include_router(me.router)

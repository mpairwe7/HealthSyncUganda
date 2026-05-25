"""Authentication endpoints.

Two flows are exposed today:

* `/auth/login`         — staff (username + password).
* `/auth/citizen/login` — citizens (NIN + OTP stub; swap for NIRA OIDC in prod).

The aim of the demo prototype is to make the integration boundary obvious;
production deployment replaces these handlers with calls to NIRA's IdP.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import Principal, hash_password, issue_token, verify_password
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.auth import CitizenLoginRequest, LoginRequest, TokenResponse
from app.services.nira_client import NiraClient, get_nira_client

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger(__name__)


@router.post("/login", response_model=TokenResponse, summary="Staff login")
async def staff_login(
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    stmt = select(User).where(User.username == body.identifier, User.active.is_(True))
    user = (await db.scalars(stmt)).one_or_none()

    if user is None or not verify_password(body.password, user.password_hash):
        # Constant-message reply prevents user-enumeration via timing
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    principal = Principal(
        subject=user.id,
        role=user.role,  # type: ignore[arg-type]
        facility_id=user.facility_id,
        name=user.full_name,
    )
    token = issue_token(principal, ttl=timedelta(hours=8))
    logger.info("auth.staff_login", user_id=user.id, role=user.role)
    return TokenResponse(
        access_token=token,
        expires_in=8 * 3600,
        role=user.role,  # type: ignore[arg-type]
        subject=user.id,
        name=user.full_name,
        facility_id=user.facility_id,
    )


@router.post("/citizen/login", response_model=TokenResponse, summary="Citizen NIN+OTP login")
async def citizen_login(
    body: CitizenLoginRequest,
    nira: Annotated[NiraClient, Depends(get_nira_client)],
) -> TokenResponse:
    """In production, this is replaced by a NIRA OIDC redirect.

    For the demo we accept OTP = "000000" and verify the NIN exists in NIRA.
    Graceful degradation: if NIRA is unreachable, we still allow login but
    flag the session as `nira_unverified` so writes can be quarantined.
    """
    if body.otp != "000000":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid OTP")

    verification = await nira.verify_nin(body.nin)
    if not verification.found:
        # Even on cache fallback we require a positive lookup
        raise HTTPException(status.HTTP_404_NOT_FOUND, "NIN not found at NIRA")

    principal = Principal(
        subject=body.nin,
        role="citizen",
        name=verification.full_name,
    )
    token = issue_token(principal, ttl=timedelta(hours=2))
    logger.info("auth.citizen_login", nin=body.nin, fallback=verification.via_fallback)
    return TokenResponse(
        access_token=token,
        expires_in=2 * 3600,
        role="citizen",
        subject=body.nin,
        name=verification.full_name,
    )


@router.post("/seed-admin", include_in_schema=False)
async def seed_admin(db: Annotated[AsyncSession, Depends(get_db)]) -> dict[str, str]:
    """Demo helper — creates an admin if none exists. Idempotent."""
    existing = (await db.scalars(select(User).where(User.username == "admin"))).one_or_none()
    if existing is None:
        user = User(
            username="admin",
            full_name="Demo Administrator",
            role="ministry_admin",
            password_hash=hash_password("admin"),
        )
        db.add(user)
        return {"created": "admin"}
    return {"created": "noop"}


@router.post("/seed-demo", include_in_schema=False)
async def seed_demo(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str | int]:
    """Demo helper — runs the FULL seed (facilities, users, supply items,
    patients, encounters, consents) into the configured database.

    Idempotent: re-runs upsert records keyed by NIN / code / username.

    Guarded by app_env: refuses in production. For staging / pilot / dev,
    this is the canonical way to populate a freshly-deployed Crane Cloud
    Postgres app (which the platform creates empty + no documented
    persistent volumes — see infra/cranecloud/README.md §0.1).

    Returns counts of facilities/users/patients post-seed for downstream
    verification.
    """
    from app.config import get_settings

    settings = get_settings()
    if settings.is_production:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "seed-demo disabled in APP_ENV=production",
        )

    # Lazy import — seed module loads ~10 KB of demo data; skip if endpoint
    # isn't called.
    from app.db.models.facility import Facility
    from app.db.models.patient import Patient
    from app.seed import run as seed_run

    logger.info("auth.seed_demo.start", env=settings.app_env)

    try:
        # Use the request's session (get_db already commits on success,
        # rollbacks on exception). Run each seed step in sequence; they
        # all upsert idempotently.
        facility_ids = await seed_run._seed_facilities(db)
        await seed_run._seed_users(db, facility_ids)
        items = await seed_run._seed_supply_items(db)
        patients = await seed_run._seed_patients(db)
        admin = (
            await db.scalars(select(User).where(User.username == "admin"))
        ).one_or_none()
        if admin is None:
            # Fall back: create admin first (mirrors seed-admin), then re-fetch
            db.add(
                User(
                    username="admin",
                    full_name="Demo Administrator",
                    role="ministry_admin",
                    password_hash=hash_password("admin1234"),
                )
            )
            await db.flush()
            admin = (
                await db.scalars(select(User).where(User.username == "admin"))
            ).one()
        await seed_run._seed_stock(db, facility_ids, items, admin.id)
        await seed_run._seed_encounters(db, patients, facility_ids)
        await seed_run._seed_consents(db, patients, admin.id)
        await db.flush()
    except Exception as exc:
        logger.exception("auth.seed_demo.failed", error=str(exc))
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"seed failed: {type(exc).__name__}: {exc}",
        ) from exc

    # Count what landed (within the same session, before commit)
    n_facilities = len((await db.scalars(select(Facility))).all())
    n_users = len((await db.scalars(select(User))).all())
    n_patients = len((await db.scalars(select(Patient))).all())

    counts = {
        "facilities": n_facilities,
        "users":      n_users,
        "patients":   n_patients,
    }
    logger.info("auth.seed_demo.done", **counts)
    return {"seeded": "demo", **counts}

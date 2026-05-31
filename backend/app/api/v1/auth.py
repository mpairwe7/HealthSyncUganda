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

from app.config import get_settings
from app.core.logging import get_logger
from app.core.redis_client import get_redis
from app.core.security import Principal, hash_password, issue_token, verify_password
from app.db.models.facility import Facility
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.auth import CitizenLoginRequest, LoginRequest, TokenResponse
from app.services.nira_client import NiraClient, get_nira_client

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger(__name__)

# Per-identifier login throttle. Keyed on the submitted username/NIN — NOT the
# client IP — so it can't be sidestepped by spoofing X-Forwarded-For, and a
# shared clinic NAT can't lock everyone out. Counts *consecutive failed*
# attempts and resets on success, so legitimate repeated logins never trip it.
# Degrades open if Redis is unavailable (mirrors RateLimitMiddleware).
_AUTH_FAIL_LIMIT = 5
_AUTH_FAIL_WINDOW_SECONDS = 300


def _auth_throttle_key(identifier: str) -> str:
    return f"auththrottle:{identifier.strip().lower()}"


async def _enforce_login_throttle(identifier: str) -> None:
    try:
        redis = await get_redis()
        attempts = await redis.get(_auth_throttle_key(identifier))
    except Exception as exc:  # degrade open — never block logins on a Redis blip
        logger.warning("auth.throttle_disabled", error=str(exc))
        return
    if attempts is not None and int(attempts) >= _AUTH_FAIL_LIMIT:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many failed login attempts — wait a few minutes and try again.",
            headers={"Retry-After": str(_AUTH_FAIL_WINDOW_SECONDS)},
        )


async def _record_login_failure(identifier: str) -> None:
    try:
        redis = await get_redis()
        key = _auth_throttle_key(identifier)
        attempts = await redis.incr(key)
        if attempts == 1:
            await redis.expire(key, _AUTH_FAIL_WINDOW_SECONDS)
    except Exception as exc:  # best-effort — the throttle is advisory
        logger.warning("auth.throttle_record_failed", error=str(exc))


async def _reset_login_failures(identifier: str) -> None:
    try:
        redis = await get_redis()
        await redis.delete(_auth_throttle_key(identifier))
    except Exception:  # best-effort — the throttle is advisory
        return


@router.post("/login", response_model=TokenResponse, summary="Staff login")
async def staff_login(
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    await _enforce_login_throttle(body.identifier)
    stmt = select(User).where(User.username == body.identifier, User.active.is_(True))
    user = (await db.scalars(stmt)).one_or_none()

    if user is None or not verify_password(body.password, user.password_hash):
        await _record_login_failure(body.identifier)
        # Constant-message reply prevents user-enumeration via timing
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    await _reset_login_failures(body.identifier)

    # Resolve the district at login time so it can be embedded as a JWT claim
    # — avoids a per-request facility join when district_admins / workers hit
    # district-scoped endpoints. Re-issued on next login if the user moves.
    district_id: str | None = None
    if user.facility_id:
        facility = await db.get(Facility, user.facility_id)
        if facility is not None:
            district_id = facility.district

    principal = Principal(
        subject=user.id,
        role=user.role,  # type: ignore[arg-type]
        facility_id=user.facility_id,
        district_id=district_id,
        name=user.full_name,
    )
    token = issue_token(principal, ttl=timedelta(hours=8))
    logger.info(
        "auth.staff_login",
        user_id=user.id,
        role=user.role,
        district=district_id,
    )
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
    settings = get_settings()
    if settings.is_production:
        # The fixed-OTP stub must never authenticate real citizens. Production
        # must wire NIRA OIDC (or a real OTP provider) in place of this handler.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Citizen OTP login is not available in production; NIRA OIDC is required.",
        )

    await _enforce_login_throttle(body.nin)
    if body.otp != "000000":
        await _record_login_failure(body.nin)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid OTP")

    verification = await nira.verify_nin(body.nin)
    if not verification.found:
        # Even on cache fallback we require a positive lookup
        raise HTTPException(status.HTTP_404_NOT_FOUND, "NIN not found at NIRA")

    await _reset_login_failures(body.nin)

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
    settings = get_settings()
    if settings.is_production:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "seed-demo disabled in APP_ENV=production",
        )

    # Lazy import — seed module loads ~10 KB of demo data; skip if endpoint
    # isn't called.
    from app.db.base import Base
    from app.db.models.facility import Facility
    from app.db.models.patient import Patient
    from app.seed import run as seed_run

    logger.info("auth.seed_demo.start", env=settings.app_env)

    try:
        # Ensure schema is up-to-date — creates any tables introduced by ORM
        # changes that haven't been applied via Alembic yet. Idempotent
        # (CREATE TABLE IF NOT EXISTS). This is the canonical "set up the
        # DB" entrypoint for staging / pilot demos; production deployments
        # should run `alembic upgrade head` instead.
        conn = await db.connection()
        await conn.run_sync(Base.metadata.create_all)

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
        await seed_run._seed_self_audit_reads(db, patients, facility_ids)
        await seed_run._seed_transfers(db, facility_ids, items, admin.id)
        await seed_run._seed_caregivers(db)
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

"""Unit tests for the clinical logic and the NIRA / DHIS2 service clients.

Two halves:

* **Clinical** (sync, plain functions) — the UNEPI schedule reference data and
  `compute_immunisation_status` / `is_duplicate_dose`. These are deliberately
  DB-free: `compute_immunisation_status` takes `_ObsLite` records, so we build
  inputs directly with a fixed `now` for deterministic boundary-age assertions.

* **Service clients** (async) — `NiraClient.verify_nin` and `Dhis2Client`. We
  never touch the network: the `httpx.AsyncClient` instance method (`.get` /
  `.post`) is replaced with an `AsyncMock`, and Redis is swapped for an
  in-memory fake. This keeps the *real* resilience stack (retry + bulkhead +
  circuit breaker, from `app.core.resilience`) in the call path — only the two
  true I/O boundaries are stubbed.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import orjson
import pytest

import app.services.dhis2_client as dhis2_mod
import app.services.nira_client as nira_mod
from app.clinical.unepi_schedule import (
    CODE_TO_ANTIGEN,
    SCHEDULE,
    SNOMED_SYSTEM,
    AntigenStatus,
    ScheduleEntry,
    _age_days,
    _ObsLite,
    compute_immunisation_status,
    is_duplicate_dose,
)
from app.config import get_settings
from app.core import resilience
from app.core.resilience import (
    BreakerState,
    UpstreamUnavailableError,
    get_breaker,
)
from app.services.dhis2_client import DataValue, Dhis2Client
from app.services.nira_client import NinVerification, NiraClient

# ── Shared fixtures / helpers ────────────────────────────────────────────────

# A frozen "today" so every age-window boundary assertion is deterministic.
NOW = datetime(2026, 5, 31, 12, 0, 0, tzinfo=UTC)
TODAY = NOW.date()

# antigen short-label -> SNOMED code (each antigen has one product code)
CODE = {row.antigen: row.snomed_code for row in SCHEDULE}


def _obs(antigen: str, when: datetime) -> _ObsLite:
    return _ObsLite(snomed_code=CODE[antigen], effective_at=when)


def _full_obs(birth_date: date) -> list[_ObsLite]:
    """One observation per dose of every antigen, each at its min-age day.

    The intervals in SCHEDULE are always <= the gap between successive
    min-age days, so administering at min-age satisfies every interval rule.
    """
    obs: list[_ObsLite] = []
    for row in sorted(SCHEDULE, key=lambda r: (r.antigen, r.dose_number)):
        eff = datetime.combine(
            birth_date + timedelta(days=row.min_age_days),
            datetime.min.time(),
            tzinfo=UTC,
        )
        obs.append(_ObsLite(snomed_code=row.snomed_code, effective_at=eff))
    return obs


def _by_antigen(statuses: list[AntigenStatus]) -> dict[str, AntigenStatus]:
    return {s.antigen: s for s in statuses}


# ══════════════════════════════════════════════════════════════════════════
# UNEPI schedule — reference data + helpers
# ══════════════════════════════════════════════════════════════════════════


def test_schedule_covers_expected_antigens_and_series_sizes() -> None:
    """The UNEPI rows must define exactly the six routine antigens with the
    correct number of doses each (BCG x1, OPV x4, DPT x3, PCV x3, MR x2,
    YF x1). This is the contract the worker UI's antigen picker depends on."""
    series_size: dict[str, int] = {}
    for row in SCHEDULE:
        series_size[row.antigen] = max(series_size.get(row.antigen, 0), row.dose_number)

    assert series_size == {"BCG": 1, "OPV": 4, "DPT": 3, "PCV": 3, "MR": 2, "YF": 1}


def test_schedule_dose_numbers_are_contiguous_from_one() -> None:
    """Within each antigen the dose_number values must be 1..N with no gaps —
    `compute_immunisation_status` indexes `series[doses_given]` and would skip
    a dose if the ordinals were sparse."""
    by_antigen: dict[str, list[int]] = {}
    for row in SCHEDULE:
        by_antigen.setdefault(row.antigen, []).append(row.dose_number)
    for antigen, doses in by_antigen.items():
        assert sorted(doses) == list(range(1, len(doses) + 1)), antigen


def test_schedule_entries_are_well_formed() -> None:
    """Every row uses sane day windows: min <= max, dose-1 has interval 0,
    and later doses carry a positive interval."""
    for row in SCHEDULE:
        assert isinstance(row, ScheduleEntry)
        assert 0 <= row.min_age_days <= row.max_age_days
        if row.dose_number == 1:
            assert row.interval_days == 0
        else:
            assert row.interval_days > 0


def test_schedule_uses_single_code_per_antigen() -> None:
    """All doses of one antigen share one SNOMED product code (the reverse
    index `CODE_TO_ANTIGEN` is 1:1 with the antigen set)."""
    codes_per_antigen: dict[str, set[str]] = {}
    for row in SCHEDULE:
        codes_per_antigen.setdefault(row.antigen, set()).add(row.snomed_code)
    for antigen, codes in codes_per_antigen.items():
        assert len(codes) == 1, antigen
    assert len(CODE_TO_ANTIGEN) == 6


def test_code_to_antigen_round_trips() -> None:
    """The reverse index maps each product code back to its antigen label."""
    for row in SCHEDULE:
        assert CODE_TO_ANTIGEN[row.snomed_code] == row.antigen
    # BCG's well-known SNOMED code resolves correctly.
    assert CODE_TO_ANTIGEN["42284007"] == "BCG"


def test_known_antigen_windows() -> None:
    """Spot-check the headline schedule values clinicians rely on:
    BCG at birth, MR dose 1 at 9 months (270d), YF single dose at 9 months."""
    bcg = next(r for r in SCHEDULE if r.antigen == "BCG")
    assert bcg.min_age_days == 0 and bcg.dose_number == 1

    mr1 = next(r for r in SCHEDULE if r.antigen == "MR" and r.dose_number == 1)
    assert mr1.min_age_days == 270

    mr2 = next(r for r in SCHEDULE if r.antigen == "MR" and r.dose_number == 2)
    assert mr2.interval_days == 180  # 6 months after MR1

    yf = next(r for r in SCHEDULE if r.antigen == "YF")
    assert yf.dose_number == 1 and yf.min_age_days == 270


def test_snomed_system_constant() -> None:
    assert SNOMED_SYSTEM == "http://snomed.info/sct"


# ── _age_days boundary helper ────────────────────────────────────────────────


def test_age_days_on_birthday_is_zero() -> None:
    bd = date(2026, 5, 31)
    assert _age_days(bd, on=date(2026, 5, 31)) == 0


def test_age_days_counts_elapsed_days() -> None:
    bd = date(2026, 5, 1)
    assert _age_days(bd, on=date(2026, 5, 31)) == 30


def test_age_days_one_year() -> None:
    bd = date(2025, 5, 31)
    assert _age_days(bd, on=date(2026, 5, 31)) == 365


def test_age_days_negative_before_birth() -> None:
    """A future birth_date (e.g. an antenatal record) yields a negative age —
    the status computer leans on `age_today > 0` to avoid flagging the unborn
    as overdue."""
    bd = date(2026, 6, 30)
    assert _age_days(bd, on=date(2026, 5, 31)) < 0


# ══════════════════════════════════════════════════════════════════════════
# compute_immunisation_status — clinical state machine
# ══════════════════════════════════════════════════════════════════════════


def test_status_output_shape_one_row_per_antigen() -> None:
    """Output is one AntigenStatus per antigen (six rows) carrying the full
    DTO shape, regardless of how many observations exist."""
    statuses = compute_immunisation_status(TODAY, [], now=NOW)
    assert len(statuses) == 6
    assert {s.antigen for s in statuses} == {"BCG", "OPV", "DPT", "PCV", "MR", "YF"}
    for s in statuses:
        assert isinstance(s, AntigenStatus)
        assert s.series_size >= 1
        assert 0 <= s.doses_given <= s.series_size
        assert s.status in {"complete", "due", "due-soon", "overdue", "not-yet"}


def test_status_newborn_no_immunisations_all_due_or_not_yet() -> None:
    """(a) A patient with NO immunisations, born today.

    Birth-dose antigens (BCG, OPV) are immediately *due*; the rest are
    *not-yet* (their min-age window opens weeks/months later). Nothing is
    complete and nothing is overdue on day zero."""
    statuses = compute_immunisation_status(TODAY, [], now=NOW)
    by = _by_antigen(statuses)

    assert by["BCG"].status == "due"
    assert by["OPV"].status == "due"
    assert by["BCG"].next_due_date == TODAY  # eligible from birth

    for antigen in ("DPT", "PCV", "MR", "YF"):
        assert by[antigen].status == "not-yet", antigen

    for s in statuses:
        assert s.doses_given == 0
        assert s.overdue_days == 0
        assert s.last_dose_at is None
        assert s.next_dose_number == 1  # series untouched -> first dose is next
        assert s.status != "complete"


def test_status_fully_immunised_all_complete() -> None:
    """(b) A fully immunised patient — every dose of every antigen recorded.

    All six antigens report `complete`, with doses_given == series_size, no
    next dose, and the most recent administration surfaced as last_dose_at."""
    birth_date = date(2023, 1, 1)  # ~3y old at NOW, every window has opened
    statuses = compute_immunisation_status(birth_date, _full_obs(birth_date), now=NOW)

    assert all(s.status == "complete" for s in statuses)
    for s in statuses:
        assert s.doses_given == s.series_size
        assert s.next_dose_number is None
        assert s.next_due_date is None
        assert s.overdue_days == 0
        assert s.last_dose_at is not None


def test_status_partial_series_shapes_and_values() -> None:
    """(c) A partially immunised ~6-month-old.

    BCG (single dose) given -> complete. OPV and DPT have dose 1 recorded ->
    in-progress with the correct next dose number and a positive overdue count
    (the infant is late for the 10-week visit). PCV/MR/YF untouched."""
    birth_date = date(2025, 11, 30)  # ~182 days at NOW
    obs = [
        _obs("BCG", datetime(2025, 12, 1, tzinfo=UTC)),
        _obs("OPV", datetime(2025, 12, 1, tzinfo=UTC)),
        _obs("DPT", datetime(2026, 1, 15, tzinfo=UTC)),  # ~6 weeks
    ]
    by = _by_antigen(compute_immunisation_status(birth_date, obs, now=NOW))

    # BCG single-dose series is finished.
    assert by["BCG"].status == "complete"
    assert by["BCG"].doses_given == 1
    assert by["BCG"].series_size == 1
    assert by["BCG"].next_dose_number is None
    assert by["BCG"].last_dose_at == datetime(2025, 12, 1, tzinfo=UTC)

    # OPV: dose 1 done, dose 2 is next and overdue (past its due date).
    assert by["OPV"].doses_given == 1
    assert by["OPV"].series_size == 4
    assert by["OPV"].next_dose_number == 2
    assert by["OPV"].status == "due"
    assert by["OPV"].overdue_days > 0

    # DPT: dose 1 done, dose 2 next.
    assert by["DPT"].doses_given == 1
    assert by["DPT"].series_size == 3
    assert by["DPT"].next_dose_number == 2

    # Untouched antigens have no doses and are not complete.
    for antigen in ("PCV", "MR", "YF"):
        assert by[antigen].doses_given == 0
        assert by[antigen].status != "complete"


def test_status_old_child_no_immunisations_is_overdue() -> None:
    """A 3-year-old with nothing recorded: antigens whose max-age window has
    passed (BCG/OPV/DPT/PCV) are *overdue* with a positive overdue_days count;
    MR/YF still inside their wide windows remain *due* rather than overdue."""
    birth_date = date(2023, 1, 1)
    by = _by_antigen(compute_immunisation_status(birth_date, [], now=NOW))

    for antigen in ("BCG", "OPV", "DPT", "PCV"):
        assert by[antigen].status == "overdue", antigen
        assert by[antigen].overdue_days > 0, antigen

    # MR (max 1825d) and YF (max 10950d) windows are still open at age ~1245d.
    assert by["MR"].status == "due"
    assert by["YF"].status == "due"


def test_status_sort_order_overdue_first_complete_last() -> None:
    """Rows are ordered overdue -> due -> due-soon -> not-yet -> complete so
    the worker UI surfaces the most urgent antigens at the top."""
    birth_date = date(2025, 11, 30)
    obs = [_obs("BCG", datetime(2025, 12, 1, tzinfo=UTC))]  # BCG complete
    statuses = compute_immunisation_status(birth_date, obs, now=NOW)

    rank = {"overdue": 0, "due": 1, "due-soon": 2, "not-yet": 3, "complete": 4}
    ranks = [rank[s.status] for s in statuses]
    assert ranks == sorted(ranks)
    # The complete BCG row must sort to the end.
    assert statuses[-1].antigen == "BCG"
    assert statuses[-1].status == "complete"


def test_status_ignores_unknown_observation_codes() -> None:
    """Observations whose code isn't in the schedule (e.g. a weight reading)
    are dropped — they neither create rows nor count as doses."""
    obs = [_ObsLite(snomed_code="27113001", effective_at=NOW)]  # body weight
    statuses = compute_immunisation_status(TODAY, obs, now=NOW)
    assert len(statuses) == 6
    assert all(s.doses_given == 0 for s in statuses)


def test_status_extra_doses_capped_at_series_size() -> None:
    """More recorded doses than the series defines never inflates doses_given
    beyond series_size (defends against duplicate data entry)."""
    birth_date = date(2024, 1, 1)
    # BCG is a single-dose series; record it three times.
    obs = [
        _obs("BCG", datetime(2024, 1, 2, tzinfo=UTC)),
        _obs("BCG", datetime(2024, 2, 2, tzinfo=UTC)),
        _obs("BCG", datetime(2024, 3, 2, tzinfo=UTC)),
    ]
    by = _by_antigen(compute_immunisation_status(birth_date, obs, now=NOW))
    assert by["BCG"].doses_given == 1
    assert by["BCG"].status == "complete"


def test_status_due_soon_within_30_day_window() -> None:
    """An antigen becomes `due-soon` when today is within 30 days *before* the
    next-due date. Born 252 days ago, MR1 (min-age 270d) is due in 18 days."""
    birth_date = TODAY - timedelta(days=252)
    by = _by_antigen(compute_immunisation_status(birth_date, [], now=NOW))
    assert by["MR"].status == "due-soon"
    assert by["MR"].overdue_days == 0
    assert by["MR"].next_due_date == birth_date + timedelta(days=270)


# ══════════════════════════════════════════════════════════════════════════
# is_duplicate_dose — duplicate-prevention guard
# ══════════════════════════════════════════════════════════════════════════


def test_duplicate_when_series_already_complete() -> None:
    """Re-administering a single-dose antigen that's already complete is a
    duplicate, with an explanatory reason mentioning the antigen."""
    birth_date = date(2025, 11, 30)
    obs = [_obs("BCG", datetime(2025, 12, 1, tzinfo=UTC))]
    dup, reason = is_duplicate_dose(birth_date, obs, CODE["BCG"], now=NOW)
    assert dup is True
    assert reason is not None and "BCG" in reason


def test_duplicate_when_next_dose_not_yet_due() -> None:
    """Giving the next dose before its minimum interval has elapsed is a
    duplicate. DPT1 given today => DPT2 is 28 days early."""
    birth_date = TODAY - timedelta(days=50)  # old enough for DPT1
    obs = [_obs("DPT", NOW)]
    dup, reason = is_duplicate_dose(birth_date, obs, CODE["DPT"], now=NOW)
    assert dup is True
    assert reason is not None and "DPT" in reason


def test_not_duplicate_when_dose_is_due() -> None:
    """The next dose, once genuinely due, is not a duplicate. DPT1 given well
    over 28 days ago => DPT2 is appropriate now."""
    birth_date = date(2025, 11, 30)
    obs = [_obs("DPT", datetime(2026, 1, 15, tzinfo=UTC))]  # >28d before NOW
    dup, reason = is_duplicate_dose(birth_date, obs, CODE["DPT"], now=NOW)
    assert dup is False
    assert reason is None


def test_not_duplicate_for_unknown_antigen_code() -> None:
    """An unscheduled code has no series to enforce against, so it's never a
    duplicate."""
    dup, reason = is_duplicate_dose(TODAY, [], "99999999", now=NOW)
    assert dup is False
    assert reason is None


def test_not_duplicate_first_dose_of_empty_series() -> None:
    """The very first dose of an antigen the patient has never had is allowed
    once they're eligible (BCG from birth)."""
    dup, reason = is_duplicate_dose(TODAY, [], CODE["BCG"], now=NOW)
    assert dup is False
    assert reason is None


# ══════════════════════════════════════════════════════════════════════════
# Service clients — NIRA + DHIS2 (async; network + Redis fully stubbed)
# ══════════════════════════════════════════════════════════════════════════

# The async service-client tests below are collected by pytest-asyncio's
# `asyncio_mode = "auto"` (configured in pyproject.toml) — no per-test marker
# needed. We avoid a module-level `pytest.mark.asyncio` because it would also
# attach (spuriously) to the sync clinical tests in the first half of the file.


# A request object so httpx.Response.raise_for_status() works on synthetic
# responses (httpx refuses to evaluate status without an attached request).
_REQUEST = httpx.Request("GET", "http://stub.invalid")


def _response(status_code: int, *, json_body: dict | None = None) -> httpx.Response:
    return httpx.Response(status_code, request=_REQUEST, json=json_body or {})


class _FakeRedis:
    """Minimal in-memory async Redis covering exactly the ops the clients use:
    string get/set (NIRA cache) and list rpush/lpush/lpop (DHIS2 outbox)."""

    def __init__(self) -> None:
        self.kv: dict[str, str] = {}
        self.lists: dict[str, list[str]] = {}

    async def set(self, key: str, value, ex: int | None = None) -> None:
        self.kv[key] = value

    async def get(self, key: str):
        return self.kv.get(key)

    async def rpush(self, key: str, *values: str) -> None:
        self.lists.setdefault(key, []).extend(values)

    async def lpush(self, key: str, *values: str) -> None:
        bucket = self.lists.setdefault(key, [])
        for v in reversed(values):
            bucket.insert(0, v)

    async def lpop(self, key: str):
        bucket = self.lists.get(key) or []
        return bucket.pop(0) if bucket else None


@pytest.fixture()
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
    """Swap the module-level `get_redis` in both clients for an in-memory fake,
    so the cache (NIRA) and outbox (DHIS2) are real data structures we can
    inspect — no Redis server, no network."""
    redis = _FakeRedis()
    monkeypatch.setattr(nira_mod, "get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(dhis2_mod, "get_redis", AsyncMock(return_value=redis))
    return redis


@pytest.fixture(autouse=True)
def fast_resilience(monkeypatch: pytest.MonkeyPatch):
    """Give each test a clean circuit breaker and zero retry back-off.

    Breakers live in a process-global registry (`resilience._breakers`) and the
    `@resilient` wrapper captures its breaker instance *by reference* at import
    time. So we must NOT swap the instances out (that would desync the client's
    closure from the registry) — instead we reset the *state* of each existing
    breaker in place (CLOSED, zero failures, default threshold) before and
    after every test, so a breaker tripped by one test cannot leak into the
    next. Patching `random.uniform -> 0` keeps the real retry counting logic
    intact while removing wall-clock sleeps, so failure-path tests stay fast."""
    default_threshold = get_settings().circuit_breaker_failure_threshold

    def _reset() -> None:
        for breaker in resilience._breakers.values():
            breaker._state = BreakerState.CLOSED
            breaker._failures = 0
            breaker._opened_at = None
            breaker.failure_threshold = default_threshold

    _reset()
    monkeypatch.setattr(resilience.random, "uniform", lambda _a, _b: 0.0)
    yield
    _reset()


def _nira_client() -> NiraClient:
    return NiraClient(get_settings())


def _dhis2_client() -> Dhis2Client:
    return Dhis2Client(get_settings())


# ── NIRA.verify_nin ──────────────────────────────────────────────────────────


async def test_nira_verify_found_returns_full_name_and_caches(fake_redis):
    """A known NIN returns found=True with the upstream-provided full_name and
    demographics, served live (via_fallback=False) and written to the cache."""
    client = _nira_client()
    client._client.get = AsyncMock(  # type: ignore[method-assign]
        return_value=_response(
            200,
            json_body={
                "full_name": "Jane Doe",
                "gender": "female",
                "date_of_birth": "1990-01-01",
                "district": "Kampala",
            },
        )
    )

    result = await client.verify_nin("CM85051712345X")

    assert isinstance(result, NinVerification)
    assert result.found is True
    assert result.full_name == "Jane Doe"
    assert result.gender == "female"
    assert result.district == "Kampala"
    assert result.via_fallback is False
    # Positive, live results are cached for the 24h fallback window.
    assert "nira:nin:CM85051712345X" in fake_redis.kv

    await client.aclose()


async def test_nira_verify_not_found_is_not_cached(fake_redis):
    """A 404 from upstream yields found=False and is NOT cached (only positive
    lookups are persisted for fallback)."""
    client = _nira_client()
    client._client.get = AsyncMock(return_value=_response(404))  # type: ignore[method-assign]

    result = await client.verify_nin("CM00000000000X")

    assert result.found is False
    assert result.full_name is None
    assert result.via_fallback is False
    assert "nira:nin:CM00000000000X" not in fake_redis.kv

    await client.aclose()


async def test_nira_falls_back_to_cache_when_upstream_down(fake_redis):
    """When the live call fails but a prior positive result is cached,
    verify_nin degrades gracefully: it returns the cached identity with
    via_fallback=True instead of raising."""
    nin = "CM85051712345X"
    client = _nira_client()

    # 1) Prime the cache with a successful live verification.
    client._client.get = AsyncMock(  # type: ignore[method-assign]
        return_value=_response(200, json_body={"full_name": "Jane Doe", "district": "Gulu"})
    )
    await client.verify_nin(nin)
    assert f"nira:nin:{nin}" in fake_redis.kv

    # 2) Upstream now hard-down — the cached value must be served.
    client._client.get = AsyncMock(side_effect=httpx.ConnectError("nira unreachable"))  # type: ignore[method-assign]
    result = await client.verify_nin(nin)

    assert result.found is True
    assert result.full_name == "Jane Doe"
    assert result.district == "Gulu"
    assert result.via_fallback is True  # served from cache, not live

    await client.aclose()


async def test_nira_hard_fails_when_down_and_no_cache(fake_redis):
    """With the upstream down and nothing cached, there is no safe degraded
    answer — verify_nin propagates the error rather than fabricating one."""
    client = _nira_client()
    client._client.get = AsyncMock(side_effect=httpx.ConnectError("nira unreachable"))  # type: ignore[method-assign]

    with pytest.raises(Exception):  # noqa: B017 - the raw transport error bubbles up
        await client.verify_nin("CM99999999999X")

    await client.aclose()


async def test_nira_breaker_opens_then_fast_fails(fake_redis):
    """Once enough live calls fail, the circuit breaker trips OPEN and further
    calls fail fast with UpstreamUnavailableError (no cache here, so the error
    surfaces instead of a fallback). Exercises the real breaker in the client
    path."""
    client = _nira_client()
    client._client.get = AsyncMock(side_effect=httpx.ConnectError("down"))  # type: ignore[method-assign]

    # Tighten the threshold on the breaker the decorator already registered so
    # a single failing call opens it (default threshold is 5).
    breaker = get_breaker("nira")
    breaker.failure_threshold = 1

    # First call: live fails -> breaker records a failure and opens. No cache,
    # so the transport error propagates.
    with pytest.raises(Exception):  # noqa: B017
        await client.verify_nin("CMAAA")
    assert breaker.state is BreakerState.OPEN

    # Second call: breaker is OPEN -> fast-fail without touching the upstream.
    with pytest.raises(UpstreamUnavailableError):
        await client.verify_nin("CMBBB")

    await client.aclose()


# ── DHIS2 post_tallies + drain ───────────────────────────────────────────────


async def test_dhis2_post_tallies_success(fake_redis):
    """A healthy DHIS2 accepts the batch: every value is delivered, none
    queued, and the outbox stays empty."""
    client = _dhis2_client()
    values = [
        DataValue(data_element="DE1", period="2026Q1", org_unit="OU1", value=12),
        DataValue(data_element="DE2", period="2026Q1", org_unit="OU1", value=7),
    ]
    client._client.post = AsyncMock(return_value=_response(200, json_body={"status": "OK"}))  # type: ignore[method-assign]

    result = await client.post_tallies(values)

    assert result == {"queued": 0, "delivered": 2}
    assert fake_redis.lists.get("dhis2:pending", []) == []
    client._client.post.assert_awaited_once()

    await client.aclose()


async def test_dhis2_post_tallies_queues_on_failure(fake_redis):
    """When DHIS2 is unreachable, post_tallies never raises: it reports the
    values as queued (delivered=0) and pushes them onto the Redis outbox."""
    client = _dhis2_client()
    values = [
        DataValue(data_element="DE1", period="2026Q1", org_unit="OU1", value=12),
        DataValue(data_element="DE2", period="2026Q1", org_unit="OU1", value=7),
    ]
    client._client.post = AsyncMock(side_effect=httpx.ConnectError("dhis2 down"))  # type: ignore[method-assign]

    result = await client.post_tallies(values)

    assert result == {"queued": 2, "delivered": 0}
    pending = fake_redis.lists.get("dhis2:pending", [])
    assert len(pending) == 2
    # Queued payloads are the JSON-serialised DataValues, replayable later.
    first = orjson.loads(pending[0])
    assert first == {
        "data_element": "DE1",
        "period": "2026Q1",
        "org_unit": "OU1",
        "value": 12,
    }

    await client.aclose()


async def test_dhis2_drain_replays_queued_values(fake_redis):
    """After an outage, drain_queue replays everything in the outbox once the
    upstream recovers, emptying the queue."""
    client = _dhis2_client()
    values = [
        DataValue(data_element="DE1", period="2026Q1", org_unit="OU1", value=3),
        DataValue(data_element="DE2", period="2026Q1", org_unit="OU1", value=5),
        DataValue(data_element="DE3", period="2026Q1", org_unit="OU1", value=8),
    ]

    # Outage: values land in the outbox.
    client._client.post = AsyncMock(side_effect=httpx.ConnectError("dhis2 down"))  # type: ignore[method-assign]
    await client.post_tallies(values)
    assert len(fake_redis.lists["dhis2:pending"]) == 3

    # Recovery: drain replays each queued value.
    client._client.post = AsyncMock(return_value=_response(200, json_body={"status": "OK"}))  # type: ignore[method-assign]
    drained = await client.drain_queue()

    assert drained == {"delivered": 3}
    assert fake_redis.lists.get("dhis2:pending", []) == []
    assert client._client.post.await_count == 3  # one replay per value

    await client.aclose()


async def test_dhis2_drain_stops_and_requeues_if_still_down(fake_redis):
    """If the upstream is still down during a drain, the un-deliverable value
    is pushed back onto the queue and the drain stops (delivered=0) — no data
    loss, retried on the next pass."""
    client = _dhis2_client()
    value = DataValue(data_element="DE9", period="2026Q1", org_unit="OU1", value=1)

    client._client.post = AsyncMock(side_effect=httpx.ConnectError("dhis2 down"))  # type: ignore[method-assign]
    await client.post_tallies([value])
    assert len(fake_redis.lists["dhis2:pending"]) == 1

    # Still down at drain time.
    drained = await client.drain_queue()

    assert drained == {"delivered": 0}
    assert len(fake_redis.lists["dhis2:pending"]) == 1  # value preserved

    await client.aclose()


async def test_dhis2_drain_empty_queue_is_noop(fake_redis):
    """Draining an empty outbox delivers nothing and does not call upstream."""
    client = _dhis2_client()
    client._client.post = AsyncMock(return_value=_response(200, json_body={"status": "OK"}))  # type: ignore[method-assign]

    drained = await client.drain_queue()

    assert drained == {"delivered": 0}
    client._client.post.assert_not_awaited()

    await client.aclose()

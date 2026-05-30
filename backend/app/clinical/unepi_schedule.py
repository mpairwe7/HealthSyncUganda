"""UNEPI childhood immunisation schedule — Uganda Ministry of Health.

Source: Uganda National Expanded Programme on Immunisation, 2024 routine
schedule. Each row binds a SNOMED-CT antigen code (mirrors the codes our
worker UI emits when recording an Observation) to:

  - dose_number    : 1-based ordinal within the series
  - min_age_days   : earliest age the dose may be administered
  - max_age_days   : latest age the dose remains routinely indicated
  - interval_days  : minimum days since the previous dose in the series
                     (0 for the first dose)

This is a static Python module rather than a DB table because:
  1. It is reference data, not user data — versioned with the application.
  2. It changes when MoH revises the schedule — a code commit captures
     the revision intent better than a runtime row-update.
  3. No write path is needed; no migration is required.

The `compute_immunisation_status()` helper joins a patient's age (from
birth_date) + their existing vaccine Observations against this schedule
and returns a per-antigen view of what's done, what's due, and what's
overdue. That helper is the data behind `GET /api/v1/patients/{id}/
immunisation-status` and powers the worker UI's duplicate-prevention
check.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal

# Code system that every entry below uses — matches our seed VACCINE_CODES
# and the SNOMED Observations the worker UI emits.
SNOMED_SYSTEM = "http://snomed.info/sct"


@dataclass(frozen=True)
class ScheduleEntry:
    antigen: str               # short label e.g. "BCG", "DPT", "MR"
    snomed_code: str           # SNOMED CT product code
    display: str               # human-readable
    dose_number: int           # 1-based within series
    min_age_days: int          # earliest age
    max_age_days: int          # latest age routinely indicated
    interval_days: int         # min days since previous dose (0 for dose 1)


# Schedule rows. Order them by (antigen, dose_number) for readability.
# Numbers are days; reference values:
#   1 month  ≈  30 days
#   1 year   = 365 days
#   5 years  = 1825 days
SCHEDULE: list[ScheduleEntry] = [
    # BCG — single dose at birth
    ScheduleEntry("BCG", "42284007", "BCG vaccine product",
                  dose_number=1, min_age_days=0, max_age_days=365, interval_days=0),

    # OPV (Oral Polio Vaccine) — birth dose + 3 doses at 6/10/14 weeks
    ScheduleEntry("OPV", "836382009", "Oral polio vaccine product",
                  dose_number=1, min_age_days=0,  max_age_days=14,  interval_days=0),
    ScheduleEntry("OPV", "836382009", "Oral polio vaccine product",
                  dose_number=2, min_age_days=42, max_age_days=730, interval_days=28),
    ScheduleEntry("OPV", "836382009", "Oral polio vaccine product",
                  dose_number=3, min_age_days=70, max_age_days=730, interval_days=28),
    ScheduleEntry("OPV", "836382009", "Oral polio vaccine product",
                  dose_number=4, min_age_days=98, max_age_days=730, interval_days=28),

    # DPT-HepB-Hib (pentavalent) — 3 doses at 6/10/14 weeks
    ScheduleEntry("DPT", "428601000124108", "DPT-HepB-Hib (pentavalent) vaccine product",
                  dose_number=1, min_age_days=42,  max_age_days=730, interval_days=0),
    ScheduleEntry("DPT", "428601000124108", "DPT-HepB-Hib (pentavalent) vaccine product",
                  dose_number=2, min_age_days=70,  max_age_days=730, interval_days=28),
    ScheduleEntry("DPT", "428601000124108", "DPT-HepB-Hib (pentavalent) vaccine product",
                  dose_number=3, min_age_days=98,  max_age_days=730, interval_days=28),

    # PCV (Pneumococcal Conjugate) — 3 doses at 6/10/14 weeks
    ScheduleEntry("PCV", "836389000", "Pneumococcal conjugate vaccine product",
                  dose_number=1, min_age_days=42,  max_age_days=730, interval_days=0),
    ScheduleEntry("PCV", "836389000", "Pneumococcal conjugate vaccine product",
                  dose_number=2, min_age_days=70,  max_age_days=730, interval_days=28),
    ScheduleEntry("PCV", "836389000", "Pneumococcal conjugate vaccine product",
                  dose_number=3, min_age_days=98,  max_age_days=730, interval_days=28),

    # Measles-Rubella — 2 doses at 9 months + 18 months
    ScheduleEntry("MR", "836383004", "Measles-Rubella vaccine product",
                  dose_number=1, min_age_days=270, max_age_days=1825, interval_days=0),
    ScheduleEntry("MR", "836383004", "Measles-Rubella vaccine product",
                  dose_number=2, min_age_days=540, max_age_days=1825, interval_days=180),

    # Yellow Fever — single dose at 9 months
    ScheduleEntry("YF", "836385006", "Yellow fever vaccine product",
                  dose_number=1, min_age_days=270, max_age_days=10950, interval_days=0),
]


# Reverse index: SNOMED code → antigen short-label
CODE_TO_ANTIGEN: dict[str, str] = {row.snomed_code: row.antigen for row in SCHEDULE}


# ── Per-patient status computation ──────────────────────────────────────────


StatusLevel = Literal["complete", "due", "due-soon", "overdue", "not-yet"]


@dataclass
class AntigenStatus:
    antigen: str
    display: str
    snomed_code: str
    series_size: int
    doses_given: int
    next_dose_number: int | None
    next_due_date: date | None       # absolute date the next dose may be given
    overdue_days: int                # 0 if not overdue; positive if past the window
    last_dose_at: datetime | None    # most recent administration
    status: StatusLevel              # "complete" | "due" | "due-soon" | "overdue" | "not-yet"


@dataclass
class _ObsLite:
    """Subset of Observation the status computer needs.

    Decoupled from the ORM so the helper is unit-testable without a DB.
    Callers pass these in instead of full SQLAlchemy rows.
    """
    snomed_code: str
    effective_at: datetime


def _today(now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).date()


def _age_days(birth_date: date, on: date | None = None) -> int:
    return ((on or _today()) - birth_date).days


def compute_immunisation_status(
    birth_date: date,
    observations: list[_ObsLite],
    *,
    now: datetime | None = None,
) -> list[AntigenStatus]:
    """For one patient, return an antigen-by-antigen status list.

    `observations` should contain only Observation rows whose
    `code_system == SNOMED_SYSTEM` AND whose code matches a row in
    SCHEDULE — i.e. only the patient's vaccine records.
    """
    today = _today(now)
    age_today = _age_days(birth_date, today)

    # Group schedule rows by antigen
    by_antigen: dict[str, list[ScheduleEntry]] = {}
    for row in SCHEDULE:
        by_antigen.setdefault(row.antigen, []).append(row)

    # Map antigen → sorted-by-time list of observations for that antigen
    obs_by_antigen: dict[str, list[_ObsLite]] = {}
    for ob in observations:
        antigen = CODE_TO_ANTIGEN.get(ob.snomed_code)
        if antigen is None:
            continue
        obs_by_antigen.setdefault(antigen, []).append(ob)
    for v in obs_by_antigen.values():
        v.sort(key=lambda o: o.effective_at)

    out: list[AntigenStatus] = []
    for antigen, series in by_antigen.items():
        series.sort(key=lambda r: r.dose_number)
        given = obs_by_antigen.get(antigen, [])
        doses_given = min(len(given), series[-1].dose_number)
        display = series[0].display
        snomed_code = series[0].snomed_code
        last_dose_at = given[-1].effective_at if given else None

        if doses_given >= series[-1].dose_number:
            out.append(AntigenStatus(
                antigen=antigen,
                display=display,
                snomed_code=snomed_code,
                series_size=series[-1].dose_number,
                doses_given=doses_given,
                next_dose_number=None,
                next_due_date=None,
                overdue_days=0,
                last_dose_at=last_dose_at,
                status="complete",
            ))
            continue

        # Compute next-due
        next_dose = series[doses_given]
        # Date the patient becomes eligible based on age (min_age_days from birth)
        earliest_by_age = birth_date + _days(next_dose.min_age_days)
        # Date allowed by interval-from-previous (if dose 2+)
        if doses_given > 0 and given:
            earliest_by_interval = given[-1].effective_at.date() + _days(next_dose.interval_days)
        else:
            earliest_by_interval = birth_date
        next_due = max(earliest_by_age, earliest_by_interval)
        latest_by_age = birth_date + _days(next_dose.max_age_days)

        # Status classification:
        #   not-yet : today < next_due
        #   due     : next_due ≤ today ≤ next_due + 30
        #   due-soon: next_due - 30 <= today < next_due (already eligible window)
        #   overdue : today > latest_by_age (missed the route window)
        if today > latest_by_age and age_today > 0:
            status: StatusLevel = "overdue"
            overdue = (today - latest_by_age).days
        elif next_due <= today:
            status = "due"
            overdue = (today - next_due).days
        elif (next_due - today).days <= 30:
            status = "due-soon"
            overdue = 0
        else:
            status = "not-yet"
            overdue = 0

        out.append(AntigenStatus(
            antigen=antigen,
            display=display,
            snomed_code=snomed_code,
            series_size=series[-1].dose_number,
            doses_given=doses_given,
            next_dose_number=next_dose.dose_number,
            next_due_date=next_due,
            overdue_days=overdue,
            last_dose_at=last_dose_at,
            status=status,
        ))

    # Stable order: overdue first, then due, then due-soon, then not-yet, then complete
    order = {"overdue": 0, "due": 1, "due-soon": 2, "not-yet": 3, "complete": 4}
    out.sort(key=lambda s: (order[s.status], s.antigen))
    return out


def _days(n: int):
    """timedelta shim — avoids re-importing inside the loop."""
    from datetime import timedelta
    return timedelta(days=n)


def is_duplicate_dose(
    birth_date: date,
    observations: list[_ObsLite],
    candidate_snomed_code: str,
    *,
    now: datetime | None = None,
) -> tuple[bool, str | None]:
    """Return (would_be_duplicate, reason).

    A "duplicate" is one of:
      - Series for that antigen is already complete.
      - The proposed dose is within the minimum interval of the previous dose
        (e.g. DPT2 administered fewer than 28 days after DPT1).
    Returns (False, None) when the candidate dose is clinically appropriate.
    """
    antigen = CODE_TO_ANTIGEN.get(candidate_snomed_code)
    if antigen is None:
        # Unknown antigen — no schedule to enforce against; not a duplicate.
        return (False, None)

    status_list = compute_immunisation_status(birth_date, observations, now=now)
    s = next((x for x in status_list if x.antigen == antigen), None)
    if s is None:
        return (False, None)

    if s.status == "complete":
        return (True, f"{antigen} series is already complete ({s.doses_given}/{s.series_size}).")

    if s.next_due_date and s.next_due_date > _today(now):
        # Trying to give the next dose before the minimum interval has elapsed
        days_early = (s.next_due_date - _today(now)).days
        return (True, f"{antigen}{s.next_dose_number} not due for {days_early} more days.")

    return (False, None)

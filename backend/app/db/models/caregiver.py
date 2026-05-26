"""Caregiver↔Child link — supports the real-world case of a parent
bringing multiple children to a facility in one visit.

A `CaregiverLink` row says "patient X is a caregiver for patient Y" with
a free-text relationship label (mother / father / guardian / aunt …).
The directionality matters: queries like "show me all my children" need
a caregiver_id → child_id lookup, while audit queries like "who is
recorded as this child's caregiver?" go the other way. Both directions
are indexed.

There is intentionally NO constraint that the caregiver be an adult or
that the child be a minor — Uganda's clinical reality includes adult
siblings of unwell adults, married minors who are parents, and elder
care. The relationship column is the source of truth for the role.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class CaregiverLink(Base, IdMixin, TimestampMixin):
    __tablename__ = "caregiver_links"

    caregiver_id: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("patients.id", ondelete="CASCADE"),
        index=True,
    )
    child_id: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("patients.id", ondelete="CASCADE"),
        index=True,
    )
    relationship: Mapped[str] = mapped_column(String(40))

    __table_args__ = (
        # The same caregiver→child pair cannot be linked twice (idempotent
        # inserts; the relationship label can be updated via PATCH if it
        # changes from e.g. "guardian" to "mother" after re-verification).
        UniqueConstraint("caregiver_id", "child_id", name="uq_caregiver_links_pair"),
        # Look-up paths: caregiver's children (most common, citizen-side),
        # child's caregivers (worker side).
        Index("ix_caregiver_links_caregiver_child", "caregiver_id", "child_id"),
    )

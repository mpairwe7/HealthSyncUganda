"""User model — covers staff (healthcare workers, pharmacists, admins).

Citizens are *not* users: they authenticate via NIN+OTP and identify by their
Patient record. Keeping these models separate keeps clinical and account data
on distinct lifecycles.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin


class User(Base, IdMixin, TimestampMixin):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(40), index=True)
    facility_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("facilities.id", ondelete="SET NULL"), index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    facility = relationship("Facility", back_populates="users", lazy="selectin")

    __table_args__ = (UniqueConstraint("username", name="uq_users_username"),)

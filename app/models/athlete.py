from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.result import Result


class Athlete(Base):
    __tablename__ = "athletes"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(200), index=True)
    birth_year: Mapped[int | None]
    gender: Mapped[str | None] = mapped_column(String(1))   # "M" | "F"
    country_code: Mapped[str | None] = mapped_column(String(3))
    swim_club_name: Mapped[str | None] = mapped_column(String(200))
    swim_club_abbr: Mapped[str | None] = mapped_column(String(20))

    world_aquatics_id: Mapped[str | None] = mapped_column(String(50), unique=True)
    swimrankings_id: Mapped[str | None] = mapped_column(String(50), unique=True)
    swimcloud_id: Mapped[str | None] = mapped_column(String(50), unique=True)
    usas_id: Mapped[str | None] = mapped_column(String(50), unique=True)

    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())

    results: Mapped[list["Result"]] = relationship(back_populates="athlete")

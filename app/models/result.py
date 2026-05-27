from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.athlete import Athlete
    from app.models.meet import Meet


class Result(Base):
    __tablename__ = "results"

    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), index=True)
    meet_id: Mapped[int] = mapped_column(ForeignKey("meets.id"), index=True)

    event_distance: Mapped[int]                          # 50, 100, 200, 400, 800, 1500
    event_stroke: Mapped[str] = mapped_column(String(20))   # "freestyle" | "backstroke" | "breaststroke" | "butterfly" | "im"
    event_gender: Mapped[str] = mapped_column(String(1))    # "M" | "F"
    course: Mapped[str] = mapped_column(String(3))          # "LCM" | "SCM" | "SCY"

    time_seconds: Mapped[float] = mapped_column(index=True)
    time_display: Mapped[str] = mapped_column(String(20))   # "1:45.23"
    swim_date: Mapped[date | None]

    source: Mapped[str] = mapped_column(String(30))
    source_result_id: Mapped[str | None] = mapped_column(String(100))

    athlete: Mapped["Athlete"] = relationship(back_populates="results")
    meet: Mapped["Meet"] = relationship(back_populates="results")
    splits: Mapped[list["Split"]] = relationship(
        back_populates="result", cascade="all, delete-orphan", order_by="Split.split_number"
    )


class Split(Base):
    __tablename__ = "splits"

    id: Mapped[int] = mapped_column(primary_key=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("results.id"), index=True)
    split_number: Mapped[int]
    distance_meters: Mapped[int]
    cumulative_seconds: Mapped[float | None]
    lap_seconds: Mapped[float | None]

    result: Mapped["Result"] = relationship(back_populates="splits")

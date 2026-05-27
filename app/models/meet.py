from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.result import Result


class Meet(Base):
    __tablename__ = "meets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(100))
    country_code: Mapped[str | None] = mapped_column(String(3))
    start_date: Mapped[date | None]
    end_date: Mapped[date | None]
    course: Mapped[str] = mapped_column(String(3))    # "LCM" | "SCM" | "SCY"
    level: Mapped[str] = mapped_column(String(20))    # "international" | "usas" | "ncaa"
    source: Mapped[str] = mapped_column(String(30))
    source_meet_id: Mapped[str | None] = mapped_column(String(100))

    results: Mapped[list["Result"]] = relationship(back_populates="meet")

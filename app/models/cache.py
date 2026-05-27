from datetime import datetime

from sqlalchemy import String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DataSourceCache(Base):
    __tablename__ = "data_source_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(30))
    operation: Mapped[str] = mapped_column(String(50))
    raw_payload: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(default=func.now())
    expires_at: Mapped[datetime]
    fetch_duration_ms: Mapped[int | None]

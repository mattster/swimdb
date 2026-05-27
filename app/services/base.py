import json
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cache import DataSourceCache
from app.services.normalizer import AthleteRecord, MeetRecord, ResultRecord


class DataSource(ABC):
    source_name: str
    default_ttl_seconds: int = 3600 * 6  # 6 hours

    @abstractmethod
    async def search_athletes(self, name: str) -> list[AthleteRecord]:
        """Return athletes matching name query."""

    @abstractmethod
    async def get_athlete_meets(self, source_id: str) -> list[MeetRecord]:
        """Return meet list for an athlete by their source-specific ID."""

    @abstractmethod
    async def get_event_top_times(
        self,
        gender: str,
        distance: int,
        stroke: str,
        course: str,
        limit: int = 100,
        year: int | None = None,
    ) -> list[ResultRecord]:
        """Return top N times for an event. If year given, restrict to that year."""

    async def _get_cached(self, key: str, session: AsyncSession) -> str | None:
        now = datetime.now(timezone.utc)
        row = await session.scalar(
            select(DataSourceCache).where(
                DataSourceCache.cache_key == key,
                DataSourceCache.expires_at > now,
            )
        )
        return row.raw_payload if row else None

    async def _set_cached(
        self, key: str, payload: str, ttl: int, session: AsyncSession
    ) -> None:
        now = datetime.now(timezone.utc)
        existing = await session.scalar(
            select(DataSourceCache).where(DataSourceCache.cache_key == key)
        )
        if existing:
            existing.raw_payload = payload
            existing.fetched_at = now
            existing.expires_at = now + timedelta(seconds=ttl)
        else:
            session.add(
                DataSourceCache(
                    cache_key=key,
                    source=self.source_name,
                    operation=key.split(":")[1] if ":" in key else "unknown",
                    raw_payload=payload,
                    fetched_at=now,
                    expires_at=now + timedelta(seconds=ttl),
                )
            )
        await session.commit()

    def _cache_key(self, operation: str, **params) -> str:
        param_str = "_".join(f"{k}-{v}" for k, v in sorted(params.items()))
        return f"{self.source_name}:{operation}:{param_str}"

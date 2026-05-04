"""Candle representation used by the live observation pipeline.

Independent from :class:`fx_monitor.core.models.MarketCandle` on purpose:
the live layer must not pull in the legacy module hierarchy that carries
trading-decision schemas.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from pydantic import BaseModel, Field


class Candle(BaseModel):
    """A single OHLC bar with optional volume."""

    t: datetime
    o: float
    h: float
    l: float
    c: float
    v: float | None = None

    def is_well_formed(self) -> bool:
        return self.h >= max(self.o, self.c) and self.l <= min(self.o, self.c)


class CandleSeries(BaseModel):
    """Ordered immutable series of candles with simple accessors."""

    symbol: str
    timeframe: str
    candles: list[Candle] = Field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.candles)

    def closes(self) -> list[float]:
        return [c.c for c in self.candles]

    def highs(self) -> list[float]:
        return [c.h for c in self.candles]

    def lows(self) -> list[float]:
        return [c.l for c in self.candles]

    def slice(self, start: int, end: int | None = None) -> "CandleSeries":
        return CandleSeries(
            symbol=self.symbol,
            timeframe=self.timeframe,
            candles=self.candles[start:end],
        )

    @classmethod
    def from_iter(cls, symbol: str, timeframe: str, items: Iterable[Candle]) -> "CandleSeries":
        return cls(symbol=symbol, timeframe=timeframe, candles=list(items))


__all__ = ["Candle", "CandleSeries"]

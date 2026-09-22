"""Market context: trend SMAs, event calendar, VIX.

The trend filter needs SMA10/30/50 on a CONTIGUOUS price history. This was a
real bug source in the research phase: the ThetaData option databases covered
March, April-June and October-December 2023, and naively computing a 50-day SMA
across that gap blends June prices into October. Here we always pull a
contiguous ~120 calendar-day window from Polygon, so the gap cannot occur.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Any

log = logging.getLogger(__name__)


def smas(closes: list[float]) -> dict[str, float | None]:
    def sma(n: int) -> float | None:
        return sum(closes[-n:]) / n if len(closes) >= n else None
    return {
        "close": closes[-1] if closes else None,
        "sma10": sma(10),
        "sma30": sma(30),
        "sma50": sma(50),
    }


class ContextProvider:
    """Caches trend and event data for a scan."""

    def __init__(self, polygon, events: dict[str, list] | None = None):
        self.poly = polygon
        self.events = events or {}
        self._trend: dict[str, dict] = {}
        self._vix: float | None = None

    async def load_trend(self, symbols: list[str], today: date,
                         lookback_days: int = 120) -> dict[str, dict]:
        start = today - timedelta(days=lookback_days)

        async def one(sym: str):
            try:
                bars = await self.poly.daily_bars(sym, start, today)
                closes = [b["close"] for b in bars]
                if len(closes) < 50:
                    return sym, None
                return sym, smas(closes)
            except Exception as e:
                log.debug("trend %s failed: %s", sym, e)
                return sym, None

        results = await asyncio.gather(*(one(s) for s in symbols))
        self._trend = {s: v for s, v in results if v}
        missing = len(symbols) - len(self._trend)
        if missing:
            log.info("trend data unavailable for %d/%d symbols", missing, len(symbols))
        return self._trend

    def trend(self, symbol: str) -> dict | None:
        return self._trend.get(symbol)

    async def vix(self) -> float | None:
        if self._vix is None:
            try:
                bars = await self.poly.daily_bars(
                    "I:VIX", date.today() - timedelta(days=10), date.today())
                self._vix = bars[-1]["close"] if bars else None
            except Exception:
                self._vix = None
        return self._vix

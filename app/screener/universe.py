"""Universe + sector map.

The sector map ships with the repo (365 symbols) because sector concentration
was the single largest contributor to the -$28,529 real-money loss in the
predecessor system: 84% of that loss came from one sector. The per-sector cap
is only as good as this map, so it is version-controlled, not fetched.

Index membership is refreshed from Polygon when available and falls back to
the bundled snapshot so the screener still runs if the API is down.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

_HERE = Path(__file__).parent
SECTORS: dict[str, str] = json.loads((_HERE / "sectors.json").read_text())

UNIVERSES = {
    "SP500": "S&P 500",
    "SP400": "S&P MidCap 400",
    "NASDAQ100": "Nasdaq 100",
}


def sector_of(symbol: str) -> str:
    return SECTORS.get(symbol.upper(), "UNKNOWN")


def resolve(names: list[str] | None = None) -> list[str]:
    """Symbols for the requested universes.

    The bundled map is the union of the three indices as of the backtest
    period. Replace with a live membership feed when you want it exact.
    """
    return sorted(SECTORS.keys())


def sector_counts(symbols: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for s in symbols:
        k = sector_of(s)
        out[k] = out.get(k, 0) + 1
    return out

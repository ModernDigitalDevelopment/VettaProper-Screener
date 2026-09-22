"""Earnings / ex-dividend calendar.

The 12-day earnings+dividend blackout was the highest-value single filter in
testing, so this module fails LOUD: if no calendar can be loaded, the scan
attaches a warning rather than quietly screening without it.

Bundled file (data/events.json) is a static snapshot. For live use, point
EVENTS_SOURCE at a provider or refresh the JSON on a schedule.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

DATA = Path(__file__).parent.parent.parent / "backtest" / "data"


@lru_cache(maxsize=1)
def load_events() -> dict[str, list[tuple[date, str]]]:
    """symbol -> sorted [(date, 'EARNINGS'|'EX_DIV')]"""
    path = Path(os.getenv("EVENTS_FILE", DATA / "events.json"))
    if not path.exists():
        log.warning("no events calendar at %s — blackout filter inactive", path)
        return {}
    raw = json.loads(path.read_text())
    out: dict[str, list[tuple[date, str]]] = {}
    for sym, rows in raw.items():
        parsed = []
        for d, t in rows:
            try:
                parsed.append((datetime.strptime(str(d)[:10], "%Y-%m-%d").date(), t))
            except ValueError:
                continue
        out[sym] = sorted(parsed)
    log.info("loaded events for %d symbols from %s", len(out), path.name)
    return out

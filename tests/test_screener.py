"""Tests for ranking, gates, sizing and order safety."""
from datetime import date, timedelta

import pytest

from app.brokers.base import OrderLeg, OrderRequest, occ_symbol
from app.core.criteria import Criteria, preset, PRESETS
from app.core.ranking import expected_return_on_risk, score, explain
from app.screener.engine import (build_candidate, event_blackout, select,
                                 size_candidate, trend_ok)

TODAY = date(2026, 9, 22)
EXP = (TODAY + timedelta(days=9)).isoformat()


def mk(strike, right, delta, bid, ask, oi=500):
    return dict(symbol="X", ticker=f"O:X{strike}", expiration=EXP, strike=strike,
                right=right, bid=bid, ask=ask, mid=(bid + ask) / 2, delta=delta,
                open_interest=oi, volume=100, iv=0.25)


GOOD_CHAIN = [mk(180, "PUT", -0.30, 1.90, 1.96), mk(175, "PUT", -0.16, 0.70, 0.74)]


# ---- ranking ------------------------------------------------------------

def test_higher_rr_ranks_higher_at_same_delta():
    lo = expected_return_on_risk(credit=0.50, width=5.0, delta=0.30)
    hi = expected_return_on_risk(credit=1.20, width=5.0, delta=0.30)
    assert hi > lo


def test_higher_delta_penalised_at_same_rr():
    """Same credit and width, deeper delta must score worse."""
    a = expected_return_on_risk(credit=1.00, width=5.0, delta=0.25)
    b = expected_return_on_risk(credit=1.00, width=5.0, delta=0.45)
    assert a > b


def test_degenerate_structure_scores_last():
    assert score(credit=6.0, width=5.0, delta=0.3) == -9.99


def test_explanation_components_sum_to_score():
    e = explain(1.20, 5.0, 0.30)
    total = (0.1408 + e.rr_contribution + e.delta_contribution
             + e.interaction_contribution)
    assert abs(total - e.expected_ror) < 1e-9


# ---- gates --------------------------------------------------------------

def test_risk_reward_gate_rejects_thin_credit():
    c = preset("validated_conservative")          # min_risk_reward = 0.20
    thin = [mk(180, "PUT", -0.30, 1.00, 1.06), mk(175, "PUT", -0.18, 0.42, 0.46)]
    assert build_candidate("X", "TECH", thin, c, TODAY) is None


def test_wide_spread_rejected():
    c = preset("validated_conservative")
    wide = [mk(180, "PUT", -0.30, 1.50, 2.40), mk(175, "PUT", -0.16, 0.70, 0.74)]
    assert build_candidate("X", "TECH", wide, c, TODAY) is None


def test_low_open_interest_rejected():
    c = preset("validated_conservative")
    illiquid = [mk(180, "PUT", -0.30, 1.90, 1.96, oi=2), mk(175, "PUT", -0.16, 0.70, 0.74)]
    assert build_candidate("X", "TECH", illiquid, c, TODAY) is None


def test_zero_max_loss_artifact_rejected():
    """The condor bug: credit ~= width made max loss ~0 and sizing exploded."""
    c = Criteria(min_risk_reward=0.0, width=1.0, width_tol=1.1)
    artifact = [mk(180, "PUT", -0.30, 0.98, 0.99), mk(179, "PUT", -0.20, 0.01, 0.02)]
    cand = build_candidate("X", "TECH", artifact, c, TODAY)
    assert cand is None, "near-zero max loss must never become a position"


def test_event_blackout_blocks_within_window():
    c = Criteria(earnings_blackout_days=12, blackout_exdiv=True)
    events = {"X": [(TODAY + timedelta(days=5), "EARNINGS")]}
    assert event_blackout("X", TODAY, events, c) is not None


def test_event_blackout_allows_outside_window():
    c = Criteria(earnings_blackout_days=12, blackout_exdiv=True)
    events = {"X": [(TODAY + timedelta(days=30), "EARNINGS")]}
    assert event_blackout("X", TODAY, events, c) is None


def test_exdiv_only_blocked_when_enabled():
    events = {"X": [(TODAY + timedelta(days=3), "EX_DIV")]}
    on = Criteria(earnings_blackout_days=12, blackout_exdiv=True)
    off = Criteria(earnings_blackout_days=12, blackout_exdiv=False)
    assert event_blackout("X", TODAY, events, on) is not None
    assert event_blackout("X", TODAY, events, off) is None


@pytest.mark.parametrize("bars,mode,expected", [
    ({"close": 110, "sma10": 105, "sma30": 102, "sma50": 100}, "s10_50", True),
    ({"close": 95,  "sma10": 105, "sma30": 102, "sma50": 100}, "s10_50", False),
    ({"close": 110, "sma10": 99,  "sma30": 102, "sma50": 100}, "s10_50", False),
    ({"close": 95,  "sma10": 99,  "sma30": 102, "sma50": 100}, "below50", True),
    (None, "s10_50", False),
    (None, "none", True),
])
def test_trend_modes(bars, mode, expected):
    assert trend_ok(bars, Criteria(trend_mode=mode), "bull_put") is expected


# ---- sizing -------------------------------------------------------------

def test_sizing_respects_pct_cap():
    c = preset("validated_conservative")           # 5% of 50k = 2500
    cand = build_candidate("X", "TECH", GOOD_CHAIN, c, TODAY)
    size_candidate(cand, c)
    assert cand.total_risk <= c.equity * c.max_pct_per_position
    assert cand.contracts >= 1


def test_contract_cap_enforced():
    c = Criteria(equity=10_000_000, max_pct_per_position=0.5, max_contracts=20,
                 min_risk_reward=0.0)
    cand = build_candidate("X", "TECH", GOOD_CHAIN, c, TODAY)
    size_candidate(cand, c)
    assert cand.contracts <= 20


def test_sector_cap_enforced():
    c = Criteria(max_per_sector=1, min_risk_reward=0.0, max_new_per_day=10)
    a = build_candidate("A", "TECH", GOOD_CHAIN, c, TODAY)
    b = build_candidate("B", "TECH", GOOD_CHAIN, c, TODAY)
    a.symbol, b.symbol = "A", "B"
    chosen = select([a, b], c)
    assert len(chosen) == 1


def test_select_orders_by_score():
    c = Criteria(max_per_sector=5, min_risk_reward=0.0, max_new_per_day=10)
    weak = build_candidate("W", "TECH", GOOD_CHAIN, c, TODAY)
    strong_chain = [mk(180, "PUT", -0.26, 2.20, 2.26), mk(175, "PUT", -0.14, 0.50, 0.54)]
    strong = build_candidate("S", "HEALTH", strong_chain, c, TODAY)
    chosen = select([weak, strong], c)
    assert chosen[0].rank_score >= chosen[1].rank_score


# ---- order safety -------------------------------------------------------

def test_occ_symbol_format():
    assert occ_symbol("AAPL", "2026-01-22", "PUT", 180.0) == "AAPL260122P00180000"
    assert occ_symbol("SPY", "2026-10-03", "CALL", 612.5) == "SPY261003C00612500"


def test_client_order_id_is_idempotent():
    legs = [OrderLeg("SELL", "PUT", 180, EXP, "AAPL"),
            OrderLeg("BUY", "PUT", 175, EXP, "AAPL")]
    r1 = OrderRequest("AAPL", legs, 6, 1.21)
    r2 = OrderRequest("AAPL", list(reversed(legs)), 6, 1.21)
    assert r1.client_order_id(TODAY) == r2.client_order_id(TODAY)


def test_client_order_id_changes_with_economics():
    legs = [OrderLeg("SELL", "PUT", 180, EXP, "AAPL")]
    base = OrderRequest("AAPL", legs, 6, 1.21).client_order_id(TODAY)
    assert OrderRequest("AAPL", legs, 7, 1.21).client_order_id(TODAY) != base
    assert OrderRequest("AAPL", legs, 6, 1.35).client_order_id(TODAY) != base


@pytest.mark.asyncio
async def test_brokers_default_to_dry_run(monkeypatch):
    monkeypatch.delenv("VPS_ALPACA_LIVE", raising=False)
    monkeypatch.delenv("VPS_IBKR_LIVE", raising=False)
    from app.brokers.alpaca import AlpacaBroker
    from app.brokers.ibkr import IBKRBroker
    assert AlpacaBroker().dry_run is True
    assert IBKRBroker().dry_run is True


@pytest.mark.asyncio
async def test_dry_run_never_sends(monkeypatch):
    monkeypatch.delenv("VPS_ALPACA_LIVE", raising=False)
    from app.brokers.alpaca import AlpacaBroker
    b = AlpacaBroker(key="k", secret="s")
    legs = [OrderLeg("SELL", "PUT", 180, EXP, "AAPL"),
            OrderLeg("BUY", "PUT", 175, EXP, "AAPL")]
    res = await b.submit(OrderRequest("AAPL", legs, 1, 1.0))
    assert res.state.value == "DRY_RUN"


# ---- presets ------------------------------------------------------------

def test_every_preset_loads_and_has_measured_results():
    for name, p in PRESETS.items():
        c = preset(name)
        assert isinstance(c, Criteria)
        assert p["measured"]["trades"] > 0
        assert 0 < p["measured"]["win_rate"] <= 100


def test_ivrv_is_off_by_default():
    """User requirement: no IV/RV anywhere unless explicitly enabled."""
    assert Criteria().use_ivrv is False
    for name in PRESETS:
        assert preset(name).use_ivrv is False


# ---- sector cap applies to the EXISTING book, not just today ------------

def test_sector_cap_counts_already_open_positions():
    """The cap is portfolio-wide. Holding TECH blocks new TECH entries."""
    c = Criteria(max_per_sector=1, min_risk_reward=0.0, max_new_per_day=10)
    cand = build_candidate("NEW", "TECH", GOOD_CHAIN, c, TODAY)
    # nothing open -> accepted
    assert len(select([cand], c, open_sectors={})) == 1
    # one TECH already open -> rejected
    cand2 = build_candidate("NEW", "TECH", GOOD_CHAIN, c, TODAY)
    assert len(select([cand2], c, open_sectors={"TECH": 1})) == 0


def test_open_sectors_allows_other_sectors():
    c = Criteria(max_per_sector=1, min_risk_reward=0.0, max_new_per_day=10)
    cand = build_candidate("H", "HEALTH", GOOD_CHAIN, c, TODAY)
    assert len(select([cand], c, open_sectors={"TECH": 1})) == 1


def test_two_per_sector_respects_existing_one():
    c = Criteria(max_per_sector=2, min_risk_reward=0.0, max_new_per_day=10)
    a = build_candidate("A", "TECH", GOOD_CHAIN, c, TODAY)
    b = build_candidate("B", "TECH", GOOD_CHAIN, c, TODAY)
    a.symbol, b.symbol = "A", "B"
    # one already open, cap 2 -> only one more allowed
    assert len(select([a, b], c, open_sectors={"TECH": 1})) == 1


# ---- deployability ------------------------------------------------------

def test_container_file_set_is_sufficient():
    """Everything the Dockerfile copies must be enough to boot the app.

    Catches the class of bug where a data file the app needs at import time
    is gitignored or omitted from the COPY list, so it works locally and
    crashes on deploy.
    """
    from pathlib import Path
    root = Path(__file__).parent.parent
    dockerfile = (root / "Dockerfile").read_text()
    for needed in ("app/", "web/", "backtest/data/events.json"):
        assert needed in dockerfile, f"Dockerfile must COPY {needed}"


def test_dockerignore_excludes_secrets():
    from pathlib import Path
    di = (Path(__file__).parent.parent / ".dockerignore").read_text().split()
    assert ".env" in di, ".env must never be baked into an image"


def test_events_calendar_loads_from_packaged_path():
    """The 12-day blackout was the highest-value filter — it must not
    silently deactivate in a container."""
    from app.screener.events import load_events
    load_events.cache_clear()
    ev = load_events()
    assert len(ev) > 300, f"expected the bundled calendar, got {len(ev)} symbols"

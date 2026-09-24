"""Screener criteria — every field here is a toggle you can flip from the UI.

Defaults are the backtest-validated configuration:
    5% per position, 1 per sector, 12-day earnings+dividend blackout,
    SMA10>50 trend, R:R >= 0.20, no IV/RV.

Provenance for each default is recorded in docs/BACKTEST.md.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field, fields
from typing import Any


@dataclass
class Criteria:
    # ---- structure -------------------------------------------------------
    structure: str = "bull_put"          # bull_put | bear_call | iron_condor
    short_delta: float = 0.30            # target short-leg delta
    delta_tol: float = 0.20              # accept 0.10 .. 0.50, ranking picks
    width: float = 5.0                   # strike width in dollars
    width_tol: float = 5.1

    # ---- expiry ----------------------------------------------------------
    target_dte: int = 9
    dte_tol: int = 2                     # 7..11 DTE

    # ---- liquidity -------------------------------------------------------
    max_rel_spread: float = 0.10         # bid/ask spread <= 10% of mid
    min_credit: float = 0.10
    min_open_interest: int = 25
    min_volume: int = 0

    # ---- edge gates ------------------------------------------------------
    min_risk_reward: float = 0.20        # credit / max_loss
    use_ivrv: bool = False               # OFF by default — hurt performance
    min_ivrv: float = 1.2                # only applied when use_ivrv is True

    # ---- event blackout --------------------------------------------------
    earnings_blackout_days: int = 12
    blackout_exdiv: bool = True

    # ---- trend -----------------------------------------------------------
    trend_mode: str = "s10_50"           # "" | none | s10_50 | s10_30 | below50

    # ---- technical indicators (ported from the Vetta screener) ----------
    # ADX >= 20 was the single best addition found: +32% net, +3.8pp win rate,
    # -9.6pp drawdown, on 15% fewer trades. See docs/INDICATORS.md.
    min_adx: float = 20.0                # 0 disables
    rsi_lo: float = 0.0                  # RSI band; 0/0 disables.
    rsi_hi: float = 0.0                  # Tested: did NOT help the portfolio.
    require_di_bullish: bool = False      # +DI > -DI

    # ---- regime ----------------------------------------------------------
    max_vix: float = 0.0                 # 0 disables
    min_vix: float = 0.0

    # ---- portfolio / sizing ---------------------------------------------
    equity: float = 50_000.0
    max_pct_per_position: float = 0.05
    max_per_sector: int = 1
    max_open: int = 12
    max_new_per_day: int = 4
    max_contracts: int = 20
    min_max_loss_per_ct: float = 25.0

    # ---- exits -----------------------------------------------------------
    profit_target: float = 0.80
    exit_days_before_expiry: int = 0
    hold_to_expiry: bool = False

    # ---- costs -----------------------------------------------------------
    commission_per_contract_leg: float = 0.65

    # ---- universe --------------------------------------------------------
    universe: list[str] = field(default_factory=lambda: ["SP500", "SP400", "NASDAQ100"])

    # ---- ranking ---------------------------------------------------------
    rank_mode: str = "score"             # score | cw | rr | delta

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Criteria":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (d or {}).items() if k in known})


# Named presets straight out of the backtest grid. Each carries its measured
# result so the UI can show what you are actually selecting.
PRESETS: dict[str, dict[str, Any]] = {
    "adx_trend_strength": {
        "label": "ADX Trend Strength (recommended) — best tested",
        "measured": {
            "trades": 205, "win_rate": 80.0, "expectancy": 344.03,
            "net": 70526, "profit_factor": 2.20,
            "max_dd_pct": 14.6, "peak_risk_pct": 51,
            "period": "2023 (7 months), 100% mid fills",
        },
        "criteria": {
            "max_pct_per_position": 0.05, "max_per_sector": 1,
            "min_risk_reward": 0.20, "rank_mode": "score",
            "trend_mode": "s10_50", "use_ivrv": False,
            "earnings_blackout_days": 12, "blackout_exdiv": True,
            "min_adx": 20.0, "rsi_lo": 0.0, "rsi_hi": 0.0,
        },
    },
    "validated_conservative": {
        "label": "SMA only — no ADX (previous default)",
        "measured": {
            "trades": 240, "win_rate": 76.2, "expectancy": 222.22,
            "net": 53334, "profit_factor": 1.62,
            "max_dd_pct": 24.2, "peak_risk_pct": 53,
            "period": "2023 (7 months), 100% mid fills",
        },
        "criteria": {
            "max_pct_per_position": 0.05, "max_per_sector": 1,
            "min_risk_reward": 0.20, "rank_mode": "score",
            "trend_mode": "s10_50", "use_ivrv": False,
            "earnings_blackout_days": 12, "blackout_exdiv": True,
            "min_adx": 0.0,
        },
    },
    "adx_strict": {
        "label": "ADX≥25 + RSI 60-80 — highest PF, fewest trades",
        "measured": {
            "trades": 158, "win_rate": 79.1, "expectancy": 351.30,
            "net": 55505, "profit_factor": 2.31,
            "max_dd_pct": 13.0, "peak_risk_pct": 43,
            "period": "2023 (7 months), 100% mid fills",
        },
        "criteria": {
            "max_pct_per_position": 0.05, "max_per_sector": 1,
            "min_risk_reward": 0.20, "rank_mode": "score",
            "trend_mode": "s10_50", "use_ivrv": False,
            "earnings_blackout_days": 12, "blackout_exdiv": True,
            "min_adx": 25.0, "rsi_lo": 60.0, "rsi_hi": 80.0,
        },
    },
    "high_win_rate": {
        "label": "High win rate (83.7%) — tighter delta",
        "measured": {
            "trades": 300, "win_rate": 83.7, "expectancy": 172.46,
            "net": 51738, "profit_factor": 1.70,
            "max_dd_pct": 31.0, "peak_risk_pct": 57,
            "period": "2023 (7 months of data)",
        },
        "criteria": {
            "max_pct_per_position": 0.05, "max_per_sector": 2,
            "short_delta": 0.25, "delta_tol": 0.07,
            "min_risk_reward": 0.0, "rank_mode": "score",
            "trend_mode": "s10_50", "use_ivrv": False,
            "earnings_blackout_days": 12, "blackout_exdiv": True,
        },
    },
    "two_per_sector": {
        "label": "ADX + 2 per sector — most profit, 35% drawdown",
        "measured": {
            "trades": 254, "win_rate": 79.9, "expectancy": 315.70,
            "net": 80187, "profit_factor": 2.00,
            "max_dd_pct": 35.5, "peak_risk_pct": 57,
            "period": "2023 (7 months), 100% mid fills",
        },
        "criteria": {
            "max_pct_per_position": 0.05, "max_per_sector": 2,
            "min_risk_reward": 0.20, "rank_mode": "score",
            "trend_mode": "s10_50", "use_ivrv": False,
            "earnings_blackout_days": 12, "blackout_exdiv": True,
            "min_adx": 20.0,
        },
    },
    "aggressive_10pct": {
        "label": "10% sizing — WARNING: 41% drawdown",
        "measured": {
            "trades": 174, "win_rate": 73.6, "expectancy": 418.39,
            "net": 72800, "profit_factor": 1.54,
            "max_dd_pct": 41.0, "peak_risk_pct": 59,
            "period": "2023 (7 months of data)",
        },
        "criteria": {
            "max_pct_per_position": 0.10, "max_per_sector": 1,
            "max_open": 6, "min_risk_reward": 0.20, "rank_mode": "score",
            "trend_mode": "s10_50", "use_ivrv": False,
            "earnings_blackout_days": 12, "blackout_exdiv": True,
        },
    },
}


def preset(name: str) -> Criteria:
    p = PRESETS.get(name)
    if not p:
        raise KeyError(f"unknown preset {name!r}; have {list(PRESETS)}")
    return Criteria.from_dict(p["criteria"])

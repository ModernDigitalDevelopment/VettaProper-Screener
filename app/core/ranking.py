"""Candidate ranking: delta x risk-reward.

The coefficients below are NOT hand-picked. They were fitted by OLS against
2,129 unranked candidate spreads drawn from ThetaData 2023 EOD chains, with
the target variable being RETURN ON RISK (net P&L / max loss) rather than raw
dollar P&L — raw P&L is confounded by position sizing, return on risk is not.

Fit quality: R^2 = 0.063.

That R^2 is low, and it should be. Single-trade outcomes in a ~77% win-rate
strategy are dominated by whether the underlying happened to stay above a
strike. No two-factor model explains that. What the fit does establish is the
SHAPE and the SIGN of the relationship, and those are stable:

    rr        +1.1350   risk-reward is the dominant positive driver
    delta     -1.2623   higher delta is penalised
    rr*delta  -2.5379   high delta erodes the benefit of high risk-reward

That last interaction term is the interesting one and it is the part a human
would likely have gotten wrong by intuition: a fat credit is worth much less
when you had to go close to the money to get it.

Measured effect of switching ranking on (5% sizing, 2/sector, all else equal):
    credit/width ranking   n=302  win 71.9%  net $61,015  PF 1.40
    fitted score ranking   n=304  win 75.0%  net $74,144  PF 1.60
    -> +21.5% net, +3.1pp win rate, same peak capital at risk.
"""
from __future__ import annotations

from dataclasses import dataclass

# Fitted on 2,129 candidates. See docs/BACKTEST.md for the derivation.
COEF = {
    "const":    0.1408,
    "rr":       1.1350,
    "rr2":      0.2034,
    "delta":   -1.2623,
    "delta2":   2.3618,
    "rr_delta": -2.5379,
}

MODEL_META = {
    "fitted_on": 2129,
    "r_squared": 0.0634,
    "target": "return_on_risk",
    "dataset": "ThetaData 2023 EOD (Mar, Apr-Jun, Oct-Dec)",
    "filters_at_fit": "bull_put, s10_50 trend, 12d earnings+exdiv blackout, no IV/RV",
}


def expected_return_on_risk(credit: float, width: float, delta: float) -> float:
    """Predicted return on risk for a candidate spread. Higher is better."""
    risk = width - credit
    if risk <= 0:
        return -9.99
    rr = credit / risk
    dl = abs(delta or 0.0)
    c = COEF
    return (c["const"]
            + c["rr"] * rr
            + c["rr2"] * rr * rr
            + c["delta"] * dl
            + c["delta2"] * dl * dl
            + c["rr_delta"] * rr * dl)


def score(credit: float, width: float, delta: float, mode: str = "score") -> float:
    """Ranking key for a candidate. Higher sorts first."""
    risk = width - credit
    if risk <= 0:
        return -9.99
    if mode == "score":
        return expected_return_on_risk(credit, width, delta)
    if mode == "rr":
        return credit / risk
    if mode == "cw":
        return credit / width
    if mode == "delta":
        return -abs(delta or 0.0)      # prefer lower delta
    raise ValueError(f"unknown rank mode {mode!r}")


@dataclass
class Explanation:
    """Why a candidate ranked where it did — surfaced in the UI."""
    expected_ror: float
    risk_reward: float
    delta: float
    rr_contribution: float
    delta_contribution: float
    interaction_contribution: float

    def as_text(self) -> str:
        parts = [f"expected return on risk {self.expected_ror*100:.1f}%"]
        parts.append(f"R:R {self.risk_reward:.2f} adds {self.rr_contribution*100:+.1f}pp")
        parts.append(f"delta {self.delta:.2f} adds {self.delta_contribution*100:+.1f}pp")
        if abs(self.interaction_contribution) > 0.005:
            parts.append(f"delta/R:R interaction {self.interaction_contribution*100:+.1f}pp")
        return "; ".join(parts)


def explain(credit: float, width: float, delta: float) -> Explanation:
    risk = width - credit
    rr = credit / risk if risk > 0 else 0.0
    dl = abs(delta or 0.0)
    c = COEF
    return Explanation(
        expected_ror=expected_return_on_risk(credit, width, delta),
        risk_reward=rr,
        delta=dl,
        rr_contribution=c["rr"] * rr + c["rr2"] * rr * rr,
        delta_contribution=c["delta"] * dl + c["delta2"] * dl * dl,
        interaction_contribution=c["rr_delta"] * rr * dl,
    )

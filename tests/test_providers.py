"""Provider parity and IBKR/Alpaca data-layer tests.

The critical property: all providers must emit the SAME row shape, because the
screener engine consumes them interchangeably. If a provider drops a field the
engine relies on (delta, open_interest), spreads silently stop being built.
"""
import os

import pytest

from app.providers import factory
from app.providers.alpaca_data import _normalise as alpaca_normalise, _parse_occ
from app.providers.ibkr_data import _f
from app.providers.polygon import _normalise_contract as poly_normalise

# fields the screener engine requires from every provider
REQUIRED = {"symbol", "expiration", "strike", "right", "bid", "ask", "mid",
            "delta", "open_interest", "volume"}


# ---- IBKR value parsing -------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("12.34", 12.34),
    ("C12.34", 12.34),      # C prefix = previous close
    ("H98.6", 98.6),        # H prefix = halted
    ("1,234.5", 1234.5),
    (4.2, 4.2),
    (None, None), ("", None), ("-", None), ("n/a", None),
])
def test_ibkr_value_parsing(raw, expected):
    assert _f(raw) == expected


# ---- OCC round-trip -----------------------------------------------------

@pytest.mark.parametrize("occ,exp,right,strike", [
    ("AAPL260122P00180000", "2026-01-22", "PUT", 180.0),
    ("SPY261003C00612500", "2026-10-03", "CALL", 612.5),
    ("TSLA260220P00425000", "2026-02-20", "PUT", 425.0),
])
def test_alpaca_occ_parsing(occ, exp, right, strike):
    assert _parse_occ(occ) == (exp, right, strike)


def test_alpaca_occ_rejects_garbage():
    assert _parse_occ("NOTANOCC") is None
    assert _parse_occ("AAPL260122X00180000") is None   # bad right


# ---- row shape parity ---------------------------------------------------

def test_alpaca_row_has_required_fields():
    snap = {"latestQuote": {"bp": 1.90, "ap": 1.96},
            "greeks": {"delta": -0.30, "gamma": 0.02, "theta": -0.05, "vega": 0.11},
            "impliedVolatility": 0.284, "openInterest": 1420,
            "latestTrade": {"s": 35}}
    row = alpaca_normalise("AAPL260122P00180000", snap, "AAPL")
    assert REQUIRED <= set(row)
    assert row["mid"] == pytest.approx(1.93)
    assert row["right"] == "PUT"


def test_polygon_row_has_required_fields():
    c = {"details": {"strike_price": 180.0, "expiration_date": "2026-01-22",
                     "contract_type": "put", "ticker": "O:AAPL260122P00180000"},
         "last_quote": {"bid": 1.90, "ask": 1.96},
         "greeks": {"delta": -0.30}, "implied_volatility": 0.284,
         "open_interest": 1420, "day": {"volume": 35}}
    row = poly_normalise(c, "AAPL")
    assert REQUIRED <= set(row)
    assert row["mid"] == pytest.approx(1.93)


def test_providers_agree_on_shape():
    """Same economic contract through both normalisers -> same keys/values."""
    a = alpaca_normalise("AAPL260122P00180000",
                         {"latestQuote": {"bp": 1.90, "ap": 1.96},
                          "greeks": {"delta": -0.30}, "impliedVolatility": 0.284,
                          "openInterest": 1420, "latestTrade": {"s": 35}}, "AAPL")
    p = poly_normalise({"details": {"strike_price": 180.0,
                                    "expiration_date": "2026-01-22",
                                    "contract_type": "put"},
                        "last_quote": {"bid": 1.90, "ask": 1.96},
                        "greeks": {"delta": -0.30}, "implied_volatility": 0.284,
                        "open_interest": 1420, "day": {"volume": 35}}, "AAPL")
    for k in REQUIRED:
        assert a[k] == p[k], f"providers disagree on {k}: {a[k]} vs {p[k]}"


# ---- rejection of bad quotes -------------------------------------------

@pytest.mark.parametrize("quote", [
    {"bp": None, "ap": 1.96},      # missing bid
    {"bp": 1.90, "ap": None},      # missing ask
    {"bp": 2.50, "ap": 1.96},      # crossed
    {"bp": 1.90, "ap": 0.0},       # zero ask
])
def test_bad_quotes_rejected(quote):
    snap = {"latestQuote": quote, "greeks": {"delta": -0.3},
            "openInterest": 100, "latestTrade": {"s": 1}}
    assert alpaca_normalise("AAPL260122P00180000", snap, "AAPL") is None


# ---- factory ------------------------------------------------------------

def test_factory_lists_all_providers():
    av = factory.available()
    assert set(av) == {"polygon", "alpaca", "ibkr"}
    assert av["ibkr"]["bulk_chain"] is False      # the important caveat
    assert av["polygon"]["bulk_chain"] is True
    assert av["alpaca"]["bulk_chain"] is True


def test_factory_rejects_unknown():
    with pytest.raises(ValueError):
        factory.make("nasdaq_direct")


def test_factory_falls_back_to_alpaca(monkeypatch):
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    monkeypatch.setenv("APCA_API_KEY_ID", "k")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "s")
    c = factory.make("polygon")
    from app.providers.alpaca_data import AlpacaDataClient
    assert isinstance(c, AlpacaDataClient)


def test_factory_raises_when_nothing_configured(monkeypatch):
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    with pytest.raises(RuntimeError):
        factory.make("polygon")

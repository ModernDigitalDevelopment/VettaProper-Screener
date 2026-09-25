#!/usr/bin/env python3
"""Verify credentials and data access before trading.

    python check_config.py            # local checks only, no network
    python check_config.py --live     # also make one real API call per provider

Prints only the first 6 characters of any key. Never logs a full secret.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

# Same blank-is-unset handling as app/main.py
for _k in ("POLYGON_API_KEY", "APCA_API_KEY_ID", "APCA_API_SECRET_KEY",
           "IBKR_GATEWAY_URL", "DATA_PROVIDER"):
    if os.environ.get(_k, "__missing__") == "":
        del os.environ[_k]

DOTENV = find_dotenv(usecwd=True)
load_dotenv(DOTENV, override=False)

OK, NO, WARN = "  [ok]  ", "  [--]  ", "  [!!]  "


def mask(v: str | None) -> str:
    if not v:
        return "(not set)"
    return f"{v[:6]}{'*' * max(len(v) - 6, 0)} ({len(v)} chars)"


def local() -> bool:
    print("=" * 66)
    print("CONFIGURATION")
    print("=" * 66)

    if DOTENV:
        print(f"{OK}.env found: {DOTENV}")
    else:
        print(f"{WARN}no .env file found")
        print("        create one:  cp .env.example .env")

    # never let a real key reach git
    root = Path(__file__).parent
    gi = (root / ".gitignore")
    if gi.exists() and ".env" in gi.read_text().split():
        print(f"{OK}.env is gitignored")
    else:
        print(f"{WARN}.env may NOT be gitignored — check before committing")

    print()
    poly = os.getenv("POLYGON_API_KEY")
    apca = os.getenv("APCA_API_KEY_ID")
    apcs = os.getenv("APCA_API_SECRET_KEY")
    gw = os.getenv("IBKR_GATEWAY_URL")
    provider = os.getenv("DATA_PROVIDER", "polygon")

    print(f"  DATA_PROVIDER        {provider}")
    print(f"  POLYGON_API_KEY      {mask(poly)}")
    print(f"  APCA_API_KEY_ID      {mask(apca)}")
    print(f"  APCA_API_SECRET_KEY  {mask(apcs)}")
    print(f"  IBKR_GATEWAY_URL     {gw or '(not set)'}")
    print(f"  ALPACA_OPTIONS_FEED  {os.getenv('ALPACA_OPTIONS_FEED', 'indicative')}")
    print()
    print(f"  VPS_ALPACA_LIVE      {os.getenv('VPS_ALPACA_LIVE', '0')}"
          f"{'   *** ARMED ***' if os.getenv('VPS_ALPACA_LIVE') == '1' else '   (dry run)'}")
    print(f"  VPS_IBKR_LIVE        {os.getenv('VPS_IBKR_LIVE', '0')}"
          f"{'   *** ARMED ***' if os.getenv('VPS_IBKR_LIVE') == '1' else '   (dry run)'}")

    print()
    ok = True
    if provider == "polygon" and not poly:
        if apca and apcs:
            print(f"{WARN}DATA_PROVIDER=polygon but no key — will fall back to Alpaca")
        else:
            print(f"{NO}DATA_PROVIDER=polygon but POLYGON_API_KEY is not set")
            ok = False
    if provider == "alpaca" and not (apca and apcs):
        print(f"{NO}DATA_PROVIDER=alpaca but Alpaca keys are not set")
        ok = False
    if provider == "ibkr":
        print(f"{WARN}DATA_PROVIDER=ibkr — no bulk chain endpoint; full-universe "
              "scans are blocked. Pass an explicit symbols watchlist.")

    if poly and poly.startswith("your_"):
        print(f"{NO}POLYGON_API_KEY still contains the placeholder value")
        ok = False
    return ok


async def live() -> bool:
    print()
    print("=" * 66)
    print("LIVE API CHECKS")
    print("=" * 66)
    sys.path.insert(0, str(Path(__file__).parent))
    allok = True

    # ---- Polygon --------------------------------------------------------
    if os.getenv("POLYGON_API_KEY"):
        from app.providers.polygon import PolygonClient, PolygonError
        try:
            async with PolygonClient() as c:
                bars = await c.daily_bars(
                    "AAPL", date.today() - timedelta(days=10), date.today())
                print(f"{OK}Polygon stocks: {len(bars)} AAPL daily bars")
                lo = date.today() + timedelta(days=5)
                hi = date.today() + timedelta(days=20)
                ch = await c.option_chain("AAPL", expiry_gte=lo, expiry_lte=hi,
                                          contract_type="put")
                if ch:
                    g = sum(1 for r in ch if r.get("delta") is not None)
                    print(f"{OK}Polygon options: {len(ch)} contracts, "
                          f"{g} with greeks")
                    if g == 0:
                        print(f"{WARN}   no greeks — screener needs delta to "
                              "target strikes")
                        allok = False
                else:
                    print(f"{WARN}Polygon options: chain empty "
                          "(market closed, or plan lacks options)")
        except PolygonError as e:
            print(f"{NO}Polygon: {e}")
            allok = False
        except Exception as e:
            print(f"{NO}Polygon: {type(e).__name__}: {str(e)[:150]}")
            allok = False
    else:
        print(f"{NO}Polygon: no key, skipped")

    # ---- Alpaca data ----------------------------------------------------
    if os.getenv("APCA_API_KEY_ID") and os.getenv("APCA_API_SECRET_KEY"):
        from app.providers.alpaca_data import AlpacaDataClient, AlpacaDataError
        try:
            async with AlpacaDataClient() as c:
                openq = await c.market_open()
                print(f"{OK}Alpaca data: reachable (market_open={openq})")
        except AlpacaDataError as e:
            print(f"{NO}Alpaca data: {e}")
            allok = False
        except Exception as e:
            print(f"{NO}Alpaca data: {type(e).__name__}: {str(e)[:150]}")
            allok = False

        from app.brokers.alpaca import AlpacaBroker
        b = AlpacaBroker()
        try:
            acct = await b.account()
            lvl = acct.get("options_level")
            print(f"{OK}Alpaca account: {acct.get('account_number')} "
                  f"paper={acct.get('paper')} equity=${acct.get('equity'):,.0f} "
                  f"options_level={lvl}")
            if lvl is not None and int(lvl) < 3:
                print(f"{WARN}   options level {lvl} — SPREADS REQUIRE LEVEL 3")
                allok = False
        except Exception as e:
            print(f"{NO}Alpaca account: {str(e)[:150]}")
            allok = False
    else:
        print(f"{NO}Alpaca: no keys, skipped")

    # ---- IBKR gateway ---------------------------------------------------
    if os.getenv("IBKR_GATEWAY_URL"):
        from app.brokers.ibkr import IBKRBroker
        st = await IBKRBroker().auth_status()
        if st.get("authenticated"):
            print(f"{OK}IBKR gateway: authenticated")
        elif st.get("reachable"):
            print(f"{WARN}IBKR gateway: reachable but NOT authenticated — "
                  "log in via browser (2FA)")
        else:
            print(f"{NO}IBKR gateway: unreachable at "
                  f"{os.getenv('IBKR_GATEWAY_URL')}")
    else:
        print(f"{NO}IBKR: no gateway URL, skipped")

    return allok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true",
                    help="make real API calls to verify credentials")
    a = ap.parse_args()

    ok = local()
    if a.live:
        ok = asyncio.run(live()) and ok
    else:
        print()
        print("  run with --live to verify the keys actually work")

    print()
    print("=" * 66)
    print("  ALL CHECKS PASSED" if ok else "  PROBLEMS FOUND — see above")
    print("=" * 66)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

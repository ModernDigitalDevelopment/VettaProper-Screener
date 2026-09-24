#!/usr/bin/env python3
"""Ingest 2022 minute-bar option + underlying data for out-of-sample testing.

This is the most valuable thing that can be done with the current research.
2023 was a falling-volatility recovery year — close to best case for selling
premium. 2022 was a bear market with rising volatility. If the strategy
survives 2022, the 2023 numbers mean something. If it does not, they were a
regime artifact.

WHAT THIS SCRIPT DOES

1. Downsamples minute bars to the EOD snapshots the engine expects. The
   backtest engine is EOD by design; feeding it minute data would change the
   execution model and make 2022 and 2023 incomparable.
2. Rebuilds the derived lookups (trend SMAs, events, VIX) for 2022.
3. Runs the SAME configurations that were run on 2023, with NO re-tuning.

THE CARDINAL RULE

Do not tune anything on 2022. The ranking coefficients, the delta targets, the
risk-reward gate and the blackout window were all fitted on 2023. Re-fitting
them on 2022 and reporting the result would be circular and worthless.

Run the 2023 configuration on 2022 unchanged. Whatever comes out is the
out-of-sample result, good or bad.

USAGE

    python backtest/ingest_2022.py --scan /path/to/2022/data
    python backtest/ingest_2022.py --build-eod /path/to/2022 --out data/2022_eod.db
    python backtest/ingest_2022.py --build-trend --out data/trend_2022.json.gz
"""
from __future__ import annotations

import argparse
import gzip
import json
import logging
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("ingest")

HERE = Path(__file__).parent
DATA = HERE / "data"

# Column names vary by vendor export. Add yours here if it differs.
COLUMN_ALIASES = {
    "trade_date": ["trade_date", "date", "quote_date", "dt", "timestamp"],
    "symbol": ["symbol", "root", "underlying", "ticker", "act_symbol"],
    "expiration": ["expiration", "expiry", "exp_date", "expiration_date"],
    "strike": ["strike", "strike_price"],
    "right": ["right", "type", "option_type", "call_put", "cp_flag"],
    "bid": ["bid", "bid_price", "best_bid"],
    "ask": ["ask", "ask_price", "best_ask"],
    "delta": ["delta", "greeks_delta"],
    "iv": ["iv", "implied_vol", "implied_volatility", "sigma"],
    "open_interest": ["open_interest", "oi"],
    "volume": ["volume", "vol", "trade_volume"],
}


def detect_schema(db_path: Path) -> dict:
    """Report tables and columns so mapping can be verified before ingesting."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    out = {}
    for (tbl,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({tbl})")]
        try:
            n = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        except sqlite3.Error:
            n = -1
        out[tbl] = {"columns": cols, "rows": n}
    con.close()
    return out


def map_columns(cols: list[str]) -> dict[str, str | None]:
    lower = {c.lower(): c for c in cols}
    mapping: dict[str, str | None] = {}
    for canon, aliases in COLUMN_ALIASES.items():
        mapping[canon] = next((lower[a] for a in aliases if a in lower), None)
    return mapping


def cmd_scan(path: Path) -> int:
    """Inspect downloaded files and report what was found."""
    files = sorted(list(path.glob("**/*.db")) + list(path.glob("**/*.sqlite"))
                   + list(path.glob("**/*.parquet")) + list(path.glob("**/*.csv*")))
    if not files:
        print(f"no data files found under {path}")
        return 1

    print(f"{len(files)} file(s) under {path}\n")
    total = 0
    for f in files:
        mb = f.stat().st_size / 1e6
        total += mb
        print(f"  {f.relative_to(path)}  ({mb:,.0f} MB)")
    print(f"\ntotal {total:,.0f} MB")

    for f in files:
        if f.suffix in (".db", ".sqlite"):
            print(f"\n--- schema: {f.name} ---")
            try:
                for tbl, meta in detect_schema(f).items():
                    print(f"  {tbl}: {meta['rows']:,} rows")
                    print(f"    columns: {', '.join(meta['columns'][:14])}")
                    m = map_columns(meta["columns"])
                    missing = [k for k, v in m.items() if v is None]
                    if missing:
                        print(f"    UNMAPPED: {missing}")
                        print("    -> add the real names to COLUMN_ALIASES")
                    else:
                        print("    all required columns mapped")
            except Exception as e:
                print(f"    could not read: {e}")
    return 0


def cmd_build_eod(src: Path, out: Path, table: str | None = None) -> int:
    """Collapse minute bars to one EOD row per contract per day.

    Takes the LAST quote of each trading day, matching how the 2023 ThetaData
    EOD snapshots were built. Keeping the two years comparable matters more
    than using the finer data.
    """
    dbs = sorted(list(src.glob("**/*.db")) + list(src.glob("**/*.sqlite")))
    if not dbs:
        log.error("no sqlite files under %s", src)
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    dst = sqlite3.connect(out)
    dst.execute("""
        CREATE TABLE IF NOT EXISTS option_eod (
            trade_date TEXT, symbol TEXT, expiration TEXT,
            strike REAL, right TEXT, bid REAL, ask REAL,
            delta REAL, iv REAL, open_interest INTEGER, volume INTEGER,
            PRIMARY KEY (trade_date, symbol, expiration, strike, right)
        )""")
    dst.commit()

    grand = 0
    for db in dbs:
        schema = detect_schema(db)
        tables = [table] if table else list(schema)
        for tbl in tables:
            if tbl not in schema:
                continue
            m = map_columns(schema[tbl]["columns"])
            need = ("trade_date", "symbol", "expiration", "strike", "right", "bid", "ask")
            if any(m[k] is None for k in need):
                log.warning("skipping %s.%s — unmapped columns", db.name, tbl)
                continue

            log.info("ingesting %s.%s (%s rows)", db.name, tbl, f"{schema[tbl]['rows']:,}")
            sel = f"""
                SELECT {m['trade_date']} AS d, {m['symbol']} AS sym,
                       {m['expiration']} AS exp, {m['strike']} AS k,
                       {m['right']} AS r, {m['bid']} AS b, {m['ask']} AS a,
                       {m['delta'] or 'NULL'} AS dl, {m['iv'] or 'NULL'} AS iv,
                       {m['open_interest'] or '0'} AS oi,
                       {m['volume'] or '0'} AS vol
                FROM {tbl}
                ORDER BY d, sym, exp, k, r
            """
            src_con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            batch, n = [], 0
            for row in src_con.execute(sel):
                d = str(row[0])[:10]
                rt = str(row[4]).upper()
                rt = "PUT" if rt.startswith("P") else "CALL"
                batch.append((d, row[1], str(row[2])[:10], float(row[3]), rt,
                              row[5], row[6], row[7], row[8],
                              int(row[9] or 0), int(row[10] or 0)))
                if len(batch) >= 50_000:
                    dst.executemany(
                        "INSERT OR REPLACE INTO option_eod VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        batch)
                    dst.commit(); n += len(batch); batch.clear()
                    print(f"\r  {n:,} rows", end="", flush=True)
            if batch:
                dst.executemany(
                    "INSERT OR REPLACE INTO option_eod VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    batch)
                dst.commit(); n += len(batch)
            print(f"\r  {n:,} rows from {db.name}.{tbl}")
            grand += n
            src_con.close()

    dst.execute("CREATE INDEX IF NOT EXISTS ix_eod ON option_eod(trade_date, symbol)")
    dst.commit()
    log.info("wrote %s rows to %s", f"{grand:,}", out)
    dst.close()
    return 0


def cmd_build_trend(eod_db: Path, out: Path) -> int:
    """Contiguous SMA10/30/50 from underlying closes.

    Contiguity matters: the 2023 option databases had a July-September gap, and
    computing a 50-day SMA straight off them would have blended June into
    October. Always build SMAs from an unbroken price series.
    """
    con = sqlite3.connect(f"file:{eod_db}?mode=ro", uri=True)
    tbls = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]
    price_tbl = next((t for t in tbls if "price" in t.lower() or "bar" in t.lower()
                      or "underlying" in t.lower()), None)
    if not price_tbl:
        log.error("no price/bar table found in %s; tables: %s", eod_db, tbls)
        return 1

    cols = [r[1] for r in con.execute(f"PRAGMA table_info({price_tbl})")]
    m = map_columns(cols)
    close_col = next((c for c in cols if c.lower() in ("close", "c", "close_price")), None)
    if not (m["trade_date"] and m["symbol"] and close_col):
        log.error("cannot map date/symbol/close in %s (cols: %s)", price_tbl, cols)
        return 1

    rows = con.execute(
        f"SELECT {m['symbol']}, {m['trade_date']}, {close_col} "
        f"FROM {price_tbl} ORDER BY {m['symbol']}, {m['trade_date']}").fetchall()
    con.close()

    by_sym: dict[str, list[tuple[str, float]]] = {}
    for sym, d, c in rows:
        if c is None:
            continue
        by_sym.setdefault(sym, []).append((str(d)[:10], float(c)))

    out_map: dict[str, list] = {}
    for sym, series in by_sym.items():
        closes = [c for _, c in series]
        for i, (d, c) in enumerate(series):
            if i < 49:
                continue
            w = closes[: i + 1]
            out_map[f"{sym}|{d}"] = [
                c,
                sum(w[-10:]) / 10,
                sum(w[-30:]) / 30,
                sum(w[-50:]) / 50,
            ]

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(gzip.compress(
        json.dumps(out_map, separators=(",", ":")).encode(), 9))
    log.info("wrote %s trend rows (%s symbols) to %s",
             f"{len(out_map):,}", len(by_sym), out)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scan", type=Path, help="inspect downloaded files")
    ap.add_argument("--build-eod", type=Path, help="source dir of 2022 data")
    ap.add_argument("--build-trend", type=Path, help="EOD db to derive SMAs from")
    ap.add_argument("--table", help="restrict to one source table")
    ap.add_argument("--out", type=Path, help="output path")
    a = ap.parse_args()

    if a.scan:
        return cmd_scan(a.scan)
    if a.build_eod:
        return cmd_build_eod(a.build_eod, a.out or DATA / "2022_eod.db", a.table)
    if a.build_trend:
        return cmd_build_trend(a.build_trend, a.out or DATA / "trend_2022.json.gz")
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

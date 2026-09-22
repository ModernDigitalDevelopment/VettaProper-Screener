#!/usr/bin/env python3
"""Fetch raw ThetaData option databases from object storage.

The .db files (2.5 GB total) are too large for GitHub. Keep them in S3 / R2 /
Backblaze and pull them when you want to run a backtest.

Configure with:
    BACKTEST_DATA_URL=https://<bucket>.r2.cloudflarestorage.com/vetta-backtest-data

Usage:
    python backtest/fetch_data.py --all
    python backtest/fetch_data.py --file thetadata_options_q2_2023.db
    python backtest/fetch_data.py --check          # verify what is present
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

DEST = Path(__file__).parent / "data"

FILES = {
    "thetadata_options_march_2023.db": {"size_mb": 386, "desc": "March 2023 chains"},
    "thetadata_options_q2_2023.db":    {"size_mb": 1100, "desc": "Apr-Jun 2023 chains"},
    "thetadata_options_q4_2023.db":    {"size_mb": 1100, "desc": "Oct-Dec 2023 chains"},
    "ib_screener_cache.db":            {"size_mb": 44, "desc": "Daily price bars for SMAs"},
}


def sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while blk := f.read(chunk):
            h.update(blk)
    return h.hexdigest()


def check() -> int:
    missing = 0
    print(f"{'file':<38} {'expected':>10} {'status'}")
    print("-" * 70)
    for name, meta in FILES.items():
        p = DEST / name
        if p.exists():
            mb = p.stat().st_size / 1e6
            print(f"{name:<38} {meta['size_mb']:>8} MB  present ({mb:.0f} MB)")
        else:
            print(f"{name:<38} {meta['size_mb']:>8} MB  MISSING")
            missing += 1
    if missing:
        print(f"\n{missing} file(s) missing. Run with --all to download, "
              "or see docs/DATA.md for alternatives.")
    return missing


def download(name: str, base_url: str) -> None:
    import httpx

    DEST.mkdir(parents=True, exist_ok=True)
    out = DEST / name
    tmp = out.with_suffix(out.suffix + ".part")
    url = f"{base_url.rstrip('/')}/{name}"
    print(f"downloading {name} ...")
    with httpx.stream("GET", url, timeout=None, follow_redirects=True) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with tmp.open("wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total:
                    pct = 100 * done / total
                    print(f"\r  {pct:5.1f}%  {done/1e6:.0f}/{total/1e6:.0f} MB",
                          end="", flush=True)
    print()
    tmp.rename(out)
    print(f"  saved {out}  sha256={sha256(out)[:16]}...")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="download everything missing")
    ap.add_argument("--file", help="download one file")
    ap.add_argument("--check", action="store_true", help="report what is present")
    a = ap.parse_args()

    if a.check or not (a.all or a.file):
        return 0 if check() == 0 else 1

    base = os.getenv("BACKTEST_DATA_URL")
    if not base:
        print("BACKTEST_DATA_URL is not set.\n"
              "Point it at your bucket, e.g.\n"
              "  export BACKTEST_DATA_URL=https://<acct>.r2.cloudflarestorage.com/vetta-backtest-data\n"
              "See docs/DATA.md.", file=sys.stderr)
        return 2

    targets = [a.file] if a.file else [n for n in FILES if not (DEST / n).exists()]
    if not targets:
        print("nothing to do — all files present")
        return 0
    for name in targets:
        if name not in FILES:
            print(f"unknown file {name!r}; known: {list(FILES)}", file=sys.stderr)
            return 2
        download(name, base)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

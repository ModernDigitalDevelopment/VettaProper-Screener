# Backtest data — what is in the repo, what is not, and why

## Short answer

**The derived data you need to re-run backtests IS in this repo** (9.2 MB, in
`backtest/data/`). The 2.5 GB of raw ThetaData option chains is **not**, because
GitHub cannot hold it in a normal repository.

---

## What ships in the repo

| File | Size | Contents |
|---|---|---|
| `backtest/data/events.json` | 818 KB | Earnings + ex-dividend dates, 365 symbols |
| `backtest/data/trend.json.gz` | 8.0 MB | 257,880 rows of close + SMA10/30/50 |
| `backtest/data/vix.json` | 15 KB | 753 daily VIX closes |
| `backtest/data/sectors.json` | 6.6 KB | Symbol → sector map, 365 symbols |
| `backtest/data/unranked_sample.pkl` | 402 KB | The 2,129 trades the ranking model was fitted on |
| `backtest/results/grid_results.csv` | 15 KB | All 144 grid configurations |
| `backtest/results/screener_runs.json` | — | Every screener run with monthly breakdown |

This is enough to:

- re-fit or challenge the ranking model
- re-run trend, event-blackout and sector logic
- reproduce every published metric
- test new filter combinations that use these inputs

## What does not ship, and why

| File | Size |
|---|---|
| `thetadata_options_march_2023.db` | 386 MB |
| `thetadata_options_q2_2023.db` | 1.1 GB |
| `thetadata_options_q4_2023.db` | 1.1 GB |
| `ib_screener_cache.db` | 44 MB |

GitHub rejects files over 100 MB and warns above 50 MB. Two of these are
more than ten times the hard limit.

**Git LFS is not a good answer here.** LFS on the free tier gives 1 GB of
storage and 1 GB/month of bandwidth. These files are 2.5 GB. You would be paying
for data packs immediately, and every clone would pull gigabytes.

---

## Recommended: object storage

Keep the raw databases in S3 / R2 / Backblaze and fetch on demand.
Cloudflare R2 is the cheapest sensible option — no egress fees.

```bash
# one-time upload
aws s3 cp "thetadata_options_q2_2023.db" s3://vetta-backtest-data/ \
    --endpoint-url https://<account>.r2.cloudflarestorage.com

# pull when you want to run a backtest
python backtest/fetch_data.py --all
```

At ~$0.015/GB/month, 2.5 GB costs roughly **$0.04 a month**.

`backtest/fetch_data.py` handles this and verifies checksums after download.

## Alternative: keep them local, back up separately

If backtests only ever run on one machine, object storage may be unnecessary.
Keep the `.db` files where they are and make sure they are in a backup that is
not your git repository. `.gitignore` already excludes `backtest/data/*.db` so
they cannot be committed by accident.

## Alternative: regenerate from ThetaData

You have a ThetaData subscription, so these databases are reproducible. The
extraction scripts are in the predecessor repo. Slower than a download, but it
costs nothing and lets you extend coverage beyond 2023 — which, given that the
single biggest weakness of the current research is having only seven months in
one favourable regime, is probably the highest-value thing you could do with
that subscription.

---

## Extending the dataset

The most valuable additions, in order:

1. **2022** — a genuine bear market with rising volatility. The current results
   have never been tested against one.
2. **Feb–Mar 2020** — COVID crash. A short-premium strategy's worst case.
3. **Feb 2018** — volatility spike. Tests the strategy against a fast shock
   rather than a grind.
4. **July–September 2023** — closes the gap in the existing sample.

Adding 2022 alone would tell you more about whether this strategy survives than
any further parameter tuning on 2023.

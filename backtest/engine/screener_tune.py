"""Find executable risk levels for the screener spec."""
import pickle
from concurrent.futures import ProcessPoolExecutor
from screener_bt import BASE, one, metrics

VARIANTS = [
    # label, overrides
    ("5%|score|rr.2",        dict(max_pct_per_position=0.05, rank_mode="score", min_risk_reward=0.20)),
    ("5%|score|rr.2|open8",  dict(max_pct_per_position=0.05, rank_mode="score", min_risk_reward=0.20, max_open=8)),
    ("5%|score|rr.2|1sec",   dict(max_pct_per_position=0.05, rank_mode="score", min_risk_reward=0.20, max_per_sector=1)),
    ("5%|score|d.25tol.07",  dict(max_pct_per_position=0.05, rank_mode="score", short_delta=0.25, delta_tol=0.07)),
    ("10%|score|rr.2|open6", dict(max_pct_per_position=0.10, rank_mode="score", min_risk_reward=0.20, max_open=6)),
    ("10%|score|rr.2|1sec|o6", dict(max_pct_per_position=0.10, rank_mode="score", min_risk_reward=0.20,
                                   max_per_sector=1, max_open=6)),
    ("7.5%|score|rr.2|open8", dict(max_pct_per_position=0.075, rank_mode="score", min_risk_reward=0.20, max_open=8)),
    ("5%|cw|rr.2|open8",     dict(max_pct_per_position=0.05, rank_mode="cw", min_risk_reward=0.20, max_open=8)),
]


def main():
    jobs = [(lab, dict(BASE, **ov)) for lab, ov in VARIANTS]
    out = {}
    with ProcessPoolExecutor(max_workers=4) as ex:
        for label, trades in ex.map(one, jobs):
            out[label] = trades
            print(f"{label:<24} {metrics(trades)}")
    pickle.dump(out, open("screener_tune.pkl", "wb"))


if __name__ == "__main__":
    main()

"""Risk-equalised view: dollars earned per dollar of peak drawdown.

The tail analysis showed the stop truncates single-trade losses monotonically
while leaving mean return unchanged. If that is real it should show up as
lower portfolio drawdown -- which is the thing that actually lets you size up.
net/dd is the comparison that matters, because a config with half the net but
a third of the drawdown is the better business.

Drawdown is computed on the realised equity curve ordered by EXIT date (that
is when cash moves), peak-to-trough in dollars, pooled across quarters within
each year so the curve is continuous where the data is continuous.
"""
import pickle
from collections import defaultdict

TAGS22 = ["2022Q1", "2022Q2", "2022Q3", "2022Q4"]
TAGS23 = ["2023Q2", "2023Q4"]
STOPS = ["none", "0.5", "1.0", "1.5", "2.0"]


def curve_dd(trades):
    ev, peak, dd, eq = sorted(trades, key=lambda t: t["exit_date"]), 0.0, 0.0, 0.0
    for t in ev:
        eq += t["net_pnl"]
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    return eq, dd


def main():
    data = {t: pickle.load(open(f"r_stop_{t}.pkl", "rb"))
            for t in TAGS22 + TAGS23}
    tenors = sorted({k.split("|")[0] for d in data.values() for k in d})
    for tenor in tenors:
        print("\n" + "=" * 88)
        print(f"{tenor}    net / peak-drawdown (dollars earned per dollar risked)")
        print("=" * 88)
        print(f"{'stop':<6}{'2022 net':>11}{'2022 dd':>10}{'n/dd':>8}"
              f"{'2023 net':>11}{'2023 dd':>10}{'n/dd':>8}{'BOTH n/dd':>11}")
        for s in STOPS:
            row = [s]
            tot_net = tot_dd = 0.0
            for grp in (TAGS22, TAGS23):
                tr = []
                for tag in grp:
                    rec = data[tag].get(f"{tenor}|{s}")
                    if rec:
                        tr += rec[0]
                net, dd = curve_dd(tr)
                tot_net += net
                tot_dd += dd
                row += [f"{net:>+11,.0f}", f"{dd:>10,.0f}",
                        f"{net/dd:>8.2f}" if dd else f"{'inf':>8}"]
            row.append(f"{tot_net/tot_dd:>11.2f}" if tot_dd else f"{'inf':>11}")
            print(f"{row[0]:<6}" + "".join(row[1:]))


if __name__ == "__main__":
    main()

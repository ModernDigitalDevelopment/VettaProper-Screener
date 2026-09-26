"""Generate put AND call candidates on the SAME (symbol, date) set.

Both sides run with trend_mode="none" so neither is pre-filtered by direction.
That is what makes a breadth switching test meaningful: the rule must choose
between two genuinely available alternatives, not between two disjoint sets.

max_open is raised and the sector cap removed so slot contention does not
silently drop candidates -- this is a SIGNAL test, not a portfolio test.
"""
import pickle
import spec_engine as E
from run2022 import BASE, DBS_2022, load

def main():
    load()
    out = {}
    for side in ("bull_put", "bear_call"):
        kw = dict(BASE)
        kw.update(structure=side, trend_mode="none",
                  max_per_sector=99, max_open=99, max_new_per_day=99)
        sp = E.Spec(label=f"pool_{side}", **kw)
        tr = []
        for db in DBS_2022.values():
            tr += E.run(db, sp)
        out[side] = tr
        print(f"{side:<10} {len(tr)} trades", flush=True)
    pickle.dump(out, open("pool22.pkl", "wb"))
    ps = {(t["symbol"], t["entry_date"]) for t in out["bull_put"]}
    cs = {(t["symbol"], t["entry_date"]) for t in out["bear_call"]}
    print(f"overlap: {len(ps & cs)}")

if __name__ == "__main__":
    main()

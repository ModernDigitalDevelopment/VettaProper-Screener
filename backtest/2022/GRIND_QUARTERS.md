# Long-DTE bull puts: the grind-quarter test

## Result: fails. 2 of 4 quarters, pooled negative.

|  | 7-11 DTE, exit 2 | 35-45 DTE, exit 15 |
|---|---|---|
| 2022Q2 | −$44,116 · RoR −22.4% · dd 95% | **−$25,924 · RoR −27.5% · dd 59%** |
| 2022Q3 | −$23,602 · RoR −8.1% · dd 63% | −$438 · RoR −0.5% · dd 21% |
| 2022Q4 | −$11,867 · RoR −4.2% · dd 52% | +$3,546 · RoR +3.6% · dd 7% |
| 2023Q2 | +$16,182 · RoR +5.6% · dd 15% | +$11,593 · RoR +12.3% · dd 6% |

Pooled across all four:

| config | n | win% | net | PF | RoR | L/W | max DD | +ve qtrs |
|---|---|---|---|---|---|---|---|---|
| 7-11 DTE, exit 2 | 475 | 58.9 | −$63,402 | 0.70 | −5.48% | 2.07 | $86,247 | 1/4 |
| 35-45 DTE, exit 10 | 162 | 58.0 | −$12,757 | 0.83 | −3.55% | 1.67 | $32,421 | 2/4 |
| 35-45 DTE, exit 15 | 166 | 56.6 | −$11,223 | 0.84 | −2.99% | 1.56 | $32,107 | 2/4 |

## Retraction

The prior commit called long DTE "the first configuration that does not invert
between regimes," based on Q2 2023 and Q4 2022. That was premature — those are
the two quarters where it happens to work. Q2 2022 is −$25,924 with a 59%
drawdown, which is not survivable at this sizing.

## What survives

Long DTE **strictly dominates** short DTE in every quarter on every metric:

- pooled loss $63,402 → $11,223 (82% smaller)
- max drawdown $86,247 → $32,107 (63% smaller)
- loss/win 2.07 → 1.56
- profit factor 0.70 → 0.84

That damage-reduction effect is consistent across all four quarters, including
the two where the strategy still loses. It is a real and useful finding about
tenor.

But **"loses less" is not "profitable."** Pooled RoR is −2.99% — negative
expectancy over a representative sample spanning a bear year and a bull
quarter.

## Why Q2 2022 kills it

A sustained grind with no recovery gives a 40-day spread no escape. The longer
tenor that helps in choppy or recovering markets becomes a liability when drift
is relentlessly down: win rate 31.7%, and the position has five more weeks of
exposure to a one-way tape. The mechanism that produces the edge elsewhere is
the same one that amplifies the damage here.

## Vol-of-vol gate

Still inert. Identical results at p70/p80/p90 in Q3; actively worse in Q2.
The trailing-percentile construction normalises away danger in a sustained
high-vol regime. A fixed threshold (the original "VVIX > 100" idea) would not
have that flaw, but there is no VVIX series in this dataset to calibrate
against. Unresolved rather than dismissed.

# Cryptocurrency statistical arbitrage

A local Python research project studying crypto momentum, reversal, transaction
costs and whether strategy selection generalizes across market periods. The
project contains the implementation, development/validation/OOS results and
**three final reports**.

## Main finding: performance did not persist across periods

The evidence is the **pattern across periods**, not the best isolated result.
Neither the basket-selection study nor the separate fixed all-22 studies
established a stable all-period edge. The two examples below show why.

### Example 1: the eight-coin basket study

The main study tested **6,615 different eight-coin baskets** within a historically
liquidity-ranked 22-coin universe. Each basket kept **BTC and ETH**, then selected
two coins from ranks **3–9**, two from **10–16**, and two from **17–22**. Signals
and weights were recomputed inside each basket; these are not slices of one
22-coin portfolio. The universe comes from the inherited historical top-30
inventory, not an unrestricted census of exchange listings.

Across these baskets, the study evaluated **169 strategy definitions** spanning
cross-sectional momentum, reversal, buffered momentum, time-series trend and a
fixed BTC-factor residual model. Four Track A strategies were selected using
development only; five Track B strategies used development eligibility and
validation. The nine frozen strategies use different eight-coin baskets, not one
common basket. Their combined membership covers 21 economic slots.

**All four development-selected strategies (A01–A04) lost money in 2024–2025
validation; all five validation-selected strategies (B01, B03–B06) lost money
in January–September 2026.** Track A's validation Sharpe ratios ranged from
−0.64 to −0.22 using √365, or −0.53 to −0.18 using √252.
Track B's January–September 2026 OOS Sharpe ratios ranged from −2.65 to +0.05
using √365, or −2.20 to +0.04 using √252.

This pattern is consistent with basket and parameter selection fitting each
period rather than identifying a stable edge. It does not prove search was the
only cause: market conditions, settings, cadence and execution assumptions also
matter. A03's strong 2026 result does not erase its validation loss. B06 lost
compounded wealth in 2026 despite a slightly positive arithmetic-return Sharpe.
No new OOS winner is selected, and these results do not establish a
deployment-ready strategy.

### Example 2: separate fixed all-22 studies

Two separate fixed studies each used all 22 eligible coins, a **28-day
lookback** and **weekly Monday rebalancing**, without a new basket or parameter
selection. Momentum and reversal were approved and evaluated separately.

| Fixed study | Period | Net return | Sharpe √365 | Sharpe √252 |
| --- | --- | ---: | ---: | ---: |
| Momentum | 2022–2023 development | +5.61% | 0.23 | 0.20 |
| Momentum | 2024–2025 validation | −17.43% | −0.38 | −0.31 |
| Momentum | Jan–Sep 2026 OOS (273 days) | −20.94% | −1.70 | −1.41 |
| Reversal | 2022–2023 development | −33.59% | −0.87 | −0.72 |
| Reversal | 2024–2025 validation | −15.66% | −0.32 | −0.27 |
| Reversal | Jan–Sep 2026 OOS (273 days) | +9.91% | 0.81 | 0.67 |

At the fixed **20 bps** primary cost, neither rule made money in all three
periods. Reversal's positive partial 2026 does not erase its earlier losses;
its development maximum drawdown was **43.69%**. These are descriptive
cross-period findings, not revised acceptance tests, a direction ranking or a
combined strategy. No isolated profitable period is promoted as a discovery.

All three periods had already been examined in the broader project, so these
additional studies are not fresh independent OOS confirmation. Momentum retains
a chronology exception: its seal preceded the first all-22 simulation but not
all input access by existing verification tests. Reversal met its new-study
pre-input-decode seal. Numerical reconciliation does not erase a procedural
exception.

## Periods and Sharpe conventions

| Period | Dates | Complete UTC days |
| --- | --- | ---: |
| Development | 1 January 2022–31 December 2023 | 730 |
| Validation | 1 January 2024–31 December 2025 | 731 |
| OOS evaluation | 1 January–30 September 2026 | 273 |

We report **two Sharpe annualization conventions: √365 and √252**. Both use the
same complete UTC daily strategy returns, including weekends, net of modeled
transaction costs, with sample standard deviation:

`S365 = sqrt(365) × mean(r) / std(r, ddof=1)`  
`S252 = S365 × sqrt(252/365)`

For example, A01's development Sharpe is **1.84 / 1.53** under √365 / √252.
Changing the annualization convention does not change the daily observations,
returns, rankings, t-statistics or p-values. CAGR, volatility and annual alpha
retain elapsed-calendar/365-day definitions. The 2026 interval is a partial year;
its annualized statistics are not realized full-year performance.

## Read the three reports

1. **Development and robustness — 2022–2023:** [PDF](final_reports/01_development/01_development_and_robustness.pdf) · [offline HTML](final_reports/01_development/01_development_and_robustness.html).
2. **Validation and frozen selection — 2024–2025:** [PDF](final_reports/02_validation/02_validation_and_frozen_selection.pdf) · [offline HTML](final_reports/02_validation/02_validation_and_frozen_selection.html).
3. **OOS evaluation and conclusions — January–September 2026:** [PDF](final_reports/03_2026_evaluation/03_2026_evaluation_and_conclusions.pdf) · [offline HTML](final_reports/03_2026_evaluation/03_2026_evaluation_and_conclusions.html).

The reports retain unsuccessful strategies and show returns, both Sharpe
conventions, CAGR, drawdowns and their duration, full-L1 turnover, exposure,
per-coin attribution, BTC-only and joint basket alpha/betas, and uncertainty.
Each also contains a clearly separate fixed all-22 study section. There are
exactly three final reports, not separate editions for each additional study.

## Run locally

Python 3.11 or newer is required. No cloud service, exchange account or API key
is needed.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python scripts/verify_project.py
python scripts/verify_fixed_all22.py
python -m pytest tests -q
python scripts/run_research.py
python scripts/reproduce_diagnostics.py
```

Verification uses the included evidence without acquiring prices. The research
runner reconstructs the nine frozen strategies and reconciles their **27 primary
strategy-period paths**. `--all-scenarios` runs the seven fixed cost/delay
scenarios per path; `--help` lists bounded strategy/period options. It does not
reselect candidates, place orders or repeat the full basket campaign. Outputs
go to `local_outputs/`. The fixed all-22 folders contain saved evidence and
raw-result verification, not a newly selected public execution strategy.

## Data sources and included dataset

Source: **Binance Data Vision spot-USDT one-hour bars**. The complete normalized
**22-instrument dataset** contains **43,824 UTC close endpoints**, from
**1 October 2021 at 01:00 UTC through 1 October 2026 at 00:00 UTC**, including
warm-up. The two fixed studies rank all 22 eligible members; the original nine
strategies each use eight. The initial 30-name inventory and explicit membership
flags are in the [universe table](data/universe.csv).

[Data documentation](docs/DATA.md) explains the original liquidity pool,
22 instruments, source archive URLs/checksums, token continuations, lifecycle
masks and suspensions. The bundle includes normalized close/quote-volume panels
and masks, not all raw OHLCV fields or ZIP archives.

| Folder | Contents |
| --- | --- |
| `src/` | Strategies, accounting, metrics and statistical diagnostics |
| `configs/` | 169 definitions, nine frozen strategies and periods |
| `data/` | Hourly panels, source catalogs, liquidity inventory and masks |
| `results/` | Performance, screening, attribution and fixed-study evidence |
| `final_reports/` | Three PDFs and their offline HTML counterparts |
| `scripts/` | Verification, research and diagnostic entry points |
| `tests/` | Strategy, accounting and numerical checks |
| `metadata/` | Package checksums and result contracts |

See [methods](docs/METHODS.md), the [fixed momentum specification](docs/FIXED_ALL22_PROTOCOL.md)
and [separate reversal specification](docs/FIXED_ALL22_REVERSAL_PROTOCOL.md).
Theoretical shorts, funding/borrow, margin, impact, capacity, realistic fills,
universe selection and prior data inspection limit interpretation.

## Attribution

Source: **Binance Data Vision (`data.binance.vision`)**. Data and derived artifacts
retain applicable **CC BY-NC-SA 4.0** conditions and non-commercial scope. See
[NOTICE](NOTICE.md) and the [dataset license](licenses/DATA_LICENSE.md). No
separate software license has been selected by the owner. Binance does not
endorse this project.

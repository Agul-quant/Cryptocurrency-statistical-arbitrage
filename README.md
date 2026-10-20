# Cryptocurrency statistical arbitrage

A local Python research project studying crypto momentum, reversal, transaction
costs and the reliability of strategy selection. This repository contains the
current development, validation and OOS results, their implementation, and
**three final reports**.

## Main finding: performance did not persist across periods

**All four development-selected strategies (A01–A04) lost money in 2024–2025
validation; all five validation-selected strategies (B01, B03–B06) lost money
in January–September 2026.** The A strategies' validation Sharpe ratios were
−0.22 to −0.64 using √365 (−0.18 to −0.53 using √252).

The pattern is consistent with basket and parameter selection fitting each
period rather than identifying a stable edge. It is not proof that search is
the sole cause: market conditions, strategy settings and execution assumptions
also matter. The development and validation selections largely share momentum,
reversal and trend families but differ in basket, lookback and sometimes cadence;
Track B also includes long/cash trend. A03's strong 2026 result does not erase
its validation loss. B06 lost compounded wealth in 2026 despite a slightly
positive raw arithmetic-return Sharpe. No new OOS winner is selected, and none
of these results establishes a deployment-ready strategy.

### Separate fixed all-22 studies also lacked persistence

To remove a new eight-coin basket and parameter selection, two **separate fixed
studies** each used all 22 coins, one 28-day lookback and weekly Monday
rebalancing. Momentum and reversal were approved and evaluated separately;
neither is a replacement selected from their outcomes.

| Fixed study | 2022–2023 net return | 2024–2025 net return | Jan–Sep 2026 net return |
| --- | ---: | ---: | ---: |
| Momentum | +5.61% | −17.43% | −20.94% |
| Reversal | −33.59% | −15.66% | +9.91% |

At the fixed **20 bps** primary cost, neither study had positive cash-relative
net return in all three periods. Momentum's positive development return was
still below the 3% nominal cash benchmark. Reversal's profitable partial 2026
had cash-excess HAC t **0.705**, with its own Holm3-adjusted **p = 0.6584**; it
also lost in both earlier periods and breached the development 40% drawdown
guardrail. No rule is promoted as a winner. Each study retains its own three
period tests; no pooled correction, correlation or combined portfolio is used.

These studies use already-examined historical dates, not new independent OOS
confirmation. **Momentum has a disclosed chronology exception:** its seal
preceded simulation but not all input access, because existing tests loaded
market panels/saved-result calculations beforehand. Reversal met its new-study
pre-input-decode seal. Both completed numerical audits; a numerical audit pass
is not a performance or procedural pass.

## Read the results

1. **Development and robustness — 2022–2023:** [PDF](final_reports/01_development/01_development_and_robustness.pdf) · [offline HTML](final_reports/01_development/01_development_and_robustness.html).
2. **Validation and frozen selection — 2024–2025:** [PDF](final_reports/02_validation/02_validation_and_frozen_selection.pdf) · [offline HTML](final_reports/02_validation/02_validation_and_frozen_selection.html).
3. **OOS evaluation and conclusions — January–September 2026:** [PDF](final_reports/03_2026_evaluation/03_2026_evaluation_and_conclusions.pdf) · [offline HTML](final_reports/03_2026_evaluation/03_2026_evaluation_and_conclusions.html).

The nine frozen strategies are compared over all three periods. Each report also
contains a clearly separate fixed all-22 study section, retaining all three
periods and highlighting its own period-specific results. Reports include
returns, Sharpe, drawdowns, full-L1 turnover, per-coin contribution intervals,
and BTC-only and joint eight-coin alpha/betas. All nine frozen strategies,
including validation and OOS failures, remain in the period results; broader
screening summaries provide context. No strategy is
approved for deployment and no new winner is selected from OOS results.

## Run locally

Python 3.11 or newer is required. No cloud service, exchange account or API key
is needed. After installing dependencies:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python scripts/verify_project.py
python scripts/verify_fixed_all22.py
python -m pytest tests -q
python scripts/run_research.py
python scripts/reproduce_diagnostics.py
python scripts/reproduce_cash_excess.py
```

Verification uses only the standard library. Research execution uses the included normalized hourly panels; it does not acquire market prices,
place orders or reselect strategies. The research runner reconciles 27 primary
strategy-period paths. Use `--all-scenarios` for the seven fixed cost/delay
scenarios per path; use `--help` for bounded strategy/period options. Generated
checks go to `local_outputs/`, not into the checked research results.

## Package layout

| Folder | Contents |
| --- | --- |
| `src/` | Python strategies, accounting, metrics and statistical diagnostics |
| `configs/` | The 169 configuration definitions, nine frozen strategies and evaluation periods |
| `data/` | Complete 22-instrument normalized hourly search inputs, liquidity inventory, source catalogs and lifecycle/decision masks |
| `results/` | Current performance, screening and explanatory results, plus compact statistical inputs |
| `final_reports/` | Three PDF reports and their fully offline HTML editions |
| `scripts/` | Current verification, research execution and diagnostic reproduction entry points |
| `tests/` | Strategy, accounting and numerical checks |
| `metadata/` | Current package file checksums and result contracts |

## Cash benchmark comparison

The reports also compare all nine fixed strategies with **3% nominal annual
cash, compounded daily on ACT/365F**. This is a hypothetical benchmark in
USDT-quoted units, not interest credited to strategy P&L or an actual investment
yield. Original zero-cash Sharpe ratios and raw returns remain unchanged.
The main nine-strategy period tables show raw and cash-excess performance
side by side; supporting cash tables provide uncertainty, daily relative
drawdowns and cash-adjusted alpha. See the
[cash-comparison methods](docs/METHODS.md#cash-benchmark-comparison).

## Data sources and included dataset

Source: **Binance Vision, Binance spot USDT, one-hour bars**. The complete
normalized **22-instrument search dataset** is included, with **43,824 UTC
endpoints per panel**, from 1 October 2021 at 01:00 UTC to 1 October 2026 at
00:00 UTC. Each original frozen strategy uses eight coins; those nine together use 21.
The separate fixed momentum and reversal studies use all 22 eligible slots,
including SAND, and recompute ranks across that full cross-section.
The initial 30-name historical liquidity ranking and explicit 22/21 membership
flags are included in the [universe inventory](data/universe.csv).

[Data sources, full coverage and field definitions](docs/DATA.md) explain the
22 instruments, original 757-directory/259-eligible liquidity screen, archive
URLs/checksums, token continuations and suspension treatment. The bundle
contains normalized close/quote-volume panels and masks—not all raw OHLCV
fields or raw ZIP archives. Source catalogs identify the verified originals.

The supplied runner reproduces the nine frozen strategies and reconciles their
27 primary strategy-period paths. It does not rerun the complete basket-selection
campaign; supporting screening and cohort tables are saved research results.

See [methods and interpretation](docs/METHODS.md) for costs, sample boundaries,
statistical intervals, data-use limitations and reproduction scope.

## Sharpe conventions and completed fixed studies

The reports show **√365 and course-convention √252 Sharpe side by side**, for
both raw and cash-excess returns. They use the same complete UTC daily series,
including weekends: `S252 = S365 × sqrt(252/365)`. A01's development raw Sharpe
is therefore **1.84 / 1.53**. This is a display-scale comparison, not a change
to returns, cash accrual, CAGR, alpha, inference or the frozen acceptance tests.

The [fixed momentum protocol](docs/FIXED_ALL22_PROTOCOL.md) and
[separate fixed reversal protocol](docs/FIXED_ALL22_REVERSAL_PROTOCOL.md) record
the completed 28-day weekly studies and their limitations. Saved results,
scenario tables, daily paths and uncertainty are under
[`results/fixed_all22_momentum`](results/fixed_all22_momentum) and
[`results/fixed_all22_reversal`](results/fixed_all22_reversal). Their results
are integrated into the existing three reports, **not a fourth report**. The
supplied execution runner remains limited to the original nine strategies;
this publication adds saved fixed-study evidence without rerunning any strategy.

## Attribution

Source: **Binance Vision (`data.binance.vision`)**. Data and derived artifacts
retain applicable **CC BY-NC-SA 4.0** conditions and non-commercial scope. See
[NOTICE](NOTICE.md) and [dataset license](licenses/DATA_LICENSE.md). No separate
software license has been selected by the owner. This project is not endorsed
by Binance.

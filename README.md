# Cryptocurrency statistical arbitrage

A local Python research project studying crypto momentum, reversal, transaction
costs and the reliability of strategy selection. This repository contains the
current development, validation and OOS results, their implementation, and
**three final reports**.

## Read the results

1. **Development and robustness — 2022–2023:** [PDF](final_reports/01_development/01_development_and_robustness.pdf) · [offline HTML](final_reports/01_development/01_development_and_robustness.html).
2. **Validation and frozen selection — 2024–2025:** [PDF](final_reports/02_validation/02_validation_and_frozen_selection.pdf) · [offline HTML](final_reports/02_validation/02_validation_and_frozen_selection.html).
3. **OOS evaluation and conclusions — January–September 2026:** [PDF](final_reports/03_2026_evaluation/03_2026_evaluation_and_conclusions.pdf) · [offline HTML](final_reports/03_2026_evaluation/03_2026_evaluation_and_conclusions.html).

The nine frozen strategies are compared over all three periods. Reports include
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
python -m pytest tests -q
python scripts/run_research.py
python scripts/reproduce_diagnostics.py
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

## Data sources and included dataset

Source: **Binance Vision, Binance spot USDT, one-hour bars**. The complete
normalized **22-instrument search dataset** is included, with **43,824 UTC
endpoints per panel**, from 1 October 2021 at 01:00 UTC to 1 October 2026 at
00:00 UTC. Each strategy uses eight coins; the frozen nine together use 21.
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

## Attribution

Source: **Binance Vision (`data.binance.vision`)**. Data and derived artifacts
retain applicable **CC BY-NC-SA 4.0** conditions and non-commercial scope. See
[NOTICE](NOTICE.md) and [dataset license](licenses/DATA_LICENSE.md). No separate
software license has been selected by the owner. This project is not endorsed
by Binance.

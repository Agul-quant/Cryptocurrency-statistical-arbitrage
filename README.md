# Cryptocurrency statistical arbitrage

A standalone Python research project investigating crypto momentum, reversal,
transaction costs, and the limits of apparent backtest profitability. All
calculations run on your computer. No Codex/ChatGPT, cloud notebook, account,
exchange API key, live order, scheduled monitor, or Git LFS service is required.

## Final reading list — three consolidated reports

The current dated edition adds **per-coin contribution intervals and a joint
eight-coin alpha/beta model** for all nine unchanged frozen strategies in all
three periods. Exactly three report titles remain the primary reading list:

1. **Development and robustness** — [PDF](final_reports_20261016/01_development/01_development_and_robustness.pdf) · [offline HTML](final_reports_20261016/01_development/01_development_and_robustness.html).
2. **Validation and frozen selection** — [PDF](final_reports_20261016/02_validation/02_validation_and_frozen_selection.pdf) · [offline HTML](final_reports_20261016/02_validation/02_validation_and_frozen_selection.html).
3. **2026 evaluation and conclusions** — [PDF](final_reports_20261016/03_2026_evaluation/03_2026_evaluation_and_conclusions.pdf) · [offline HTML](final_reports_20261016/03_2026_evaluation/03_2026_evaluation_and_conclusions.html).

These are post-hoc explanatory diagnostics, not new OOS results, causal effects
or a new winner. Original returns, Sharpe, turnover, drawdowns and selections
are unchanged. See the [publication/reproduction guide](docs/ATTRIBUTION_PUBLICATION.md).

The [prior edition](final_reports_20261015/README.md) remains unchanged as
archival version history of the same three reports, not a fourth report.

## Earlier reports (archival)

- **Original course study, with the new universe story:**
  [Revised PDF](studies/crypto_stat_arb_report_revision/reports/project_report.pdf).
  Page 2 explains the eight-coin choice and the absence of a documented larger
  screening pool.
- [Original frozen report](studies/crypto_stat_arb/reports/project_report.pdf)
  and [executed notebook](studies/crypto_stat_arb/notebooks/crypto_stat_arb_research.ipynb).
- [Expanded hourly report](studies/crypto_stat_arb_extensions/reports/expanded_research_report.pdf)
  and [executed notebook](studies/crypto_stat_arb_extensions/notebooks/expanded_crypto_research.ipynb).
- [Five-minute pilot report](studies/crypto_intraday_5m/reports/intraday_5m_report.pdf)
  and [executed notebook](studies/crypto_intraday_5m/notebooks/intraday_5m_research.ipynb).
- [Research chronology and interpretation](docs/RESEARCH_STORY.md).

The PDFs can be read offline without installing Python. Historical executed
notebook outputs are included; PDF remains the fully offline reading format.

## Local setup

Python **3.11 or newer** is required. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python scripts/local_project.py restore
python scripts/local_project.py verify
python scripts/local_project.py test
python -m pytest tests -q
```

On the originating machine, the existing environment can be used instead:

```bash
~/.venvs/myenv/bin/python scripts/local_project.py restore
~/.venvs/myenv/bin/python scripts/local_project.py verify
~/.venvs/myenv/bin/python scripts/local_project.py test
```

Installation downloads Python packages once; research execution is local. After
dependencies and the included data are available, the documented verification,
tests and notebook commands do not acquire market prices or contact a trading
service. Run `python scripts/local_project.py --help` for available commands.
New notebook executions go to `local_outputs/`, not into the frozen studies.

```bash
python scripts/local_project.py notebooks --execute
```

This executes the original, expanded-hourly and five-minute notebooks in private
temporary study copies. Add `--notebook all` to include the time-scale notebook.

The portable test command explicitly skips two legacy tests that require the
originating host's external original-project ZIPs. It does not weaken or skip
strategy arithmetic, chronology, data-boundary or frozen-source tests. Local
study preservation is checked separately by the snapshot hashes; external ZIP
preservation remains a historical recorded check, not a new portable assertion.
The revised report can also be rebuilt without legacy host paths:

```bash
python scripts/rebuild_universe_report.py
```

## What is included

| Folder | Research scope |
| --- | --- |
| `studies/crypto_stat_arb/` | Original 18-configuration hourly study, plus preserved follow-ups including the 156-configuration time-scale scan |
| `studies/crypto_stat_arb_extensions/` | Diagnostics, lower-turnover momentum, time-series trend, fixed BTC-factor residual reversal, regimes and frozen 2026 evaluation |
| `studies/crypto_intraday_5m/` | Actual five-minute candles; 18 configurations and all 504 configuration-period-cost/delay results |
| `studies/crypto_stat_arb_report_revision/` | Revised nine-page original-project report, universe narrative and its builder |
| `provenance/` | Exact study file hashes, lossless-data-part hashes, and packaging checks |
| `scripts/` | Portable local verification, restoration, tests and notebook execution |

The research folders are byte-identical copies, excluding scratch/cache files.
No candidate, strategy selection, threshold, trade rule, price, cost scenario or
historical freeze receipt was changed for this release. Original host paths in
legacy receipts and sources are preserved as historical provenance; they are
**not prerequisites for the root-level local commands**. Do not use the
host-specific legacy preservation commands as portable entry points.

### Large files and raw caches

The two five-minute Parquet files exceed normal GitHub file limits. Their exact
bytes are supplied as checksum-pinned 32 MiB parts under `data_parts/`.
`restore` concatenates and verifies them; this is not interpolation, data
resampling, cloud computation or a Git LFS download. The restored large files
are ignored by Git. The snapshot has **no runtime dependence on GitHub**.

The ordinary Git checkout includes hourly raw archives needed by the frozen
extension audit. The five-minute raw ZIP/checksum cache is omitted from Git to
avoid duplicating the included normalized five-minute inputs. Its original
manifest and checksums are recorded; optional missing raw-cache files are
reported explicitly by `verify`. The separate **full local archive** retains
those raw files as well as restored Parquets, and does not duplicate their
`data_parts/` storage. Neither distribution includes the private course DOCX
or the original project ZIPs. No historical claims about those original ZIPs
are upgraded into a new verification of ZIPs that are not distributed.
The original study's historical `.gitignore` is preserved; its locked input
data are explicitly tracked in this release so that ignore rule does not omit
required offline evidence.

## Findings and boundaries

- The original selected hourly strategies lost money at the prescribed 20 bps
  in their initial 2025 test. Unsuccessful configurations remain in the results.
- The wider time-scale search was designed after those 2025 results had been
  seen; its 2025 evaluation is exploratory, despite choosing parameters on 2024.
- The preserved 28-day-lookback weekly reversal reference returned **17.11% net
  at 20 bps** in January-September 2026: Sharpe **1.53**, annualized nine-month
  CAGR **23.51%**, hourly maximum drawdown **8.87%**. It was not selected using
  that 2026 return. Highlighting the best observed holdout model still creates
  winner-focus bias; this is not a recommendation or a live record.
- The five-minute pilot did not establish net profitability at the primary
  20 bps cost. Its 2026 period reused already-inspected history and is not fresh
  independent confirmation.

The fixed BTC/ETH/LTC/ADA/LINK/DOGE/DOT/SOL survivor universe, theoretical shorts,
USDT numeraire, unmodeled borrow/funding/margin/capacity, idealized close fills,
omitted weight-drift trading, multiple comparisons and short evaluation windows
limit inference. CAGR annualizes the measured period rather than predicting a
future annual return. No live trading functionality is supplied.

## Attribution and permitted use

Source: **Binance Vision (`data.binance.vision`)**. Dataset-derived prices,
results, figures, reports and analytical derivatives retain **CC BY-NC-SA 4.0**
attribution and conditions, including non-commercial scope. See
[NOTICE](NOTICE.md), [dataset license](licenses/DATA_LICENSE.md), and the
[official dataset terms](https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md).
This project is not endorsed by Binance. No separate software license has been
chosen by the repository owner; public availability is not a new MIT/Apache
license grant for the software. Third-party Python packages retain their own
licenses.

Changes to the frozen experiments should be made in a separate research folder
with honest exploratory labeling and further unexamined or prospective data,
not by rewriting historical freeze receipts.

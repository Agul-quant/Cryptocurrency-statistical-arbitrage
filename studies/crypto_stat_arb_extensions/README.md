# Expanded crypto strategy research

This is an isolated, non-commercial educational extension of the completed
crypto course project. It preserves the original project, report, notebook,
existing 156-configuration time-scale scan, and original ZIP. Exact copies of
the original pure backtest/data/metrics APIs and elapsed-time schedule are
vendored here for reproducibility; their original files are unchanged.

## Deliverables

- `reports/expanded_research_report.pdf`: supplementary research report.
- `notebooks/expanded_crypto_research.ipynb`: executed, explained notebook.
- `notebooks/expanded_crypto_research.html`: readable notebook preview.
- `outputs/historical_metrics.csv`: all 17 configurations in development,
  validation, and retrospective research periods, including failures.
- `outputs/holdout_metrics.csv`: eight frozen models across cost/delay scenarios.
- `outputs/selection.json` and `outputs/freeze_receipt.json`: validation-only
  selections, immutable evidence, and the pre-access research freeze.
- `outputs/holdout_access_receipt.json`: first permitted 2026 acquisition,
  followed by checksum/coverage and historical-prefix reconciliation.
- `outputs/run_manifest.json`: exact inputs, outputs, code, chronology,
  versions, attribution, and limitations.
- `outputs/ic_summary.csv`, `outputs/regime_summary.csv`, and
  `outputs/factor_models.csv`: predictive diagnostics, conditional outcomes,
  and every monthly factor-model eligibility decision.

## Reproduce on this host

Run from this project directory using the requested virtual environment:

```bash
/Users/cosdis/.venvs/myenv/bin/pip install -e . --no-deps --no-build-isolation
/Users/cosdis/.venvs/myenv/bin/python -m pytest -q
/Users/cosdis/.venvs/myenv/bin/python -m crypto_stat_arb_extensions verify
/Users/cosdis/.venvs/myenv/bin/python -m crypto_stat_arb_extensions report
```

For a new environment, install the versions in `requirements.lock.txt` first.
The local preservation check needs the original project at its captured path;
the saved snapshot and vendored dependency hashes remain inspectable elsewhere.
The executed notebook independently reproduces portfolio accounting from the
bundled data and holdings. No original-project installation is needed for the
vendored computational APIs.

The ordered commands are `prepare-history`, `screen`, `freeze`, `evaluate`,
`report`, and `all`, with optional `--root /absolute/project/path`. A completed
`evaluate` invocation verifies and reuses locked results rather than generating
new selections. Original pre-access receipts are never reset on reruns.

**Do not edit the frozen configuration or analysis source and reuse this
holdout as if it were unseen.** The runner rejects changed analysis hashes or
evidence. Reporting appearance and new independent verification tests can be
updated without changing trading decisions; their final hashes are recorded
separately.

## Chronology and evaluation

- Eight fixed Binance spot USDT pairs: BTC, ETH, LTC, ADA, LINK, DOGE, DOT, SOL.
- October–December 2021 warms the extended windows.
- Development: 2022–2023. Selection: 2024. Retrospective robustness: 2025.
- These historical extensions are exploratory because those years were already
  inspected. They are not relabeled as new independent tests.
- After candidate/code/threshold/selection freeze, January–September 2026 is
  acquired and evaluated once. Returns cover `(2026-01-01, 2026-10-01]`, or
  **273 complete UTC interval-days / 6,552 hours**. This is new-to-analysis
  historical data, not prospective paper trading or full-year 2026 performance.
- Raw archives are SHA256 verified. Full-data historical close and quote-volume
  panels must exactly equal the frozen historical prefix.
- Missing archives, invalid schemas, unknown gaps, and checksum failures stop
  evaluation rather than shorten the period or fill prices.

## Seventeen bounded candidates

1. Cross-sectional momentum: 14/28-day lookback × daily/weekly rebalance ×
   buffer 0/0.25 = eight configurations. Four plain versions already existed
   in the exploratory scale scan; they are matched-period controls, not new
   discoveries. The whole rebalance is skipped only below full-L1 change 0.25.
2. Time-series trend: the same two horizons and two cadences, separately for
   long/cash and theoretical long/short = eight configurations. Each coin has
   a fixed 1/8 allocation; inactive names are not rescaled.
3. One fixed BTC-factor residual-spread reversal model. Monthly 90-day formation
   ends 24 hours before refitting: earliest 30 daily return observations estimate
   beta, the following 60 price-level spread endpoints calibrate/screen it.
   Monthly coefficients, sample mean, and sample standard deviation remain
   fixed. ADF constant/AIC/maxlag3 plus Holm across seven assets, beta bounds,
   and AR(1) half-life gates can legitimately leave the model entirely in cash.

The factor spread is `log(Pcoin) - beta*log(PBTC)`, not cumulative demeaned
return residuals. Fixed 1/7 spread budgets include the actual BTC hedge;
aggregate BTC positions before computing turnover and fees. Entry is at
`2 <= |z| < 4`, mean-crossing exit at the appropriate ±0.5 boundary, adverse
stop at ±4, and maximum holding 20 calendar days. Decisions/stops occur at
daily observed closes, not guaranteed intraday fills. Monthly refit day is cash,
entries resume the next day, and same-day exit/reentry is forbidden. No
formation gate is relaxed after examining holdout outcomes.

Three tuned-family champions use highest defined 2024 net daily Sharpe at
20 bps; ties favor lower turnover then fixed ID. The fixed factor model and
four saved references (two original and two scale-scan selections made at
20 bps) complete the eight evaluated models. 2025 never determines these
selections. A negative champion is a control, not a profitable recommendation.

## Diagnostics and metrics

- Daily cross-sectional Spearman rank-IC uses eight trailing-return horizons
  and three forward horizons, with complete date grids, tied ranks, audited
  halt endpoint exclusions, and no labels crossing a period boundary.
- Confidence intervals use 4,000 seeded circular 28-calendar-day bootstrap
  samples shared across hypothesis cells. Holm adjustment counts 24 IC tests
  within each period. Inference is nominal and does not erase prior searches
  or strategy-selection optimism.
- Volume, 30-day BTC volatility, and 24-hour return dispersion thresholds are
  development medians. Decision-time features label the *next* daily outcome.
  High/low/unknown strata retain counts, conditional gross/net means and
  turnover. Net high-minus-low contrasts receive within-period Holm correction.
  Regimes never filter trading; no discontinuous-stratum annualized Sharpe is
  presented.
- Primary costs are 20 bps per full one-way L1 target change, including cash
  entry and final liquidation. 0/5/10/15/40 bps are hypothetical sensitivities;
  20 bps with an additional hourly execution lag is a robustness scenario.
- Daily compounded returns drive 365-day annualized volatility, arithmetic
  mean return, and Sharpe (risk-free zero). CAGR uses actual elapsed duration;
  total return, CAGR, and arithmetic annual return are distinct. BTC alpha/beta
  uses daily OLS with HAC(7) confidence intervals. Flat zero-return portfolios
  have zero volatility and undefined Sharpe, not invented Sharpe zero.
- Exposure/cash participation accompany returns: directional trend, dollar-
  neutral rank momentum, and factor-hedged spreads have different risk profiles.
  Dollar neutrality does not establish market-beta neutrality.

## Data exception and limitations

The original March 24, 2023 spot suspension remains an explicit observed
11:00→15:00 UTC bridge: retain holdings, earn the real endpoint price move once,
do not execute or fabricate intermediate marks. One all-asset missing hour
remains absent. Sixteen original close-time metadata anomalies retain their
exact prior policy; a single SOL metadata-only repair is supported by an
official daily archive. Unknown exceptions remain fatal. The halt is in
development, not the 2026 holdout. Drawdown within unobserved intervals is
unknown. See each dataset's `data/processed/data_quality.json`.

This is a purposive survivor universe, not a point-in-time crypto market.
USDT differs from USD. Shorts are theoretical; borrow, funding, margin,
capacity and liquidation are excluded. Course target-weight turnover ignores
ordinary weight drift, and close execution is idealized. Five bps all-in cost
is below the course's approximate seven-bps commission assumption. Source
archives may contain later revisions; current retrieval does not demonstrate
original timestamp availability. Formation tests are limited-sample screening
diagnostics, not proof of cointegration or a causal explanation of profitability.

## Attribution and license

Source: **Binance Vision (`data.binance.vision`)**.
[Source documentation](https://github.com/binance/binance-public-data) and
[dataset terms](https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md).
Dataset-derived results, charts and redistributed derivatives retain
**CC BY-NC-SA 4.0**, attribution and non-commercial educational/research
conditions. No live orders, external publication or scheduled monitoring is
performed by this project.

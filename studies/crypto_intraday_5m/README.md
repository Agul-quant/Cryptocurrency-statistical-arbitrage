# Five-minute crypto momentum/reversal pilot

An isolated educational experiment using **actual Binance 5-minute candles**,
not interpolated hourly prices. Neither completed hourly project nor either
original project ZIP is modified.

## Scope and chronology

- Eight fixed spot USDT pairs: BTC, ETH, LTC, ADA, LINK, DOGE, DOT, SOL.
- Monthly archives: December 2021–September 2026. December is warm-up only.
- Momentum/reversal × 5/15/30-minute lookbacks × 5/15/60-minute rebalancing:
  **18 configurations**.
- Development: 2022–2023. Selection: 2024. Retrospective: 2025 and
  January–September 2026. **All periods are exploratory/retrospective** because
  their coarser-frequency outcomes were already examined. No fresh independent
  holdout or prospective trading claim is made.
- One model per family is chosen exclusively by defined 2024 daily Sharpe at
  20 bps, ties lower turnover then canonical ID. Negative choices remain controls.
- All 18 configurations, four periods and seven cost/delay scenarios are retained
  in `outputs/experiments.csv` (504 measurements), not just favorable outcomes.
- `outputs/protocol.json` records the fixed grid before strategy calculations.
  Source inspection was already underway; this is not data-naive preregistration.
  Implementation IDs use `_m` while declaration IDs use `_l`; their identical
  parameter mapping is explicitly recorded in `protocol_alignment.json`.

## Reproduce

Run from this directory using the requested environment:

```bash
/Users/cosdis/.venvs/myenv/bin/pip install -e . --no-deps --no-build-isolation
/Users/cosdis/.venvs/myenv/bin/python -m pytest -q
/Users/cosdis/.venvs/myenv/bin/python -m crypto_intraday_5m verify
/Users/cosdis/.venvs/myenv/bin/python -m crypto_intraday_5m report
```

For a new environment, first install `requirements.lock.txt`. Commands are
`download`, `run`, `verify`, `report`, `all`, with optional `--root /absolute/path`.
`run` uses audited cached prices only. Completed results require unchanged
analysis code/config and output fingerprints; a matching rerun reuses them.
Use a different experiment folder for changed trading rules. Report styling
and independent verification tests do not change trading decisions.

The current-host preservation check requires both captured original projects;
their snapshot hashes and ZIP hashes remain inspectable when copied elsewhere.

## Accounting and numerical precision

Rank, demean and L1 normalize trailing price-ratio returns across assets; reversal
negates the score. Net dollar exposure is zero; gross exposure is one unless all
ranks tie. Only targets carry forward, never missing prices.

Lag one means a completed-bar signal earns the next 5-minute interval under an
idealized observed-close fill. Lag two adds five minutes of delay. Twenty bps is
charged per **full one-way L1 target change**, including initial cash entry and
terminal liquidation, regardless of bar length. Costs 0/5/10/15/40 bps are
hypothetical sensitivities. Five bps is below the course's approximate seven-bps
commission alone; smaller bars do not make fees smaller. Ordinary weight drift
is not charged, matching the course convention. Cached asset-return matrices
are a trusted internal optimization: compute them with `observed_asset_returns`
from the same audited price panel; structural checks do not certify arbitrary
user-supplied economic values.

Daily P&L covers exactly **1,440 elapsed minutes**, normally 288 observations,
and is compounded before 365-day Sharpe/volatility/annual arithmetic metrics.
CAGR uses actual elapsed duration. BTC alpha/beta uses daily OLS and HAC(7)
confidence intervals. Maximum drawdown includes initial wealth one.

High-cost, high-turnover paths can make displayed double-precision equity
underflow to zero although every interval has return greater than −1. We retain
finite cumulative `log_equity`, calculate CAGR/drawdown from it, and record
`terminal_log_equity` and `equity_underflow_count`. No epsilon floor or false
insolvency is inserted. Total returns may round to −100%; logarithmic wealth
distinguishes remaining-capital magnitudes. Arithmetic annual means are not
realized one-year returns and can have magnitudes greater than 100%.

## Data audit and disagreements

- 464 monthly ZIPs and checksums, approximately 178.7 MB compressed.
- 4,066,432 observed asset-bar rows of 4,066,560 expected; complete calendar
  panel 508,320 × 8. The only absent cells are the documented halt below.
- Spot timestamp units are milliseconds before January 2025 and microseconds
  afterward. Unknown duplicates, gaps, nonfinite prices and malformed rows fail.
- Sixteen exact raw close-time anomalies retain a sourced policy: one SOL
  December 24, 2021 timestamp is repaired using an official 5-minute daily
  archive, changing **only close_time**; 15 shortened timestamps are warnings.

The March 24, 2023 halt is independently audited at minute resolution. Last
complete pre-halt endpoint **11:25 UTC**, first complete resumed endpoint
**14:05 UTC**: one 160-minute observed interval. Sixteen missing endpoints
12:45–14:00 remain NaNs across all assets. Other partial/zero-trade interior
source bars remain in raw data but are not valuation or execution endpoints.
Hold positions across the suspension and book the actual endpoint price ratio
once; no anticipatory cash-out, fictional marks or price filling. Intra-halt
drawdown is unknown. The suspension day still covers 1,440 elapsed minutes.

Independent hourly reconciliation found **zero close/volume discrepancies in
the evaluated January 2022–September 2026 window**. December 2021 retains three
close and 134 quote-volume-sum disagreements between selected monthly 5-minute
and preserved hourly sources. Official daily 5-minute files corroborate the
hourly close values at the three divergent points. No price/volume replacement
is made: these discrepancies are before December 28 and cannot affect January
1 evaluation with lookbacks ≤30 minutes, rebalance ≤60 minutes and lag ≤2 bars.
Receipts document both agreements and disagreements; do not claim full exact
cross-frequency agreement. Candle agreement also does not establish identical
portfolio compounding at different observation frequencies.

## Deliverables

- `reports/intraday_5m_report.pdf`: findings, all-case screens, selected paths,
  costs, numerical precision, source quality and limitations.
- `notebooks/intraday_5m_research.ipynb` and HTML: executed explanation and
  independent holdings/P&L/cost/daily-metric reconciliation.
- `outputs/selection.json`, `run_manifest.json`, `result_verification.json`:
  selections, code/input/output fingerprints and independent checks.
- `outputs/preservation.json`: both prior projects and prior ZIPs protected.
- `data/processed/data_quality.json`, `outputs/data_*`: source audit and
  independently documented granular halt/warm-up disagreement policies.

## Interpretation and licensing

Faster candles can expose short-lived patterns but OHLCV is not bid/ask,
order-book or fill data. Apparent reversal can be affected by microstructure;
zero-cost profit is not executable profit. The fixed survivor universe, USDT
quote, theoretical shorts, unmodeled borrow/funding/margin/capacity, idealized
close fills and omitted drift turnover limit real-world conclusions.

Source: **Binance Vision (`data.binance.vision`)**.
[Official documentation](https://github.com/binance/binance-public-data),
[dataset terms](https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md),
[documented halt](https://www.binance.com/en/blog/from-our-ceo/6789340645608890113).
Dataset-derived results/charts/derivatives retain attribution and **CC BY-NC-SA
4.0**, non-commercial educational/research conditions. No live orders,
publication, monitoring or scheduled jobs are performed.

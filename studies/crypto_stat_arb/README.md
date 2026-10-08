# Crypto momentum and reversal course research

This project tests 18 predeclared cross-sectional momentum/reversal configurations on eight Binance spot USDT pairs. It follows the course's idealized long-short convention, includes the assigned 20 bps market-order cost, freezes selections using 2024 validation, and evaluates 2025 without parameter reselection. This is educational research, not a live trading system or an investment recommendation.

## Start here

- `reports/project_report.pdf`: concise research report, required performance metrics, figures, and limitations.
- `notebooks/crypto_stat_arb_research.ipynb`: executed explanation and independent reproduction of frozen 2025 results.
- `outputs/final_metrics.csv`: exact gross/net performance, cost/delay scenarios, and BTC alpha/beta.
- `outputs/experiments.csv`: every baseline development/validation result, including unsuccessful tests.
- `outputs/selection.json`: persisted pre-test selection receipt.
- `outputs/run_manifest.json`: timestamps, input/code fingerprints, and library versions.

## Main result

No configuration had positive net validation performance at the required 20 bps cost. The least-negative validation configuration in each family was still evaluated in the untouched 2025 test, not presented as a profitable candidate:

| Frozen configuration | 2025 gross total return | 2025 net total return | Net Sharpe | Maximum drawdown |
| --- | ---: | ---: | ---: | ---: |
| Momentum: 168-hour lookback, daily rebalance | -11.32% | -40.38% | -2.75 | 42.60% |
| Reversal: 1-hour lookback, daily rebalance | +7.85% | -57.72% | -4.43 | 59.02% |

The combination was correctly omitted because both families failed the positive-net-validation gate. Reversal's gross test gain did not survive turnover costs. These negative findings complete the course research question; they do not establish that every possible crypto momentum/reversal strategy is unprofitable.

## Reproduce

The existing environment is `/Users/cosdis/.venvs/myenv/bin/python`. Run commands from this project directory:

```bash
/Users/cosdis/.venvs/myenv/bin/pip install -e . --no-deps --no-build-isolation
/Users/cosdis/.venvs/myenv/bin/python -m pytest -q
/Users/cosdis/.venvs/myenv/bin/python -m crypto_stat_arb download
/Users/cosdis/.venvs/myenv/bin/python -m crypto_stat_arb run
/Users/cosdis/.venvs/myenv/bin/python -m crypto_stat_arb report
```

`download` verifies cached SHA256 checksums and resumes missing archives; it does not contact a trading API. `run` uses only cached verified data. `report` executes the notebook and builds the PDF from saved results. `all` performs the three stages in that order. Use `--root /absolute/project/path` to choose another project location and `--config /absolute/config/path` to choose a configuration.

For a fresh environment, install the direct versions in `requirements.lock.txt` before installing the package. The delivered manifest records the actual execution environment. Re-running unchanged inputs retains the original frozen selection timestamp. A mismatch in configuration, validation evidence, or selected parameters is an error rather than an automatic overwrite of the receipt.

## Research design

Pairs: BTC, ETH, LTC, ADA, LINK, DOGE, DOT, SOL against USDT. December 2021 warms indicators. Development: 2022-2023; validation: 2024; final test: 2025. Momentum lookbacks: 24/72/168 hours; reversal lookbacks: 1/4/12 hours. Both use rebalance intervals of 1/4/24 hours, phased to UTC midnight.

Signals are trailing price-ratio returns, negated for reversal. Rank, demean, and L1 normalize to gross exposure one and net exposure zero; ties produce a flat portfolio. A completed-bar signal earns a subsequent interval's return. Total one-way L1 target changes, including entry and terminal liquidation, cost 20 bps. The additional-hour execution delay and 0/40 bps scenarios evaluate the same frozen selections without reselection. Optional 50/50 combination requires positive validation net performance in both families; its turnover comes from combined positions.

All reported Sharpe/volatility/arithmetic annual return statistics use compounded UTC daily returns and 365-day annualization, with zero risk-free return. CAGR uses actual elapsed duration. Maximum drawdown uses compounded observed-endpoint wealth from initial equity one. Alpha is the daily regression intercept times 365; beta is against BTC/USDT, with 95% HAC(7) confidence intervals. Arithmetic annual return, CAGR, and total return are different quantities and are labeled separately.

Relative-volume diagnostics use current completed-hour quote volume divided by strictly preceding 168-hour average volume, averaged across the fixed universe. The high/low threshold is the development median. Unknown regimes are retained when missing source volume prevents a full denominator; they are not replaced with stale activity. Conditional means are descriptive, not a new selected trading rule.

## Data integrity and the documented trading halt

Source: [Binance Vision public archives](https://github.com/binance/binance-public-data). There are 392 monthly ZIP/checksum pairs (December 2021-December 2025), roughly 14.4 MB compressed. Spot timestamps switch from milliseconds to microseconds in January 2025. Original archives remain unchanged under `data/raw`; normalized prices and quote volume are in `data/processed/bars.parquet` with a detailed SHA256/coverage audit.

The source genuinely lacks one hour for all eight pairs on March 24, 2023. [Binance's official explanation](https://www.binance.com/en/blog/from-our-ceo/6789340645608890113) records a spot halt from 11:27 UTC, with trading resuming at 14:00. Same-venue daily archives confirm the missing hour, so it cannot be repaired from an actual candle.

The backtest therefore uses one explicit observed interval from the last normal close at 11:00 to the first complete post-resumption close at 15:00. It retains invested positions and books the cumulative real price move once, prohibits executions during the interval, and does not fabricate prices, infer sub-hour returns, delete the day, or anticipate the halt by moving to cash. The interval covers four elapsed hours with one return observation. Drawdown within the unobserved interval is unknown. This exception is confined to development; validation and final test have regular hourly observations.

The audit also records 16 raw close-time metadata anomalies. One SOL December 2021 timestamp is corrected from a checksum-verified official daily source without changing its OHLCV; 15 shortened metadata timestamps remain explicitly allowlisted. Unknown gaps and malformed data still fail. See the data-quality JSON and raw repair provenance for exact timestamps and source checksums.

## Important limitations and licensing

- The fixed universe is a purposive survivor sample, not a point-in-time representation of all crypto markets.
- USDT-denominated returns are not identical to USD returns.
- Shorts are theoretical: no borrowing, funding, margin, capacity, or liquidation model is included.
- Execution is idealized at observed closes. Turnover follows course target-weight changes and ignores ordinary weight drift.
- A 7 bps limit-order commission does not imply fills, zero slippage, or achievable limit-order profitability; this project does not simulate them.
- Selecting among 18 validation experiments makes selected validation performance optimistic; 2025 is the separate final evaluation.
- Volume is an activity proxy, not evidence of informed trading or causal news.

Attribution: Binance Vision (`data.binance.vision`). The [dataset terms](https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md) grant non-commercial educational/research use under CC BY-NC-SA 4.0 and restrict production/commercial uses. Dataset-derived results, charts, and redistributed derivatives retain attribution and CC BY-NC-SA 4.0 conditions. No publication, distribution to third parties, or live trading is performed by these commands.

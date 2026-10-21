# Fixed all-22-coin reversal: executed specification and saved results

**Status: completed, approved and independently audited.** This document describes the unchanged trading specification, saved period evidence and execution provenance. It does not revise the original acceptance criteria or introduce a new test. The source implementation base was `573b8f646b6b833019f8e3319c427642d39fadff`.

## Main finding: performance did not persist across periods

Reversal lost in development and validation; its positive partial-year 2026 result does not establish persistence across periods. The pattern across periods—not the best isolated result—is the finding.

| Period | Net return at 20 bps | Sharpe √365 / √252 | Hourly maximum drawdown |
| --- | ---: | ---: | ---: |
| 2022–2023 development | -33.59% | -0.87 / -0.72 | 43.69% |
| 2024–2025 validation | -15.66% | -0.32 / -0.27 | 31.57% |
| January–September 2026 (273 days) | +9.91% | 0.81 / 0.67 | 11.10% |

These are saved descriptive period results, **not newly defined acceptance tests**. The nine frozen strategies remain unchanged. This standalone fixed study is not combined with another rule, used for a new direction selection, or treated as a new winner.

## Purpose and fixed universe

Use one cross-sectional rank-demean reversal rule across all 22 inherited economic slots, without another eight-coin basket or lookback selection step. The fixed historical-liquidity order is BTC, ETH, SHIB, BNB, SOL, XRP, DOT, SAND, legacy LUNA, AVAX, DOGE, ADA, FTM, TRX, MATIC, MANA, FIL, GALA, LINK, AXS, LTC and VET, all USDT source slots. Every eligible member enters the same ranking; inactive slots are not replaced.

Membership follows `in_tiered_basket_search_22=True` in [the universe inventory](../data/universe.csv). The inherited screen used 90 daily endpoints from 3 October through 31 December 2021, not contemporary liquidity. Source discovery and coverage limitations mean this is not a perfectly reconstructed point-in-time listing universe. [Data documentation](DATA.md) supplies the complete selection, coverage and lifecycle record.

## Unchanged trading specification

| Setting | Fixed value |
| --- | --- |
| Strategy | `reversal_h0672_r168` |
| Signal | Trailing 672-elapsed-hour simple return, exactly 28 days |
| Direction | Buy relative losers and short relative winners |
| Weights | `−(average_tied_rank_i − mean_rank) / sum(abs(rank − mean_rank))` over eligible members |
| Schedule | Monday 00:00 UTC; phase 0; epoch 3 January 2022; preserve the warm-up clock |
| Buffer | Off: full-L1 threshold 0.0 |
| Normal targets | Gross 1 and net 0; long and short each 0.5 when nondegenerate |
| Degenerate target | Flat for fewer than two eligible ranks or all equal ranks; permission/missingness deferrals remain distinct |
| Primary costs/execution | 20 bps one-way full-L1 target change; idealized observed-close lag 1 |
| Sensitivities | Lag 1 at 0/5/10/15/20/40 bps; lag 2 at 20 bps; 21 period-scenario keys |

The 40% hourly drawdown guardrail was an evaluation limit, **not an intra-run trading stop**. No basket, lookback, cadence, direction or fee sensitivity is promoted after observing these results.

## Source, lifecycle and boundaries

The [source manifest](../data/manifest.json) pins seven Binance Data Vision spot-USDT hourly panels/masks: **43,824 UTC close endpoints**, from **1 October 2021 at 01:00 through 1 October 2026 at 00:00**, including warm-up.

| Period | Start boundary | Closing endpoint | Complete days |
| --- | --- | --- | ---: |
| Development | 1 January 2022, 00:00 UTC | 1 January 2024, 00:00 UTC | 730 |
| Validation | 1 January 2024, 00:00 UTC | 1 January 2026, 00:00 UTC | 731 |
| Partial-year 2026 | 1 January 2026, 00:00 UTC | 1 October 2026, 00:00 UTC | 273 |

Each period begins independently uninvested, uses full prior warm-up, and pays initial entry and terminal liquidation costs. A warm-up-established target may enter the first interval; there is no artificial first-Monday wait. Do not concatenate independently reset paths into one investable curve. Full-L1 costs include initial, ordinary, mandatory and terminal changes without halving turnover.

The engine preserves audited venue bridges and lifecycle permissions, legacy LUNA’s real 00:40 UTC exit on 13 May 2022 in the 01:00 accounting bucket, FTM/S and MATIC/POL continuations, nontrading gaps and rewarm rules. No gaps were filled, instruments replaced, or windows shortened. Lag 1 is an idealized observed-close fill, not a guaranteed one-hour wait; lag 2 adds one hour. Ordinary weight-drift maintenance, borrow, funding, margin, realistic impact and capacity remain unmodeled.

## Performance conventions and descriptive uncertainty

Net means **after transaction costs**; gross performance is reported separately. Saved tables include compounded net returns, CAGR, volatility, gross/net Sharpe, full-L1 turnover, hourly drawdown and its dates/durations, exposure and descriptive BTC alpha/beta with confidence intervals.

Two separate Sharpe annualization conventions are shown on the **same complete UTC daily return series, including weekends**:

- **√365:** `sqrt(365) × mean(daily return) / sample_sd(daily return)`.
- **√252:** the √365 result multiplied by `sqrt(252/365)`.

This changes the Sharpe scale, not the observations, strategy or P&L. CAGR, volatility, turnover annualization and annual alpha retain elapsed-calendar/365-day conventions. Partial-year 2026 CAGR is an extrapolated annual rate, not a realized full-year return.

Saved raw-mean t-statistics are **descriptive**, using calendar Bartlett HAC27 with the n/(n−1) covariance adjustment. The saved 95% raw Sharpe intervals are marginal percentile intervals from 10,000 circular 28-day block draws, NumPy PCG64 seed 20261020 reset for each period. Both Sharpe scales use the same draw indices; √252 endpoints are positive-scale transforms of √365 endpoints. Resampling uses saved daily observations, without regenerated signals or invented block-boundary fees. No new hypothesis test, revised acceptance decision or corrected p-value is inferred from this presentation.

BTC attribution is descriptive full-period OLS with Bartlett HAC7, no finite covariance correction, 365-day annual alpha and marginal 95% coefficient intervals. It is BTC-only, not a joint 22-coin model. Uncertainty is conditional on the supplied universe and fixed specification, not adjusted for earlier basket/parameter research. The 273-day 2026 period supplies only about 9.75 block lengths.

## Chronology and interpretation

**Reversal chronology:** its complete code/configuration/environment/data receipt was sealed before the first new-study actual input decode: freeze event 20 October 2026 at 19:08:16.129615 UTC; first actual panel access at 19:08:22.131262 UTC. Synthetic-only tests ran before that seal with readers blocked. Other studies were byte-hashed for administrative preservation, not used as performance or inference inputs. This clean study-specific gate does not turn previously examined historical dates into unseen evidence.

All three historical windows had already been examined in the wider project. Their established development/validation/2026 labels support consistent period comparison; these later fixed studies are **not fresh independent OOS confirmation**. A failure here does not prove every reversal strategy fails. Neither an isolated gain nor a descriptive interval establishes deployment readiness.

Independent accounting checks reconciled all 21 scenario-period keys, targets and held paths, lifecycle returns, initial/forced/final full-L1 costs, compounding and performance metrics. Independent statistical checks reconciled the saved statistics and preservation record. Publishing these saved results introduces no new strategy execution, parameter selection, source-data acquisition, live order or monitoring.

## Saved evidence

- [Primary full-precision period results](../results/fixed_all22_reversal/primary_summary.csv)
- [All 21 cost/delay results](../results/fixed_all22_reversal/scenario_metrics.csv)
- [Saved daily returns](../results/fixed_all22_reversal/daily_returns.csv)
- [Descriptive means and raw Sharpe intervals](../results/fixed_all22_reversal/primary_inference.json), also available as [CSV](../results/fixed_all22_reversal/primary_inference.csv)
- [Settings, source/code hashes, chronology and audit summary](../results/fixed_all22_reversal/methods.json)

The existing `scripts/run_research.py` remains the frozen-nine reproducer; no new public fixed-study runner is introduced. Findings appear within the existing three reports, not a fourth report.

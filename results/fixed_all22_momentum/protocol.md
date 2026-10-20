# Draft fixed all 22 coin momentum protocol

**Status: draft for approval, not run.** The user chose momentum for this proposal on 20 October 2026. Choosing that direction is not approval to execute the benchmark. No all-22 strategy backtest, new price acquisition, live order or scheduled job is authorized by this document. The nine frozen strategies, their results and acceptance flags remain unchanged.

## Purpose and fixed hypothesis

Test whether a simple relative-strength rule behaves more consistently across periods when eight-coin basket optimization and parameter reselection are removed. The single proposed specification is **28-day cross-sectional momentum on the fixed 22-slot universe, rebalanced weekly**. It is a simplicity benchmark, not a recommendation or a forecast of positive performance.

This proposal was made after the existing development, validation and January-September 2026 results had been examined. The historical windows retain their established labels for comparison; they are not fresh independent tests of this newly proposed rule. Even a positive result in all three would require confirmation on an unseen period with boundaries fixed before accessing its prices. This removes a new basket search, not inherited universe choices or prior research influence.

There will be no reversal alternative, parameter grid, basket sweep, buffer comparison, volatility target, regime switch, stop-loss optimization or post-result reselection in this experiment. Negative or invalid outcomes remain in the record. No changes will be made simply to obtain a positive Sharpe.

## Single specification

| Item | Proposed fixed choice |
| --- | --- |
| Direction | Momentum: buy relative winners and short relative losers |
| Existing engine definition | `momentum_h0672_r168` |
| Family and grid | `momentum`; `time_scale` |
| Trailing lookback | 672 elapsed hours, exactly 28 days |
| Scheduled decisions | Every Monday at 00:00 UTC, 168-hour cadence |
| Schedule epoch and phase | 3 January 2022 00:00 UTC; phase 0; keep the same clock throughout warm-up |
| Buffer | Off, full-L1 buffer threshold 0.0 |
| Normal target exposure | Gross 1 and net 0 when eligible ranks are nondegenerate |
| Position sizing | Average-tied ranks, demeaned and full-L1 normalized across eligible members; no volatility or liquidity weighting |
| Primary fee and execution | 20 bps one way on full-L1 changes; inherited idealized observed-close lag 1 |
| Cash comparison | 3% nominal annual, ACT/365F, daily cash return 0.03/365; benchmark only, no interest credited to strategy balances |

At a decision time t, score coin i by `s_i = P_i(t)/P_i(t-672h) - 1`. Among the source-eligible coins E, calculate average-tied ranks q_i, their mean q_bar, and `w_i = (q_i-q_bar)/sum_j(abs(q_j-q_bar))`. Unavailable members have zero proposed target. For a computable but degenerate target, including fewer than two eligible ranks, the proposed target is all cash. Audited suspensions or an unavailable decision instead follow the engine's deferral rules; they must not be relabeled as an observed all-equal signal.

All 22 slots belong to the universe; not all must have nonzero holdings. Every eligible member affects its relative ranking. This is not 1/22 per coin, and it is not an eight-coin portfolio sliced from a 22-coin target. Long and short target budgets are each one half when nondegenerate. Dollar-neutral targets do not guarantee realized BTC-beta neutrality, particularly around lifecycle events.

## Fixed universe and historical liquidity

Use exactly the members with `in_tiered_basket_search_22=True` in `data/universe.csv`, in their historical liquidity-rank order. The ranking used median daily Binance spot-USDT quote volume over 90 endpoints from 3 October through 31 December 2021, with a 1 January 2022 decision and 24-hour information lag. It was drawn from the inherited 30-coin research inventory, not an unrestricted listing census. There is no reconstitution or replacement by present-day survivors.

| Historical rank | Economic source slot |
| --- | --- |
| 1 | `BTCUSDT` |
| 2 | `ETHUSDT` |
| 3 | `SHIBUSDT` |
| 4 | `BNBUSDT` |
| 5 | `SOLUSDT` |
| 6 | `XRPUSDT` |
| 7 | `DOTUSDT` |
| 8 | `SANDUSDT` |
| 9 | `LUNAUSDT` |
| 10 | `AVAXUSDT` |
| 11 | `DOGEUSDT` |
| 12 | `ADAUSDT` |
| 13 | `FTMUSDT` |
| 14 | `TRXUSDT` |
| 15 | `MATICUSDT` |
| 16 | `MANAUSDT` |
| 17 | `FILUSDT` |
| 18 | `GALAUSDT` |
| 19 | `LINKUSDT` |
| 20 | `AXSUSDT` |
| 21 | `LTCUSDT` |
| 22 | `VETUSDT` |

SAND is included even though it is absent from the nine-strategy union. `LUNAUSDT` means legacy Terra/LUNC, not Terra 2.0; FTM/S and MATIC/POL retain the existing migration and cash-gap treatment. BTC and ETH are ordinary members of this rank calculation, not fixed-capital sleeves. Historical ranks determine membership only; they do not become portfolio weights or later selection signals.

## Source and lifecycle contract

Reuse the included Binance Vision one-hour normalized data and all seven checksum-pinned files in `data/manifest.json`. The complete UTC grid has 43,824 close endpoints from 1 October 2021 01:00 to 1 October 2026 00:00. Reuse `prices`, `quote_volume`, `tradable`, `observed`, `hold_allowed`, `mandatory_exit` and the whole-venue `decision_allowed` series, with their attributes. Do not decode any panel for this proposed experiment until execution is explicitly approved and its receipt is sealed.

Signals require the existing causal current/lookback observations and uninterrupted lifecycle eligibility. Preserve NaNs; do not forward-fill, shorten a window, interpolate a suspended price, substitute another coin or bridge an unaudited migration gap. A temporarily missing active quote defers the whole ordinary rebalance under the existing generator. Whole-venue suspension bridges and unavailable decisions defer ordinary changes and preserve the audited return accounting. Mandatory lifecycle exits override cadence and rerank the remaining eligible cross-section using the existing engine.

Keep the legacy LUNA partial exit at its audited final real quote, 13 May 2022 at 00:40 UTC, in its existing 01:00 accounting bucket. Other-position adjustments at the hourly mark can create temporary exposure imbalance. Preserve documented migration gaps and rewarm requirements. A checksum failure, unexplained gap, invalid permission or unpriced nonzero holding stops evaluation as a data/integrity failure, rather than generating a shortened or filled result.

## Periods and boundary accounting

| Established comparison label | Start inclusive | End closing endpoint | Complete UTC days |
| --- | --- | --- | --- |
| Development | 1 January 2022 00:00 UTC | 1 January 2024 00:00 UTC | 730 |
| Validation | 1 January 2024 00:00 UTC | 1 January 2026 00:00 UTC | 731 |
| Partial-year 2026 evaluation | 1 January 2026 00:00 UTC | 1 October 2026 00:00 UTC | 273 |

Generate signals with the complete preceding warm-up and inherited schedule. Evaluate each period independently from cash and charge initial entry and terminal liquidation. The first evaluated interval can enter a target already established during warm-up; do not impose a new first-Monday waiting rule. Returns cover accounting intervals ending after the start and through the closing endpoint. Do not concatenate the independently reset period NAVs into a single investable equity curve. Any annual slices within a two-year path retain that path's positions and fees, with no invented January reset.

## Costs and execution sensitivities

Retain seven predeclared scenarios per period: 0, 5, 10, 15, 20 and 40 bps at lag 1, plus 20 bps at lag 2. This is **21 scenario-period keys for one strategy**, not 21 candidate strategies. The 20-bps lag-1 result remains primary regardless of which sensitivity looks best.

Use the current generator, simulator, boundary accounting and metric APIs without modifying frozen registries or public APIs. Lag 1 is idealized execution at an observed close; it is not a guaranteed one-hour elapsed wait. Lag 2 adds an hour. Full-L1 costs include entry, scheduled changes, mandatory changes and liquidation, with no division by two. Ordinary drift-maintenance trading, actual short borrow, funding, margin, order-book depth, slippage and capacity remain unmodeled. Report a noncompoundable return or insolvency as a failed/invalid scenario; never discard the failing interval or silently switch to cash.

## Performance and Sharpe conventions

For each primary period report gross and net compounded return, elapsed-calendar CAGR, annualized daily volatility, hourly maximum drawdown and its dates/durations, full-L1 turnover, exposure, and descriptive BTC alpha/beta with intervals. Provide the same fixed 3% cash benchmark, cash-relative return and growth, raw-versus-cash daily drawdown, and cash-excess Sharpe. Retain both gross and net Sharpe where defined. Theoretical neutrality is not a realized alpha claim.

Use the same complete UTC daily return series, including weekends, for both Sharpe scales: `S365 = sqrt(365)*mean(d)/sample_sd(d)` and `S252 = S365*sqrt(252/365)`, where d is raw daily net return for the zero-cash comparison or daily net return minus 0.03/365 for cash excess. The 252 result is a course-convention display of the same series, not a new weekday-only sample. Preserve signs and undefined all-cash Sharpe states. Cash accrual, elapsed-calendar CAGR, alpha annualization, t-statistics and hypothesis tests do not change to 252. Do not subtract three percentage points from CAGR or alpha as a shortcut.

## Predeclared interpretation and uncertainty

The primary economic persistence condition is **positive wealth-relative net return above the 3% cash benchmark in each of the three periods at 20 bps, lag 1**. Also disclose nominal net profitability in every period. Failure in any period defeats an all-period persistence claim; do not average away a losing interval or replace the rule. No numerical Sharpe floor or ranking promotion is used.

As a proposed risk guardrail, flag an original hourly maximum drawdown greater than 40% in any primary period. This is an evaluation flag, not an intra-run stop or strategy modification. Turnover is disclosed and costed in full; no data-fitted turnover cap or leverage adjustment is introduced. Passing these conditional checks is not approval to trade.

The primary inferential family is the **three period-specific mean arithmetic daily cash-excess returns**, one hypothesis per period, alternative mean greater than zero. Use calendar-aware Bartlett HAC with 27 lags and n/(n-1) covariance adjustment. Report the HAC mean/standard error and t-statistic. Use 10,000 centered circular 28-day block-bootstrap-t draws, seed 20261020 reset separately for each period, for the one-sided primary p-value `(1 + count(T_star >= T_observed))/(10000 + 1)`. Apply Holm at 5% across these three hypotheses, retaining every slot. Do not apply this new family to the original nine or alter their acceptance flags.

Use one new NumPy Generator(PCG64(20261020)) per period. For each draw, sample ceil(n/28) block starts uniformly from 0 through n-1, concatenate the circular 28-day index blocks and truncate to n observations. Use these same draw indices for every statistic within that period. The null test centers daily cash excess by its observed mean and computes T_star = mean(centered_x_star)/SE_star. The mean-interval bootstrap statistic is (mean(x_star)-mean(x))/SE_star, with calendar HAC27 recomputed in each draw. If q.025 and q.975 are its bootstrap quantiles and SE is the original sample's HAC standard error, invert the interval as [mean(x)-q.975*SE, mean(x)-q.025*SE].

Report 95% studentized intervals for mean cash excess and marginal 95% percentile intervals for cash-relative return, relative annualized growth and Sharpe. For the latter intervals, resample the **uncentered** saved daily strategy returns in circular 28-day blocks, retaining each period's length and deterministic cash days; do not regenerate signals, add block-boundary trades, or reselect parameters. Transform Sharpe interval endpoints by the same positive sqrt(252/365) factor rather than bootstrapping a second convention. Raw mean statistics and BTC attribution are descriptive comparisons, not extra tests used to declare the model successful.

Count invalid bootstrap draws per statistic. Never drop them silently: any invalid draw makes the affected interval/test unavailable; a non-estimable primary test retains its correction-family slot conservatively at p=1 with its unavailable status visible. In an all-cash/constant path, report undefined Sharpe rather than zero. The nine-month period contains only about 9.75 block lengths, so its intervals and tests have limited precision. Holm corrects only this three-hypothesis conditional family; it does not remove earlier universe, parameter, period or research-design selection.

**Classification is fixed in advance:** economic persistence requires the cash-relative return condition in all three periods; the proposed risk condition requires hourly drawdown no greater than 40% in each; statistical support across periods requires all three estimable cash-mean tests to have positive HAC t and Holm3 p <= 0.05. Report these dimensions separately. Passing only one dimension is not a combined pass, and even a combined conditional pass is not a deployment or fresh-independent-confirmation claim.

## Approval and execution gates

1. Obtain explicit approval of this exact specification, dates, assumptions and success criteria, and an instruction to run it. A choice of direction or permission to publish this draft is not execution approval.
2. Before opening panels, seal the approved protocol hash, fixed 22-member list, all code/configuration/data hashes, Python/dependency versions, output destination and scenario coverage. Verify every packaged source checksum. No new exchange download is part of this experiment.
3. Use a separate all-22 runner/output area after approval; the existing `run_research.py` remains a frozen-nine reproducer and must not be reconfigured to select or replace strategies. The current N-asset signal/simulator helpers may be reused through an additive adapter. Do not modify current results, selection files or source data.
4. Before a complete evaluation, test N=22 ranks/ties/degenerate cases, neutrality and exposure, weekly scheduling, missingness/forced exits, period starts and liquidation fees, full-L1 reconciliation, future-prefix invariance, compounding and Sharpe conversion. Validate existing frozen-nine reproduction unchanged, without turning it into a selection exercise.
5. Account for all 21 scenario-period keys, including failures and unavailable statuses. Independently reconcile the primary paths/fees/metrics and audit the final source/code hashes. Publish all three primary periods together, not only a favorable one. Do not change the rule after seeing the outcome.

No executable all-22 configuration, runner, backtest result or deployment claim is created by this draft. A genuinely unseen confirmation period would require a separately approved, pre-access window; it is not silently supplied by reusing the existing 2026 label.

## Source anchors

The draft is based on source commit `39b6ddc9ae0f5dacd8afc6e966df4748663474f6`. The publication manifest pins the complete current package. These anchors identify the specific universe, definition and implementation to review; the execution gate must additionally pin the complete approved dependency set and all seven data-file records before decoding.

| Source | SHA-256 |
| --- | --- |
| `data/manifest.json` | `b42a52ad424ea57af44ef542b9f418e353005952c51819cb6c19ee20c535381a` |
| `data/universe.csv` | `1aa6d5827f220dced04d1bce20b40d52dd5b0a615ab7b1c237aafe2f71a87c7d` |
| `configs/configuration_space.json` | `ee1998a33f77bfc85422bf0ae5978f96a84d1efab54a6040e19fb4812a2b583a` |
| `src/crypto_research/strategies.py` | `6a8d5f85dac9c248833b947becbae89a2e2fcc263f732fdf364a16b55ad0f5b0` |
| `src/crypto_research/simulator.py` | `23dc58af2eb92164aa0ba9fb3a4ac07d96f8ddd8969df66015c86d93132528c1` |
| `src/crypto_research/metrics_adapter.py` | `c02aec3acae0aead63a31a97b07931b57b4d8933c013a84dd012ce4390ad7ef6` |
| `src/crypto_research/cash_excess.py` | `8a22f418e68cc7413b76fb214a8d6ef9982ef4000277c167725ac0325862ea33` |

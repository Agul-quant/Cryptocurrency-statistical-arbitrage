# Draft fixed all 22 coin weekly reversal protocol

**Status: draft for approval, not run.** Prepared on 20 October 2026. This is a standalone reversal study with its own approval, execution, inference, outputs and conclusions. This proposal authorizes no backtest, additional price decoding, model fitting, download, GitHub push, live order or monitoring. Execution requires explicit approval of this protocol and an instruction to run. Existing strategies, results and three final reports remain unchanged.

## Purpose and interpretation

Test whether one fixed cross-sectional reversal rule on a fixed 22-coin universe has persistent economic and statistical support across three periods. The rule is **buy relative past losers and short relative past winners**, using a **28-day lookback and weekly Monday schedule**. Do not search for another lookback, basket or cadence.

The 2022–2023, 2024–2025 and January–September 2026 observations were already examined during the broader project; retaining their comparison labels cannot make them fresh independent tests of this proposal. A positive result would require confirmation on a separately approved unseen period fixed before its data are accessed.

This is relative-return reversal, not a fitted stationary price spread or guaranteed statistical arbitrage. No factor hedge, price-spread stationarity test or mean-reversion half-life is implied. Evaluate this rule on its own predeclared criteria. Do not load another strategy's results, calculate cross-strategy correlations, construct a combined portfolio, pool another study's tests, or choose a rule based on cross-study rankings.

## Fixed strategy

| Item | Proposed choice |
| --- | --- |
| Existing definition | `reversal_h0672_r168` |
| Family and grid | `reversal`; `time_scale` |
| Lookback | 672 elapsed hours, exactly 28 days |
| Decisions | Monday 00:00 UTC, every 168 elapsed hours |
| Epoch and phase | 3 January 2022 00:00 UTC; phase 0, including preceding warm-up Mondays |
| Buffer | Off; `buffer_l1 = 0.0` |
| Normal target | Gross exposure 1; net exposure 0; long and short budgets each 0.5 |
| Sizing | Average-tied ranks, demeaned, full-L1 normalized within the eligible cross-section |
| Primary cost and execution | 20 bps one way on full-L1 weight changes; inherited idealized observed-close lag 1 |
| Cash benchmark | 3% nominal annual, ACT/365F; daily c = 0.03/365; no interest credited to strategy balances |

At decision time t, compute `u_i = P_i(t)/P_i(t-672h) - 1`. Within eligible members E, let `q_i = rank_E(u_i, average ties)` and q_bar be the mean rank. Set:

```text
w_i = -(q_i - q_bar) / sum_j(abs(q_j - q_bar))
```

The existing engine's average-tied rank of `-u_i`, demeaned and normalized, is equivalent. Unavailable slots receive zero proposed weight. For a computable degenerate signal, including fewer than two eligible ranks, use an all-cash target. An unavailable decision is different: preserve the existing whole-target deferral rules rather than inventing an observed flat signal.

All 22 members participate when eligible; positions are not fixed 1/22 sleeves or eight-coin weights sliced from another portfolio. Dollar-neutral targets do not guarantee realized market-beta neutrality. Lifecycle partial exits can temporarily disturb exposure.

**Generate reversal targets and all accounting directly from the pinned source inputs.** Derive per-coin P&L from this study's held weights and audited asset returns, charge its own transaction costs, and compound its own NAV. No saved strategy return series or performance statistic is an input.

## Fixed universe and sources

Use exactly `in_tiered_basket_search_22=True` from `data/universe.csv`, in historical liquidity-rank order:

| Ranks | Binance spot USDT economic slots |
| --- | --- |
| 1–2 | BTC, ETH |
| 3–9 | SHIB, BNB, SOL, XRP, DOT, SAND, legacy LUNA/LUNC |
| 10–16 | AVAX, DOGE, ADA, FTM/S, TRX, MATIC/POL, MANA |
| 17–22 | FIL, GALA, LINK, AXS, LTC, VET |

Exact source column IDs are `BTCUSDT, ETHUSDT, SHIBUSDT, BNBUSDT, SOLUSDT, XRPUSDT, DOTUSDT, SANDUSDT, LUNAUSDT, AVAXUSDT, DOGEUSDT, ADAUSDT, FTMUSDT, TRXUSDT, MATICUSDT, MANAUSDT, FILUSDT, GALAUSDT, LINKUSDT, AXSUSDT, LTCUSDT, VETUSDT`.

The inherited liquidity measure is median daily USDT quote volume over 90 endpoints from 3 October through 31 December 2021, using a 1 January 2022 decision and 24-hour information lag. This is a ranking within the inherited 30-coin research inventory, not an unrestricted exchange-listing census. No reconstitution, replacement, coin removal or later liquidity filter is permitted. BTC and ETH are ordinary ranked members. SAND is included. Legacy LUNA/LUNC is not Terra 2.0.

Reuse the included Binance Vision hourly panels: `prices`, `quote_volume`, `tradable`, `observed`, `hold_allowed`, `mandatory_exit`, and whole-venue `decision_allowed`, preserving their attributes. The complete source grid has 43,824 endpoints from 1 October 2021 01:00 UTC through 1 October 2026 00:00 UTC. Verify all seven byte sizes and SHA-256 pins in `data/manifest.json` before decoding. No new exchange download is proposed.

Preserve NaNs, continuous lookback eligibility, documented venue-halt bridges, inactive slots, migration cash gaps and rewarm rules. Missing active observations defer the whole ordinary rebalance. Mandatory exits override cadence and rerank remaining eligible members. Retain legacy LUNA's audited 13 May 2022 00:40 UTC final-quote exit in its existing 01:00 accounting bucket. Do not fill gaps, bridge unaudited migrations or permit unpriced nonzero holdings. Integrity failures stop evaluation rather than shorten the sample.

## Periods and accounting

| Comparison label | Start UTC | Closing endpoint UTC | Complete days |
| --- | --- | --- | ---: |
| Development | 1 January 2022 00:00 | 1 January 2024 00:00 | 730 |
| Validation | 1 January 2024 00:00 | 1 January 2026 00:00 | 731 |
| Partial-year 2026 evaluation | 1 January 2026 00:00 | 1 October 2026 00:00 | 273 |

Keep full preceding warm-up and the inherited scheduling epoch. Each period starts independently from cash and pays initial entry and final liquidation. The first evaluated interval may enter a target established during warm-up; do not impose a first-Monday waiting rule. Include accounting intervals ending after the start and through the closing endpoint. Do not concatenate independently reset NAVs into one investable curve. Within-period annual slices keep continuous positions and fees, with no invented January reset.

Evaluate six fee levels at lag 1: **0, 5, 10, 15, 20 and 40 bps**, plus **20 bps at lag 2**. This is **21 new scenario-period keys for one reversal strategy**, not a candidate search. The primary remains 20 bps, lag 1 regardless of sensitivity results. Include ordinary, forced, initial and terminal full-L1 charges without dividing by two. Reuse zero-fee base accounting per lag where valid.

Lag 1 is an idealized observed-close fill, not a guaranteed real one-hour delay; lag 2 adds an hour. Retain failed, noncompoundable, insolvent and unavailable slots with explicit status. Do not discard a loss interval or switch to cash as a repair. Short borrow, funding, margin, order-book impact, capacity and ordinary weight-drift maintenance remain unmodeled.

## Performance

For all three primary periods, report gross and net compounded returns, calendar CAGR, annualized daily volatility, hourly maximum drawdown with peak/trough/recovery and duration, full-L1 turnover, exposure, raw daily versus cash-relative daily drawdown, and descriptive BTC alpha/beta with marginal confidence intervals. Alpha is 365 times the daily arithmetic intercept, not CAGR; retain the existing full-calendar HAC7 convention and cash-adjusted comparison. No coefficient becomes a selection gate.

Report raw and cash-excess Sharpe under both conventions on the **same complete UTC daily series including weekends**:

```text
S365 = sqrt(365) * mean(d) / sample_sd(d, ddof=1)
S252 = S365 * sqrt(252/365)
d = daily net return                  for the zero-cash comparison
d = daily net return - 0.03/365       for cash excess
```

Keep constant/all-cash Sharpe undefined. Cash-relative return is `W(strategy)/W(cash)-1`; relative annualized growth is `(W(strategy)/W(cash))^(365/n)-1`. Do not compound arithmetic excess as if it were the wealth ratio. Cash accrual, CAGR, volatility, alpha, t-statistics and p-values do not change to 252. The nine-month CAGR is an extrapolation, not a full-year realized return.

Cash is a hypothetical constant benchmark in USDT-quoted units, not an available risk-free yield product. A USD interpretation assumes USDT/USD parity; no depeg hedge or currency conversion is modeled.

Present only this study's reversal results, with cash and BTC serving the explicitly defined performance/attribution benchmarks. Its tables, inference and acceptance decisions must not depend on another strategy study's returns, p-values or classifications.

## Success criteria and uncertainty

**Economic persistence:** reversal must have strictly positive cash-relative net return in **each** primary period. Also disclose nominal profitability in each. One failed period defeats an all-period claim; neither averaging nor an alternative fee scenario can rescue it.

**Risk:** hourly maximum drawdown must be no greater than **40% in each** primary period. This is an evaluation guardrail, not an intra-run stop. Turnover is disclosed and fully costed, without a fitted cap, leverage adjustment or new Sharpe threshold.

For each period, test the alternative that mean arithmetic daily cash excess is greater than zero. Use calendar-aware Bartlett **HAC27**, with n/(n−1) covariance correction. Report mean, standard error and t. Use **10,000 circular 28-day bootstrap-t draws**, NumPy Generator(PCG64(**20261020**)), reset separately for each period. Draw ceil(n/28) uniformly sampled block starts from 0 through n−1, concatenate circular blocks and truncate to n. The same index draw drives all statistics within a period.

Center cash excess by its observed mean for the null and use `T_star = mean(centered_x_star)/SE_star`, recomputing HAC27 per draw. The one-sided p-value is `(1 + count(T_star >= T_observed))/10001`. For a studentized 95% mean interval, use `(mean(x_star)-mean(x))/SE_star` quantiles and invert as `[mean(x)-q.975*SE, mean(x)-q.025*SE]`. For marginal 95% cash-relative return, relative growth and raw/cash Sharpe intervals, resample uncentered daily strategy returns with the same indices and deterministic number of cash days. Do not regenerate trades or invent block-boundary fees. Rescale Sharpe CI endpoints for √252 rather than bootstrap a second convention.

### Reversal only testing family

**Primary statistical classification uses Holm3 within this reversal study only:** one positive-cash-mean hypothesis for each of the three periods. Correct the three original unadjusted one-sided bootstrap-t p-values together. The fixed slot order is development, validation, then partial-year 2026. No other strategy's test or p-value enters this family.

The all-period statistical-support condition requires **all three reversal tests estimable, positive HAC t, and Holm3-adjusted p ≤ 0.05**. No pooled correction, paired comparison or cross-strategy ranking is part of this protocol.

Holm3 accounts only for these three conditional hypotheses. It does not adjust for earlier universe, parameter or period research, remove prior observation of these dates, or create unseen confirmation.

Count invalid draws for every statistic. Any invalid draw makes its affected interval/test unavailable; do not discard it. A non-estimable test retains its correction-family slot at p=1, with unavailable status visible. Do not replace an unavailable test with a different metric. The 273-day period has only about 9.75 block lengths, limiting precision.

Report economic, risk, statistical and procedural compliance separately. A combined conditional performance pass requires all three performance dimensions; it is not deployment approval. Procedural breaches must remain disclosed even if performance is favorable.

## Approval and execution gates

1. **Obtain explicit approval and an instruction to run.** A request for this draft is not execution approval. No executable reversal adapter, new return path or reversal inference result is created now.
2. After approval, create an owned, separate reversal study. Before **any additional actual-input decoding or real-data test for that experiment**, seal this approved text, exact definition/membership, all execution/audit code, configuration, source-data pins, environment, output destination and 21-key coverage. The gate precedes access for the new experiment; it must not claim that project data have never been seen. Other strategy results and test statistics are not input dependencies.
3. **Classify tests before running them.** Before the seal, run only explicit synthetic fixtures with actual-data loaders blocked. Do not run the entire existing test suite: some tests decode hourly panels and recompute saved-data strategy diagnostics. Select the source-only/synthetic engine checks needed for this standalone study. After sealing, log access before any source loading or permitted real-data verification. Never describe real-data tests as synthetic-only. Preserve and disclose any breach rather than rewriting its chronology.
4. Keep existing runners, registries, reports and completed study directories immutable. Use unchanged N-asset strategy, simulator and metric APIs through an additive reversal adapter. Check exact membership, average ties, zero/undefined signals, neutrality, weekly epoch/warm-up, missingness, forced exits, lag 1/2, causal prefixes, initial/terminal fees, compounding and √252 scaling. Independently derive expected reversal weights from its own score/rank formula, without another strategy's targets or returns.
5. Verify original source/configuration/data/results hashes remain unchanged. Independently reconcile reversal targets, held weights, per-coin gross P&L, full-L1 fees, NAV, daily returns, drawdowns and all 21 work keys. Independently verify bootstrap draws, CI transformation and the three Holm3 inputs and their ordering. No cross-study performance reproduction or result comparison is required by this protocol.
6. Present all three primary reversal periods together, all sensitivities and all failures. Do not change direction, basket, parameters, windows or success criteria after seeing the results. Public report/GitHub updates, live trading and scheduled monitoring require separate authorization.

Proposed local study location: `local_outputs/fixed_all22_reversal/`. Its source adapter, approval, code/data/environment freeze, access log, outputs, coverage/accounting/statistical audits and final checksums are owned by this study alone. It may reuse the audited engine and market dataset, but not another study's performance outputs. This document is a technical draft, not a fourth final performance report.

## Source anchors

Current source commit: `573b8f646b6b833019f8e3319c427642d39fadff`. These identify the inputs and existing implementations to be pinned again at execution; they are not an execution receipt.

| Source | SHA-256 |
| --- | --- |
| `data/manifest.json` | `b42a52ad424ea57af44ef542b9f418e353005952c51819cb6c19ee20c535381a` |
| `data/universe.csv` | `1aa6d5827f220dced04d1bce20b40d52dd5b0a615ab7b1c237aafe2f71a87c7d` |
| `configs/configuration_space.json` | `ee1998a33f77bfc85422bf0ae5978f96a84d1efab54a6040e19fb4812a2b583a` |
| `src/crypto_research/strategies.py` | `6a8d5f85dac9c248833b947becbae89a2e2fcc263f732fdf364a16b55ad0f5b0` |
| `src/crypto_research/simulator.py` | `23dc58af2eb92164aa0ba9fb3a4ac07d96f8ddd8969df66015c86d93132528c1` |
| `src/crypto_research/metrics_adapter.py` | `c02aec3acae0aead63a31a97b07931b57b4d8933c013a84dd012ce4390ad7ef6` |
| `src/crypto_research/cash_excess.py` | `8a22f418e68cc7413b76fb214a8d6ef9982ef4000277c167725ac0325862ea33` |

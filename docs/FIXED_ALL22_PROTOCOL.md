# Fixed all-22-coin momentum: approved and completed separate study

**Current status: completed, approved, independently audited.** This document is a current publication summary of the executed specification. It is **not** a rewritten sealed protocol. The [exact approved protocol snapshot](../results/fixed_all22_momentum/protocol.md) is preserved byte-for-byte with SHA-256 `57b01784b17929b60bcef0db5eda3ee53e675fdfcfcfd1be88a549d38950197a`; its pre-execution “draft/not run” wording describes the snapshot when prepared, not the current completion status. Explicit execution approval was subsequently recorded on 20 October 2026. The source implementation base was `573b8f646b6b833019f8e3319c427642d39fadff`.

## Purpose and scope

Run one fixed cross-sectional rank-demean momentum rule across the complete inherited 22-coin universe, removing a new eight-coin basket and lookback selection step. This is a standalone follow-up study, not a replacement for the nine frozen strategies or a search for a 2026 winner. It has its own three-period hypothesis family and conclusions. Publishing it beside another separately conducted fixed study does not create a combined model, correlation analysis or pooled test.

The observations in all three established periods had already been examined in the broader project. Their development/validation/2026 labels are retained for consistent reporting, **not fresh independent confirmation**. A genuinely unseen confirmation window would require separate pre-access approval.

## Executed specification

| Setting | Fixed value |
| --- | --- |
| Strategy | `momentum_h0672_r168` |
| Signal | Trailing 672-elapsed-hour simple return, exactly 28 days |
| Direction | Buy relative winners and short relative losers |
| Weights | `+(average_tied_rank_i-mean_rank)/sum(abs(rank-mean_rank))` over eligible members |
| Schedule | Weekly Monday 00:00 UTC, phase 0, epoch 3 January 2022; preserve warm-up clock |
| Buffer | Off: full-L1 threshold 0.0 |
| Normal targets | Gross 1, net 0; long and short each 0.5 when nondegenerate |
| Degenerate target | Flat when fewer than two eligible ranks or all ranks equal; permission/missingness deferrals remain distinct |
| Primary costs/execution | 20 bps one-way full-L1 changes, idealized observed-close lag 1 |
| Sensitivities | Lag 1 at 0/5/10/15/20/40 bps; lag 2 at 20 bps; 21 period-scenario keys |
| Cash comparison | 3% nominal annual ACT/365F, daily 0.03/365, benchmark only |

The fixed historical-liquidity order is BTC, ETH, SHIB, BNB, SOL, XRP, DOT, SAND, legacy LUNA, AVAX, DOGE, ADA, FTM, TRX, MATIC, MANA, FIL, GALA, LINK, AXS, LTC and VET (all USDT source slots). Every eligible member enters the same rank calculation; inactive slots are not replaced. Membership follows `in_tiered_basket_search_22=True` in [the inventory](../data/universe.csv). It inherits the 90 daily-endpoint October–December 2021 liquidity ranking, not an unrestricted contemporary listing universe.

## Source, lifecycle and evaluation boundaries

Use the seven checksum-pinned Binance Data Vision spot USDT one-hour panels/masks in [the source manifest](../data/manifest.json), with 43,824 UTC close endpoints from 1 October 2021 at 01:00 through 1 October 2026 at 00:00. [Data documentation](DATA.md) defines liquidity selection, availability, token continuations and audited suspensions.

| Period | Start boundary | Closing endpoint | Complete days |
| --- | --- | --- | ---: |
| Development | 1 January 2022 at 00:00 UTC | 1 January 2024 at 00:00 UTC | 730 |
| Validation | 1 January 2024 at 00:00 UTC | 1 January 2026 at 00:00 UTC | 731 |
| Partial-year 2026 | 1 January 2026 at 00:00 UTC | 1 October 2026 at 00:00 UTC | 273 |

Each period starts independently from cash with full prior warm-up and pays initial entry and terminal liquidation. A warm-up-established target can enter the first interval; no artificial first-Monday wait is added. Do not concatenate these separately reset paths into a single investable curve. Full-L1 costs include entry, ordinary targets, mandatory changes and final liquidation, without halving turnover.

Preserve audited venue bridges, lifecycle permissions, legacy LUNA’s real 00:40 UTC exit on 13 May 2022 in the 01:00 bucket, FTM/S and MATIC/POL continuation/cash gaps and rewarm rules. No interpolation, forward filling, replacement, unexplained-gap repair or shortened evaluation. Lag 1 is an idealized observed-close fill, not a guaranteed one-hour elapsed wait; lag 2 is an additional-hour sensitivity. Ordinary drift-maintenance, borrow, funding, margin and realistic market-impact/capacity constraints remain unmodeled.

## Performance, inference and fixed criteria

Use complete UTC daily observations including weekends. Report raw net and cash-relative wealth returns and growth, gross/net Sharpe, volatility, full-L1 turnover, original hourly drawdown and its dates/durations, exposures and descriptive full-period BTC raw/cash alpha/beta intervals. Sharpe √252 is Sharpe √365 times `sqrt(252/365)` on the **same** daily series. Do not change cash accrual, elapsed-calendar CAGR, alpha or inference to 252 days. Cash is not credited to strategy wealth; relative return is `W_strategy/W_cash-1`.

The primary test is mean daily arithmetic cash excess greater than zero, once per period. Use Bartlett calendar HAC27 with n/(n−1) covariance adjustment, 10,000 centered circular 28-day bootstrap-t draws, NumPy PCG64 seed 20261020 reset each period, and `(1+count(Tstar>=Tobserved))/(10000+1)`. Apply **Holm across this study’s three period hypotheses only**. Keep separate from the other fixed study and original nine corrections.

Use 95% studentized mean intervals and marginal percentile intervals for cash-relative return/growth and raw/cash Sharpe, using the same uncentered draw indices for those descriptive intervals. Transform √252 Sharpe endpoints by the same positive constant. Resample saved daily observations only; do not regenerate signals or add block-boundary fees. Never drop invalid draws: affected inference is unavailable and non-estimable tests retain a conservative p = 1 slot. BTC attribution uses descriptive full-period OLS Bartlett HAC7, no finite covariance correction, 365-day annual alpha and marginal 95% coefficient intervals.

Predeclared dimensions are distinct:
- **Economic persistence:** positive cash-relative net wealth return in every primary period.
- **Risk:** original hourly maximum drawdown no greater than 40% in every primary period; an evaluation flag, not a trading stop.
- **Statistical support:** all three tests estimable with positive HAC t and Holm3 p ≤ 0.05.
- **Nominal profitability:** disclose positive compounded net return in every period separately.

Failure in any period defeats the corresponding all-period condition. Passing only one dimension is not a combined pass; even a combined conditional pass is not deployment approval or unseen confirmation. Conditional intervals do not correct earlier universe and research-design selection; 273 days provide only about 9.75 block lengths.

## Execution provenance and saved evidence

**Momentum chronology exception:** Strict pre-panel-access sealing was not satisfied. Existing verification tests decoded the seven actual hourly panels and saved daily inputs and recomputed the original nine strategies’ cash statistics before this study’s complete execution seal. Corrections were retained; no new all-22 targets or strategy performance were calculated before the all-22 code was sealed. Later sealing does not repair that gate failure. The completed study is therefore labeled with this procedural exception, not strict pre-access compliance.

The independent accounting audit reconciled all 21 scenario-period keys, targets/held paths, lifecycle returns, initial/forced/final full-L1 costs, compounding and metrics; the separate statistical audit independently checked inference and preservation. The original nine frozen strategies, source data, public financial code and existing results were unchanged. No new exchange download, live order or monitoring was performed.

Saved public evidence:
- [Primary full-precision period results](../results/fixed_all22_momentum/primary_summary.csv)
- [All 21 cost/delay results](../results/fixed_all22_momentum/scenario_metrics.csv)
- [Saved daily returns](../results/fixed_all22_momentum/daily_returns.csv)
- [Inference with intervals and tests](../results/fixed_all22_momentum/primary_inference.json) and [CSV](../results/fixed_all22_momentum/primary_inference.csv)
- [Predeclared classification](../results/fixed_all22_momentum/classification.json)
- [Sanitized settings, sealed code/data/protocol hashes and audit summary](../results/fixed_all22_momentum/methods.json)

These are saved-result publications. This repository’s existing `scripts/run_research.py` remains the frozen-nine reproducer; no new public runner or fresh execution is introduced by this update. Findings are integrated into the existing three reports, not a fourth report.

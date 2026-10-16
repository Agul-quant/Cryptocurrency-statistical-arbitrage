# Draft OOS protocol for the nine frozen crypto strategies

**Status: Draft for user approval. No 2026 market-data access, acquisition or OOS execution is authorized.**

Prepared October 15, 2026, New York time. This protocol specifies how to evaluate the original four development-selected strategies and the five validation-selected Track B finalists. It does not select another winner, change a strategy, form a portfolio or authorize live trading.

## 1 Approval summary

| Proposed decision | Draft specification |
|---|---|
| Evaluation window | Full calendar 2026: January 1, 2026 00:00 UTC to January 1, 2027 00:00 UTC |
| Timing | Wait until the full window and required checksum-verified archives are available; no partial-year run under this draft |
| Strategies | All nine exact case-basket pairs below; original identities and complete case dictionaries unchanged |
| Primary trading assumptions | Existing hourly Binance spot engine; 20 bps one-way full-L1 costs; inherited lag1 |
| Primary hypotheses | Nine one-sided tests of positive expected arithmetic daily net return against zero-interest cash |
| Mean-return t-statistic | Newey-West/Bartlett HAC, 27 daily lags, declared small-sample variance correction |
| Primary p-values | Null-centered circular block-bootstrap-t; 10,000 replications; 28-day blocks; synchronized across all nine |
| Multiple testing | Holm step-down across all nine primary hypotheses together; familywise alpha 5% |
| Bootstrap intervals | Marginal 95% intervals for mean return, daily Sharpe and complete-day annualized geometric growth; separate approximate simultaneous mean lower bounds |
| Economic criterion | Positive compounded full-period net total return at 20 bps |
| **New proposed risk budget** | Observed-hour maximum drawdown no greater than **40%** |
| **New proposed turnover budget** | Annualized full-L1 turnover no greater than **1.5 times the larger saved development/validation annualized turnover** for that exact strategy |
| Sensitivities | Existing cost/delay scenarios remain diagnostic only; they cannot replace the primary test or reselect candidates |

**The 40% drawdown ceiling and 1.5-times turnover multiplier are proposed governance tolerances requiring your approval.** They are not inherited selection rules, optimized estimates or universal standards. They do not remove any of the nine strategies before evaluation. You may change them before approval and before any OOS access, with a new draft version.

The machine-readable specification is `protocol_draft.json`; exact case dictionaries and unrounded turnover budgets are in `strategy_registry.json`. This draft's status must not be mistaken for an approved execution freeze.

## 2 Research questions and limits of the test

- **Track A:** how do the four unchanged outputs of the original development-only procedure perform in the later period?
- **Track B:** how do the five unchanged development-plus-validation-selected outputs perform in the later period?

Report individual outcomes and descriptive counts by track. One later period cannot establish that either selection procedure generally works across markets or regimes. Different baskets and settings prevent a simple Track A-versus-B table from establishing causal or statistical superiority. No paired superiority hypothesis, average-return portfolio, overall primary strategy or ensemble weight is introduced here.

**2026 is not pristine project-wide OOS.** Earlier versions of the broader project inspected January-September 2026. This restart has not loaded or evaluated that period, but it cannot erase prior project-wide exposure. Label the eventual analysis a **retrospective temporal evaluation of frozen strategies, with prior 2026 exposure disclosed**, not a blind or prospective discovery test. Holm correction addresses the nine specified claims, not the earlier universe/configuration search or that exposure. A genuinely prospective confirmation requires observations arriving after the final approved freeze.

## 3 Immutable strategy registry

All coin names below denote historical economic slots against USDT, in the displayed order. Full instrument identifiers and every existing case field are retained in the registry.

| ID | Basket | Frozen configuration | Eight coin slots |
|---|---:|---|---|
| A01 | 4645 | `buffered_momentum_h0672_r168_b025` | BTC, ETH, SOL, LUNA, FTM, TRX, LINK, LTC |
| A02 | 4645 | `momentum_h0672_r072` | BTC, ETH, SOL, LUNA, FTM, TRX, LINK, LTC |
| A03 | 1159 | `reversal_h1440_r168` | BTC, ETH, SHIB, DOT, ADA, MANA, FIL, VET |
| A04 | 4444 | `trend_long_short_h0672_r024` | BTC, ETH, SOL, LUNA, AVAX, FTM, FIL, VET |
| B01 | 2323 | `buffered_momentum_h0672_r024_b025` | BTC, ETH, BNB, XRP, DOGE, FTM, AXS, VET |
| B03 | 2457 | `momentum_h2160_r072` | BTC, ETH, BNB, XRP, FTM, MATIC, AXS, LTC |
| B04 | 6064 | `reversal_h2160_r168` | BTC, ETH, DOT, LUNA, AVAX, MANA, FIL, VET |
| B05 | 2330 | `trend_long_cash_h0672_r168` | BTC, ETH, BNB, XRP, DOGE, TRX, GALA, LINK |
| B06 | 2495 | `trend_long_short_h0672_r168` | BTC, ETH, BNB, XRP, TRX, MANA, GALA, LINK |

A01-A04 preserve original `run_01`-`run_04`. B02 remains the unselected factor-residual family; do not add it or renumber the other B identifiers. All nine are fixed nonfactor trailing-return strategies: **there are no monthly fitted-model refits** in this candidate set.

Preserve legacy **LUNA/LUNC, not Terra 2**, and the documented **FTM/S** and **MATIC/POL** lineages. A historical slot label is not an assertion that its old ticker remains tradable. Keep source-backed cash gaps, rewarm rules, forced exits and permanently vacant slots; do not replace failed assets with later survivors.

## 4 Window and execution invariants

The proposed accounting interval is `start < bar_end <= end`, from January 1, 2026 00:00 UTC through the January 1, 2027 00:00 UTC endpoint; exclude candles opening at the ending cutoff. New York equivalents are **December 31, 2025 at 7 p.m. EST** and **December 31, 2026 at 7 p.m. EST**. A complete year supplies 8,760 elapsed hours and 365 complete UTC return days.

The end is future-dated as of this draft. Do not silently substitute the present date, the former September cutoff or a period chosen from performance. An earlier partial-year evaluation requires a separate user-approved, pre-access amendment with its exact latest-completed-hour UTC cutoff, New York equivalent and partial-year label. Do not repeatedly inspect and extend the window until a favourable result appears.

Use the unchanged simulator, metrics and strategy APIs:

- Generate targets inside each exact eight-coin basket using the full October 2021 onward warm-up and inherited lifecycle rewarm. Do not slice thirty-coin weights or discard inactive slots.
- Keep the January 3, 2022 00:00 UTC scheduling epoch and phase zero. Weekly decisions are Monday 00:00 UTC. The 72-hour configurations remain on their elapsed-time schedule, not a newly restarted three-day or weekly calendar.
- Keep average rank ties, demeaning, full-L1 normalization, gross exposure constraints and whole-target buffering. A buffer skips the entire proposed rebalance only when full-L1 change is below 0.25; lifecycle exits override buffering.
- Trend allocations remain fixed at one eighth per slot; inactive allocations are not redistributed.
- Each OOS path starts independently from cash and pays one terminal liquidation. No monthly/yearly resets, cash-reset time shards or new risk-slice simulation are permitted.
- Lag1 retains the idealized observed-close convention; it is **not** a literal extra-hour delay. Lag2 is the inherited additional-hour stress.
- Costs use full-L1 target changes, including initial, forced and terminal trading. Ordinary drift-maintenance trading, realistic fills, funding, borrow and capacity are not fully modeled.

Run the seven existing scenarios for every fixed pair: lag1 at 0/5/10/15/20/40 bps, plus lag2 at 20 bps. This produces **63 financial work keys**, implemented using 18 zero-cost base simulations before cost transformations. This is not permission to rerun the 169-case grid or search more baskets.

## 5 Data and access gates

Drafting and synthetic statistical tests may use metadata and saved 2022-2025 summaries only. **No 2026 prices, raw archives, price panels, saved 2026 results or return paths may be loaded for this task.**

After explicit approval, a separate execution study must, in order:

1. Record the user's approval of the exact protocol/registry hashes and proposed budgets. Approval cannot be inferred from this draft, a document's wording or the existence of a freeze receipt.
2. Implement and test the new owned adapter without opening 2026. Pin its code, inherited engine hashes, environment, output schema, source policy and inference reference before market-data access. This draft does not yet contain a complete trading runner.
3. Record first price access under the new study's ownership. Use the same hourly Binance spot source, official monthly archives and SHA256 sidecars. Reuse historical verified bytes read-only; do not regenerate old study receipts or modify old caches.
4. Require the complete declared window. Missing archives, checksum failures or unexplained gaps **stop evaluation**; do not fill, shorten, substitute a coin or silently fall back to API candles. Wait if required final-year archives are unavailable.
5. Verify the six aligned DataFrames (`prices`, `quote_volume`, `tradable`, `observed`, `hold_allowed`, `mandatory_exit`), whole-venue `decision_allowed` Series, UTC index, attributes, raw NaNs and audited halt/lifecycle treatment. New lifecycle events need source-backed documentation, not a favourable assumed alias or conversion.
6. Seal prepared inputs before simulation; independently reconcile holdings/P&L, full-L1 costs, compounding and metric scopes afterward. Preserve failed and unavailable work keys.

Known unavailable coin slots can be cash under the inherited masks. They are not unexplained missing data. Conversely, a failed or missing evaluation must never be labeled a valid all-cash strategy.

## 6 Performance and inference scopes

Full observed-hour paths determine gross/net total return, elapsed-time CAGR, drawdown depths/episodes/recovery, turnover, costs and exposure. Retain the established additional metrics, including volatility, Sortino, Calmar, expected shortfall, worst day/week, time underwater, cash participation and BTC alpha/beta with their existing definitions.

Inference uses each strategy's **same-path, complete, contiguous UTC daily net simple returns**, including cash days and their actual costs. Keep the identical 365-day calendar for all nine. Do not discard losing/flat days, compress missing dates, relocate fees, prorate boundary observations or resimulate a daily-risk slice. If the declared common complete-day scope cannot be supplied, block final inference rather than silently shorten it. Report full elapsed days, complete risk days and any boundary partials explicitly.

Sharpe remains the established descriptive convention, `sqrt(365) × mean(daily net return) / sample_SD(daily net return)`, with zero risk-free rate. Its small-sample/dependence uncertainty is reported separately. The mean-return HAC test below is **not** obtained mechanically from annualized Sharpe. The inherited BTC-attribution HAC(7) convention is a separate metric and must not be confused with this new HAC(27) mean test.

## 7 Primary hypotheses and HAC t-statistics

For each fixed strategy i, test:

\[
H_{0i}: E[r_{it}]\leq 0,\qquad H_{1i}:E[r_{it}]>0.
\]

The estimand is expected **arithmetic daily net return against zero-interest cash**. This is not a test of positive expected geometric growth, BTC alpha, arbitrage, or superiority over another strategy.

With n daily observations, demean the returns and calculate:

\[
\hat\gamma_k=\frac1n\sum_{t=k+1}^{n}(r_t-\bar r)(r_{t-k}-\bar r),
\]

\[
\hat\Omega=\frac{n}{n-1}\left[\hat\gamma_0+
2\sum_{k=1}^{27}\left(1-\frac{k}{28}\right)\hat\gamma_k\right],
\quad SE_{HAC}=\sqrt{\hat\Omega/n},\quad
t_{HAC}=\bar r/SE_{HAC}.
\]

Freeze the 27-lag Bartlett bandwidth; do not choose it from OOS autocorrelations. The `n/(n-1)` term is a declared variance correction, not an exact finite-sample Student-t calibration. Report `1 - Phi(t_HAC)` as a **secondary normal-approximation p-value only**. It cannot replace the primary bootstrap p-value when it is smaller. The official [HAC implementation reference](https://www.statsmodels.org/stable/generated/statsmodels.stats.sandwich_covariance.cov_hac.html) describes the Newey-West estimator; the bandwidth and test choice here are proposed design decisions.

## 8 Primary bootstrap test

Use **10,000 circular moving-block replications**, block length **28 days**, and `numpy.random.Generator(numpy.random.PCG64(20261015))` in fixed registry order A01, A02, A03, A04, B01, B03, B04, B05, B06.

For each replication, draw `ceil(n/28)` independent uniform start indices in `[0,n)`, concatenate 28-day blocks modulo n, and truncate to n observations. Apply that **same index sequence to all nine strategies**. This preserves observed within-block time dependence and joint cross-strategy dependence under the resampling model.

Null-center each strategy, `u_it = r_it - observed_mean_i`. Resample those centered daily returns and recompute the identical HAC t-statistic for every replicate. The one-sided primary p-value is:

\[
p_i=\frac{1+\#\{b:t^*_{ib}\geq t_{HAC,i}\ \text{or }t^*_{ib}\text{ is undefined}\}}{10001}.
\]

The plus-one rule prevents a reported zero Monte Carlo p-value. It does not make a dependent bootstrap test exact. Do not add replications, change the seed/block length or switch primary tests in response to a borderline result. Record exceedance counts, invalid-draw counts and Monte Carlo resolution; a numerical result close to a rejection threshold must retain its simulation-precision caveat.

Resample realized daily net-return vectors, **not prices**. Do not regenerate signals, reselect strategies, re-estimate costs from resampled prices or add a fresh entry/liquidation fee at every block boundary. Circular end-to-start joins are a resampling device, not actual trades. The statistical premise is approximately stationary, weakly dependent returns; [block-bootstrap methodology](https://mathweb.ucsd.edu/~politis/StatSci03.pdf) does not guarantee that future crypto regimes resemble the observed year.

## 9 Bootstrap intervals

Reuse exactly the same index matrix on the **uncentered original net returns**. Use linear empirical quantiles.

| Quantity | Interval specification | Interpretation |
|---|---|---|
| Mean daily net return | Marginal 95% studentized interval using `T* = (mean* - observed_mean) / SE_HAC*`; endpoints `mean - q(.975) × SE_HAC` and `mean - q(.025) × SE_HAC` | Approximate individual-mean uncertainty |
| Daily-return net Sharpe | Marginal 95% percentile interval of `sqrt(365) × mean* / sample_SD*` | Descriptive, conditional on the observed strategy path |
| Complete-day annualized geometric growth | Marginal 95% percentile interval of `expm1((365/n) × sum(log1p(r*)))` | Not arithmetic mean multiplied by 365; equivalence to full-hour CAGR requires complete-scope reconciliation |
| Mean net-return lower bounds | `mean - q(1 - .05/9) × SE_HAC` for each strategy | Approximate simultaneous 95% lower bounds by Bonferroni; not Holm-inverted intervals and not another success gate |

The ordinary 95% intervals are **marginal**, not jointly 95% across all nine. The simultaneous lower bounds are separately labeled, use a more conservative construction and need not produce the identical decision as Holm-adjusted p-values.

**Do not attach a daily-bootstrap interval to hourly maximum drawdown.** Report its actual observed-hour magnitude, peak/trough/recovery, duration and censoring. A reordered daily sequence is a different path-dependent risk object, not uncertainty for the recorded hourly drawdown episode.

Bootstrap intervals condition on the realized selected strategy returns. They do not rerun the earlier universe/parameter selection or correct its selection bias. With one year, there are only about thirteen block-lengths of information. Wide intervals and no Holm rejections are possible even for a genuinely positive effect; nonsignificance is not evidence that the edge is exactly zero.

## 10 One multiple-testing family

Apply **Holm step-down at familywise alpha 0.05 across all nine primary 20-bps hypotheses together**, not separately by Track A and Track B. Sort primary p-values ascending, breaking ties by the fixed registry order. With m = 9:

\[
p^{adj}_{(j)}=\min\left(1,\max_{k\leq j}\{(9-k+1)p_{(k)}\}\right).
\]

Statistical support requires the adjusted primary p-value to be at most 0.05, a valid **observed HAC t-statistic greater than zero**, and valid positive-direction inference. Keep **m = 9** if a strategy is flat, fails or has undefined inference: conservatively enter p = 1 for adjustment and retain its explicit status, not a fabricated computed p-value. If a source/engine failure blocks the evaluation, do not issue final family-level claims from the surviving subset.

[Holm's procedure](https://www.ime.usp.br/~abe/lista/pdf4R8xPVzCnX.pdf) accommodates dependence provided the underlying p-values are valid. Here the bootstrap calibration is approximate, so an exact finite-sample 5% guarantee is not claimed. Correction of these nine claims is also not correction for prior project-wide searching or data exposure; the [selection-bias literature](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf) remains relevant.

Cost sensitivities, lag2, monthly/quarterly summaries, beta/alpha and validation-to-OOS comparisons are **descriptive diagnostics only**. No unadjusted secondary p-value, attractive subperiod or sensitivity winner may become an alternative route to declaring success. New formal contrasts require a separately predeclared hypothesis family before access.

## 11 Success criteria and outcome labels

Report each component separately; do not collapse an unprofitable result, a risk breach and statistical uncertainty into one unexplained failure label.

| Component | Proposed requirement |
|---|---|
| Validity | Full declared scope, source and code gates, coverage and independent accounting/inference checks pass |
| Economic outcome E | Compounded full-hour net total return at 20 bps is strictly positive |
| Statistical evidence S | Valid bootstrap test, observed HAC t-statistic greater than zero, and Holm-adjusted primary p-value at most 0.05 |
| Drawdown budget D | Observed-hour maximum drawdown is at most 40% |
| Turnover budget T | Annualized full-L1 turnover is at most 1.5 times the larger saved development/validation value for the exact fixed pair |

The unrounded turnover budgets and their source values are retained per strategy in the registry. Annualization uses full-period turnover divided by elapsed calendar days times 365, including entry and liquidation. Differences in period length must not be used to relocate or remove those fees. There is **no additional Sharpe floor**.

- **Meets proposed research acceptance:** validity and E, S, D and T all pass. This is not proof of deployability or a pristine out-of-sample discovery.
- **Economically positive but statistically inconclusive:** E, D and T pass, inference is valid, but Holm does not reject. Do not call this proof of no edge or relax the threshold afterward.
- **Economic criterion not met:** realized net return is zero/negative. Positive arithmetic-return evidence, if present, does not override negative compounded wealth.
- **Risk or turnover expectation not met:** D or T breaches its approved budget, even if the expected-return test rejects. Keep any economic/statistical evidence visible separately.
- **Inference unavailable:** no fabricated Sharpe/t-statistic or statistical pass. Distinguish this from a valid non-rejection.
- **Evaluation blocked or not evaluable:** unexplained data, code, scope or accounting failure. Do not label it a market-performance failure or silently omit it.

A Track A/Track B count of passing cases is descriptive, with denominators four and five and substantial overlap/dependence. Even if one or more strategies meet all criteria, do not claim that an entire family or selection procedure has generally been validated. Do not automatically promote the largest OOS Sharpe into another supposedly unbiased winner.

## 12 Degenerate paths and numerical rules

- Cash days stay in the sample. A genuine all-cash path has zero return, undefined Sharpe/t when variance is zero, conservative adjustment p = 1 and no economic/statistical pass.
- Nonpositive/nonfinite observed HAC variance makes the t-test unavailable; no infinite t-statistic is fabricated. Undefined p = 1 is explicitly a conservative adjustment convention.
- Undefined bootstrap-t draws count as primary tail exceedances rather than being silently discarded. If any occur, studentized mean intervals and simultaneous bounds are unavailable.
- If any bootstrap Sharpe is undefined, its percentile interval is unavailable; retain the invalid count rather than conditioning on valid draws.
- Nonpositive/noncompoundable full-hour wealth is an economic/risk failure. Do not fabricate geometric growth, bootstrap inference or a post-bankruptcy trading path; preserve status and p = 1 for the fixed family.
- Missing/nonfinite required input returns are data errors, not cash. Use the same exact calendar and declare scope failures; do not fill or compress time.

Report undefined values as unavailable with reasons, not as zero. Reference-module synthetic samples can be shorter than a year to test mathematics, but **a synthetic test does not relax the future runner's 365-day scope requirement**.

The pure `analyze_nine` reference accepts an **all-valid numeric matrix only**. A future failure-aware adapter must retain all nine identity/status slots and use the same 365-day bootstrap index matrix on valid columns only. A bankrupt or unavailable strategy receives no fabricated returns, no zero-filled column and no bootstrap path; only its conservative **p = 1 for the nine-way adjustment** is supplied. Independently test that orchestration before access. An explicit economic bankruptcy need not prevent analysis of other valid strategies; a shared calendar, source or engine defect still blocks final claims.

## 13 Evaluation outputs and acceptance audit

After approval and eventual execution, retain:

1. All **63** financial scenario/status rows and **nine** primary inference rows, including failures and flat/undefined cases.
2. For each primary row: mean/SD, n, HAC bandwidth/variance/SE/t, raw bootstrap p, normal-approximation p (secondary), Holm p/rejection, every interval with its marginal/simultaneous label, invalid-draw/exceedance counts and E/S/D/T flags.
3. Joint dated daily returns; full observed-hour return/position/turnover/cost paths; target and lifecycle/forced-exit events; exact registry; bootstrap seed, index-matrix hash and software versions.
4. Full inherited performance/risk/exposure metrics and drawdown dates/durations, plus separate Track A/B descriptive tables and cost/delay diagnostics.
5. User approval and first-access chronology, source/code/environment/prepared-data seals, checksum/gap audits and prior-artifact preservation evidence.
6. Independent verification of signal/schedule parity, future-prefix invariance, fee/P&L accounting, complete-day compounding and a separate implementation of the primary inference/adjustment on the saved nine-series matrix.
7. An executed notebook, readable report and final acceptance receipt. A launched job or partially written result is not a completed evaluation.

This draft includes a pure inference reference and synthetic tests, not an acquisition/backtest runner. Its tests must not read project prices or OOS returns. No result table should be populated with invented 2026 observations or placeholder zero performance.

## 14 Approval and amendments

Approval must explicitly cover the **full-calendar window**, **all nine unchanged pairs**, **primary test/interval/multiplicity choices**, and **new 40%/1.5-times budgets**, tied to the final draft and registry hashes. Until then, `approved = false` and OOS access remains disabled.

Before access, any changed policy gets a new retained draft version and explicit approval. After access, do not change candidates, parameters, periods, budgets or primary inference to rescue results. A necessary technical correction requires a logged cause, scope/impact assessment, amended code hashes and transparent rerun of affected work under the unchanged economic hypotheses. Preserve superseded evidence and disclose which outcomes had already been seen.

No publication, Git push, orders, paid compute, scheduled monitoring or automatic future run is authorized. Even approval of a full-year protocol does not authorize pretending future candles or unpublished archives already exist.

## Method references

- Newey-West HAC estimator: [official statsmodels documentation](https://www.statsmodels.org/stable/generated/statsmodels.stats.sandwich_covariance.cov_hac.html). The specific 27-lag design and small-sample multiplier are stated above.
- Politis (2003), [The impact of bootstrap methods on time series analysis](https://mathweb.ucsd.edu/~politis/StatSci03.pdf).
- Holm (1979), [A simple sequentially rejective multiple test procedure](https://www.ime.usp.br/~abe/lista/pdf4R8xPVzCnX.pdf), university-hosted copy of the original paper.
- Phipson and Smyth, [Permutation p-values should never be zero](https://gksmyth.github.io/pubs/PermPValuesPreprint.pdf). Its Monte Carlo lesson does not turn this dependent bootstrap into an exact permutation test.
- Bailey and Lopez de Prado (2014), [The deflated Sharpe ratio](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf). No deflated-Sharpe statistic is claimed to have been calculated here.

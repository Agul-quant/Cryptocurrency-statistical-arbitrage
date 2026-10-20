# Research methods and interpretation

## Periods and frozen strategies

- Development: **1 January 2022–31 December 2023**, 730 UTC days.
- Validation: **1 January 2024–31 December 2025**, 731 UTC days.
- OOS: **1 January–30 September 2026**, ending 1 October at 00:00 UTC,
  273 days. This is a partial-year interval, not a full-year or live record.

The frozen strategy IDs are A01–A04 and B01/B03/B04/B05/B06. B02 is an empty
family slot because no candidate qualified; it is not a tenth strategy.
Track A selections used development only. Track B selections used development
eligibility and validation; their validation statistics are selection statistics.

### Headline and interpretation

All four A strategies lost compounded net wealth in 2024–2025 validation;
their raw √365 Sharpe ratios ranged from −0.22 to −0.64 (−0.18 to −0.53 under
√252). All five B strategies
lost compounded net wealth in January–September 2026. This is the headline
pattern across the three reports, not a claim that every individual period or
arithmetic-return statistic was negative. In particular, A03 passed the original
2026 acceptance test after losing in validation, and B06's 2026 raw √365 Sharpe
was slightly positive (0.05; 0.04 under √252) despite its compounded loss.

This failure to generalize is consistent with fitting basket/parameter choices
to the selection period. It does not establish that search alone caused the
failures. Differences in basket, lookback, cadence, family, realized regimes
and idealized execution remain relevant. No OOS winner is newly promoted.
Project-level follow-up headlines orient readers across periods; they were not
inputs to the original development selections. Original strategy definitions,
results, selections, risk limits and acceptance flags remain unchanged.

**Data-use note:** These are fixed historical evaluation periods. Some 2026
observations had been inspected during the wider project. The nine-strategy
evaluation and subsequent cohort, attribution and factor diagnoses share these
observations; those diagnoses are not additional independent tests. Period
labels or frozen file hashes do not remove prior-data-use or selection bias.

## Trading and accounting

Primary cost is **20 bps one-way on full-L1 traded weight changes**, including
entries, forced changes and terminal liquidation. Saved cost sensitivities use
0/5/10/15/40 bps; an additional-hour delay is a separate execution sensitivity.
The inherited lag1 fill is an idealized observed-close fill, not a guaranteed
real-world one-hour delay. Each evaluation period starts from cash and retains
its full warmup and scheduling epoch. Weekly scheduling uses elapsed calendar
time, not every seventh observed row.

Cross-sectional ranks, inactive allocations, whole-target buffering, lifecycle
cash gaps, migrations, forced exits and shared decision suspensions follow the
fixed engine. Remaining trend positions are not rescaled to use inactive slots.
No price gap is silently filled and no failed economic slot is replaced.
Theoretical shorts omit borrowing, funding and margin constraints. Liquidity,
capacity, realistic execution and weight-drift maintenance costs are not fully
modeled. Dollar neutrality does not imply market-beta neutrality.

Returns compound on the accounting path. Sharpe and risk statistics use complete
UTC-day returns, including weekends. The established 365-day convention remains
the frozen result convention; the reports additionally show the course's √252
Sharpe scale as described below. Annualized CAGR extrapolates the observed
interval; it is not a forecast. Full-L1 turnover is not divided by two.

## Sharpe annualization comparison

For the **same** complete UTC daily observations, define
`S365 = sqrt(365) × mean(d) / sample_std(d, ddof=1)` and
`S252 = S365 × sqrt(252/365)`, where d is raw simple daily strategy return for
the zero-cash comparison or daily net return minus `0.03/365` for cash excess.
The conversion factor is approximately **0.8309097176613772**. This does not
remove weekends or claim that crypto trades only 252 days a year. It supplies
both the calendar-crypto convention and course comparison explicitly.

For example, A01's development raw Sharpe is **1.83818 / 1.52736** under
√365 / √252; its cash-excess Sharpe is **1.73402 / 1.44081**. The reports label
both scales in performance tables and numeric Sharpe comparisons. Positive
constant rescaling leaves signs and rankings unchanged. Where a saved source
provides only rounded group medians, the converted display is marked
approximate rather than implying recovered full precision.

Sharpe confidence-interval endpoints are multiplied by the same positive
factor; these are not independent bootstrap results or a new testing family.
Counts, rank correlations, t-statistics, p-values and acceptance decisions are
not rescaled. Cash accrual remains ACT/365F, and existing elapsed-calendar CAGR,
volatility and 365-times-daily-intercept alpha definitions remain unchanged.
The original query evidence and financial results are retained; added display
projections and `sharpe_conventions.csv` exports expose the arithmetic comparison.
Square-root annualization is a reporting convention, not a claim of independent
daily returns; HAC and block-bootstrap inference retain their established rules.

## Per-coin attribution

Each interval's gross coin contribution is held weight times audited coin
return. Ordinary, forced and terminal transaction costs are allocated to the
coin that incurred them. Contributions are linked on prior **net strategy NAV**;
the eight net coin contributions sum to the strategy's full compounded net
return. Gross linked contributions are therefore not a separately compounded
zero-cost strategy return.

Confidence intervals use **4,000 seeded 28-day circular block samples** per
period, synchronized across strategies and coins (seed 20261016). Each draw
rebuilds net NAV and relinks all gross, fee and net components. No strategy
signals or new block-boundary trades are generated. Reported percentile intervals
are marginal conditional intervals, not universe/configuration-search-adjusted
profitability claims. Invalid draws are counted rather than discarded.

## Joint basket alpha and betas

The dependent variable is saved net simple daily strategy return. Regressors
are an intercept and the eight basket coins' contemporaneous simple daily
returns. Annual alpha is **365 times the arithmetic daily intercept**, not CAGR.
Betas are conditional historical sensitivities, not capital weights, causal
effects or recommended hedge sizes.

Regressions exclude a day when any required factor return is unknown; full
strategy performance and attribution retain all days. No missing factor is
zero-filled or bridged across a lifecycle event. Calendar-aware Bartlett
**HAC(27)** intervals keep actual calendar lags and use an n/(n−k) covariance
correction. HAC(7) is a same-design sensitivity. BTC-only full-period HAC(7)
results remain a benchmark; matched-sample BTC-only HAC(27) results separate
factor-specification effects from sample effects.

The 243 joint coefficients form one global two-sided Holm family, with
Bonferroni simultaneous intervals also supplied. These coefficient corrections
are separate from the original nine-strategy acceptance tests and do not adjust
for the entire basket/configuration search. Standardized condition numbers,
VIF, sample exclusions, leverage and Cook's distance disclose model reliability.
Heavy-tailed influential observations can make asymptotic intervals fragile
even when collinearity is acceptable.

## Reproduction boundary

`verify_project.py` checks the current package checksums, result coverage and
report links without fitting a model or accessing the network. `run_research.py`
reconstructs the nine fixed strategies on the included normalized hourly panels
and reconciles all three primary-cost periods. It does not rerun the complete
basket-selection campaign, select a new strategy, or fetch raw exchange archives.
`reproduce_diagnostics.py` uses the compact daily statistical inputs to
reconcile the factor models and coin-attribution intervals. Saved broader cohort tables
provide the report's screening context and are not independent replications.

The [fixed all-22-coin momentum protocol](FIXED_ALL22_PROTOCOL.md) is a separate
**draft awaiting explicit approval to run**. It proposes one 28-day weekly
momentum specification without a new basket or parameter sweep. It does not
authorize a backtest, alter the frozen-nine runner or create an all-22 result.
Its already-inspected historical comparison windows cannot supply fresh
independent confirmation of a rule proposed after seeing the project results.


## Cash benchmark comparison

### Benchmark and unchanged trading record

The additional comparison uses **3% nominal annual cash**, compounded daily
with **ACT/365F**: each calendar day's simple cash return is `c = 0.03 / 365`.
It is not a 3% effective annual rate. Compounded cash growth is approximately
**3.0453% over 365 days**, **6.1834% over 730 development days**,
**6.1921% over 731 validation days**, and **2.2691% over 273 OOS days**.
Leap-year validation still divides the nominal rate by 365, not 366.

This is a hypothetical benchmark in **USDT-quoted units**. It is neither a
historical deposit/Treasury/lending yield series nor a claim of an available
risk-free USDT product. Reading it as a USD cash comparison assumes USDT/USD
parity; no currency conversion or depeg hedge is modeled. No interest is
credited to unused strategy cash or short-sale proceeds. Positions, trades,
transaction costs, borrow/funding omissions, per-coin P&L, raw results, frozen
selections, risk limits and original acceptance tests are unchanged.

### Arithmetic excess versus relative wealth

For saved complete-UTC-day net strategy returns `r[p,t]`, arithmetic excess is
`d[t] = r[p,t] - c`. **Cash-excess Sharpe** is
`sqrt(365) * mean(d) / sample_std(d, ddof=1)`. The original report's raw Sharpe
is retained explicitly as a zero-cash benchmark comparison, not silently
replaced. The main nine-strategy period tables present the raw and cash-excess
comparisons side by side; the supporting cash tables retain the full uncertainty
and diagnostic results. Because `c` is constant, subtracting it changes the mean
but not the standard deviation. Sharpe's historic formulation uses the average and standard
deviation of a differential return, rather than a compounded return difference.
[William F. Sharpe, The Sharpe Ratio](https://web.stanford.edu/~wfsharpe/art/sr/sr.htm).
The square-root annualization remains the established reporting convention;
serial dependence is addressed separately by HAC and block-bootstrap inference.

Compounded strategy wealth is `W[p] = product(1 + r[p,t])` and cash wealth is
`W[c] = (1 + c)^n`. **Wealth-relative excess return** is `W[p] / W[c] - 1`.
It is not `W[p] - W[c]`, nor the compounded product of `1 + d[t]`.
**Relative annualized growth** is `(W[p] / W[c])^(365/n) - 1`.

Relative drawdown is measured from the daily wealth-ratio path
`product((1 + r[p,t]) / (1 + c))`, including initial NAV 1. Its peak, trough,
recovery and underwater durations use **daily endpoints**. It is therefore not
interchangeable with the original report's hourly maximum drawdown. A matching
raw daily drawdown is supplied for a like-clock comparison; original hourly
risk metrics stay unchanged. These daily figures make no intraday-loss claim.

### Cash-adjusted factor models

The regression comparison subtracts the same daily cash return from **both**
the dependent strategy return and every coin factor:

```text
r[p,t] - c = alpha_cash_daily + sum_i beta_i * (r[i,t] - c) + residual[t]
alpha_cash_annual = alpha_raw_annual + 0.03 * (sum_i beta_i - 1)
```

Annual alpha is 365 times the daily arithmetic intercept, not CAGR. With a
constant cash rate and unchanged sample, betas, their standard errors and their
marginal intervals stay unchanged up to numerical precision. Alpha is not
generally obtained by simply subtracting three percentage points. Its standard
error and interval are recomputed using the **full coefficient covariance**,
including alpha–beta and beta–beta terms; they are not an interval translation
by a fixed annual-rate subtraction.

Joint eight-coin and matched-sample BTC comparisons retain the original
calendar-aware HAC(27) covariance with the finite-sample correction and HAC(7)
sensitivity. Full-period BTC-only comparisons retain their HAC(7) convention
without the correction. Factor-day exclusions and calendar gaps are identical
to the corresponding raw models; no missing factor is filled and full-period
performance is not shortened to the regression sample.

### Uncertainty and separate testing families

Mean arithmetic cash excess uses a calendar-aware Bartlett **HAC(27)**
intercept test with `n/(n-1)` covariance correction and approximate normal
95% intervals. The reported t-statistic uses that standard error; its p-value
is asymptotic normal, not a finite-sample Student-t claim. The **27
strategy-period means** form one new Holm-corrected family, separate from the
original nine-strategy acceptance tests.

The **243 cash-adjusted joint coefficients** form a separate Holm family,
with Bonferroni simultaneous intervals also supplied. They are distinct from
the 243 raw coefficients. Although beta point estimates and marginal intervals
stay unchanged, Holm-adjusted p-values can change because the family contains
new alpha p-values. BTC comparison intervals are marginal diagnostics, not an
additional collection of selected profitability tests.

Wealth-relative return, relative annualized growth and cash-excess Sharpe use
**4,000 synchronized 28-day circular-block samples** per period, seed 20261016
reset for each period. Strategy daily returns are sampled; the cash rate is not.
Every draw retains the period's deterministic number of cash-accrual days and
rebuilds its compounded wealth. No signals, positions or block-boundary trades
are rerun. Intervals are marginal 95% percentiles. Invalid draws are counted
per statistic; any invalid draw makes that statistic's interval unavailable,
rather than silently discarding a draw.

These are conditional comparisons on the same fixed historical observations,
not additional independent tests, basket/configuration-search-adjusted evidence,
or grounds to select another winner. The raw selection statistics and original
acceptance outcomes remain intact. Run `python scripts/reproduce_cash_excess.py`
to recompute and reconcile the seven checked CSV tables and two JSON results
from pinned saved daily inputs; output is restricted to `local_outputs/`.

# Research methods and interpretation

## Baskets, periods and frozen selections

The main study enumerated 6,615 eight-coin baskets from historical liquidity ranks
1–22. Every basket included BTC and ETH, two members of ranks 3–9, two of 10–16
and two of 17–22. Each basket's signals and weights were recomputed in its own
cross-section. The inherited liquidity-ranked inventory has 30 names; the study
is not an unrestricted census of every historical exchange listing.

The complete basket grid uses 168 retained definitions. The frozen IDs A01–A04 were
selected from 2022–2023 development only. B01/B03/B04/B05/B06 used development
eligibility and 2024–2025 validation; their validation statistics are selection
statistics. The nine identities use different eight-coin baskets and remain fixed; identifier gaps do not imply additional selected strategies.

| Period | Start UTC | Closing endpoint UTC | Complete days |
| --- | --- | --- | ---: |
| Development | 1 January 2022 00:00 | 1 January 2024 00:00 | 730 |
| Validation | 1 January 2024 00:00 | 1 January 2026 00:00 | 731 |
| Partial-year OOS | 1 January 2026 00:00 | 1 October 2026 00:00 | 273 |

All four Track A strategies lost compounded net wealth in validation. All five
Track B strategies lost in January–September 2026. A03's positive 2026 result
does not erase its validation loss; B06's small positive arithmetic-return Sharpe
coexisted with a compounded loss. This pattern is consistent with weak transfer
or period-specific fitting, but does not uniquely identify its cause. Baskets,
settings, market conditions and execution assumptions also matter.

The periods are fixed historical comparisons. Data had been inspected during
the wider project, and later explanatory diagnoses share those observations.
Neither a frozen file nor a period label creates additional independent tests.
No new OOS winner or deployment recommendation is selected.

The current reporting scope contains **168 retained configurations**. This scope was narrowed after evaluation; the nine frozen selections and historical development-ranked group memberships were not reselected or reranked. Grid-wide summaries are recomputed for the retained scope, not presented as a newly independent test.

## Strategy mechanics and accounting

Cross-sectional momentum and reversal rank trailing simple returns, demean the
ranks and normalize full L1 gross exposure to one. Average ties receive average
ranks. Momentum buys relative winners and shorts relative losers; reversal has
the opposite sign. Eligibility, complete lookbacks, missingness, inactivity and
whole-target deferral follow the unchanged engine. Buffered momentum skips an
entire ordinary rebalance only when full-L1 target change is below 0.25.

Time-series long/cash and theoretical long/short trend retain fixed 1/N slots;
inactive positions do not cause the remaining slots to be rescaled. Dollar neutrality is not beta neutrality. Exact nine-strategy definitions,
baskets and risk limits are in the frozen registry.

Primary costs are **20 bps one-way on full-L1 weight changes**, including entry,
ordinary changes, forced exits and terminal liquidation. Sensitivities are
0/5/10/15/40 bps and an additional execution hour at 20 bps. Lag1 is idealized
observed-close execution, not a guaranteed real-world one-hour latency; lag2
adds an hour. Full-L1 turnover is not divided by two and does not include
ordinary drift-maintenance trades that the model omits.

Each evaluated period starts flat, preserves full preceding warm-up and the
Monday scheduling epoch, and pays entry and final liquidation. Weekly means
168 elapsed hours from the established Monday epoch, not every seventh observed
row. Internal annual slices preserve continuous positions and actual fees.
Do not concatenate separately reset periods into one investable curve.

Binance Data Vision spot-USDT hourly panels provide normalized prices and quote
volume. Seven pinned panels/masks retain lifecycle permissions, migrations,
whole-venue suspensions and mandatory exits. Missing active observations do not
trigger interpolation or a shorter test. Legacy LUNA's audited 13 May 2022 00:40
quote exit remains in its 01:00 accounting bucket, with the partial exposure
adjustment. LUNA/LUNC is not Terra 2.0; FTM/S and MATIC/POL retain their economic
slots. [Data documentation](DATA.md) and the [source manifest](../data/manifest.json)
define the complete dataset.

Theoretical shorts omit actual borrowing, funding and margin constraints.
Order-book depth, impact, capacity, realistic fills and ordinary drift-maintenance
costs are not validated. Quoted returns use USDT units; a USD interpretation
assumes parity. Historical quote volume does not establish executable capacity.

## Performance and two Sharpe conventions

Gross return compounds the zero-modeled-fee path; net return compounds interval
P&L after modeled fees. Neither is the sum of daily returns. CAGR uses elapsed
calendar days; annualized volatility uses daily sample standard deviation and
√365. Maximum drawdown is positive loss depth at observed valuation endpoints,
including initial NAV. Intrahour lows and halt interiors are not observed.
Peak, trough, recovery, duration and censored recovery are retained.

For the **same complete UTC daily net returns**, including weekends, report:

`S365 = sqrt(365) × mean(r) / std(r, ddof=1)`  
`S252 = sqrt(252) × mean(r) / std(r, ddof=1)`

These are **two separate annualization conventions**. Their factor is
`sqrt(252/365) = 0.8309097176613772`; no weekend observation is removed. Positive
constant scaling preserves signs and rankings. A01's development values are
1.83818 and 1.52736. Confidence-interval endpoints use the same factor; these
are not independent resampling results or a new test family. Approximation
marks remain where a source supplied only rounded group medians.

CAGR, volatility, alpha, t-statistics, p-values and original acceptance flags do
not change with the Sharpe display convention. A constant/all-flat series has
undefined Sharpe. Arithmetic mean and compounded wealth can have different
signs. Partial-year CAGR is an extrapolation, not realized full-year performance.

## Original nine-strategy inference

Original acceptance uses positive full-period compounded net return, positive
HAC27 t, centered circular 28-day bootstrap-t Holm9 p≤0.05, hourly drawdown
≤40%, and each unchanged turnover cap. The cap is 1.5 times the maximum saved
development/validation annualized full-L1 turnover. These are evaluation flags,
not intra-run stop or trading rules. The 10,000-draw mean test uses the shared
calendar and accounts for serial dependence; Holm9 covers the nine fixed cases,
not the preceding universe/configuration search. The original flags and raw
statistical evidence remain unchanged.

The 273-day window is short, with about 9.75 nonoverlapping 28-day block lengths.
Intervals are conditional and approximate, not proof that highlighted strategies
will remain profitable. Full raw inference and risk tables are retained in
Report 3 and its companions.

## Separate fixed all-22 studies

The momentum and reversal studies each fix 22 members, a 672-hour lookback,
weekly Monday 00:00 UTC decisions, phase 0 and no buffer. Every eligible member
determines the cross-section; BTC and ETH are ordinary ranked members. Neither
selects an eight-coin subset, another parameter or a replacement winner.

Their three-period net returns are:

| Study | Development | Validation | Jan–Sep 2026 |
| --- | ---: | ---: | ---: |
| Momentum | +5.61% | −17.43% | −20.94% |
| Reversal | −33.59% | −15.66% | +9.91% |

Neither had positive net return in every period. Reversal's development hourly
drawdown was 43.69%. These are descriptive observations about unchanged paths,
not new acceptance tests or a claim that all momentum/reversal rules fail.
The reports do not promote one direction, pool tests, calculate cross-study
correlation or construct a combined portfolio.

Raw daily-mean HAC27 t-statistics are descriptive. Raw Sharpe intervals use the
saved 10,000 circular 28-day draws, PCG64 seed 20261020 reset for each period;
√252 endpoints are scaled from the same √365 draw intervals. Mean covariance
uses Bartlett HAC27 with n/(n−1), and the Sharpe intervals are marginal
percentiles. The same within-period indices drive statistics. No trade or fee
is inserted at a resampled block boundary, and invalid draws are not discarded.
No raw positive-mean hypothesis is newly tested by this publication.

BTC alpha/beta intervals for these two studies are descriptive full-calendar
HAC7 estimates, not joint 22-coin regressions. Alpha is 365 times the arithmetic
daily intercept, not CAGR. Coefficients are not selection gates.

Both studies use already-examined periods and are not fresh independent OOS
confirmation. Momentum's seal preceded its first all-22 simulation but not all
input access by existing verification tests; that chronology exception remains.
Reversal met its new-study pre-decode seal. Numerical audit success cannot
repair a procedural exception. Public raw tables are explicit field projections
of the completed studies; the trading rules and retained values are unchanged.

## Per-coin attribution and joint basket alpha/betas

Coin gross P&L is held weight times audited coin return. Ordinary, forced and
terminal fees are assigned to the coin that incurred them. Components are
linked on prior net strategy NAV, so eight net contributions sum to the unchanged
full compounded return. Gross linked contributions are not a separately
compounded zero-fee strategy return.

Attribution intervals use 4,000 seeded, synchronized 28-day circular daily-vector
samples across all nine strategies and coins, seed 20261016 reset per period.
Each draw rebuilds NAV and relinks gross/fee/net contributions. Signals and
trades are not regenerated. Invalid draws make affected intervals unavailable,
rather than being dropped. Reported 95% intervals are marginal and conditional,
not adjusted for the original basket/parameter search.

Joint regressions use daily net strategy returns, an intercept and all eight
basket coin returns simultaneously. Annual alpha is 365 times the daily
arithmetic intercept. Conditional betas are neither portfolio weights nor
causal effects. A day with any unknown required factor is excluded only from
the regression; full performance is not shortened, and missing factors are not
filled. Calendar-aware Bartlett HAC27 with n/(n−k) correction retains actual
calendar lags; HAC7 is a same-design sensitivity. Full-period BTC-only HAC7 and
matched-sample BTC-only HAC27 help distinguish sample and factor specifications.

The 243 raw joint coefficients form a separate global two-sided Holm family;
Bonferroni simultaneous intervals are also supplied. They do not correct the
original configuration/universe search or replace original nine-strategy tests.
Condition numbers, VIF, exclusions, leverage and Cook's distance disclose model
reliability; influential heavy-tailed observations can make asymptotic intervals
fragile even when collinearity is acceptable.

## Reproduction scope

`verify_project.py` checks package hashes, result coverage and links without
network or model fitting. `run_research.py` reconstructs the nine fixed
strategies and reconciles their 27 primary paths; it does not repeat the full
basket campaign or reselect candidates. `reproduce_diagnostics.py` reconciles
raw factor models and attribution from compact daily inputs. The fixed all-22
folders contain saved raw evidence; `verify_fixed_all22.py` checks those
projections without loading prices or rerunning strategies or bootstrap draws.

Current scope and preserved financial-file checks are available through `python scripts/verify_reporting_scope.py`. The current grid has 168 retained definitions; summary CSVs are in `results/retained_scope/`, with scope and source hashes in `metadata/reporting_scope.json` and `metadata/retained_scope_sources.json`. Frozen group labels are not recalculated quintiles of the narrower grid.

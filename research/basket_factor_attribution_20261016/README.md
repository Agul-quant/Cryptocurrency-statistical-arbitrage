# Fixed-nine basket attribution diagnostics

This is an explicitly **post-hoc** explanation of the same nine frozen strategy–basket pairs, not a new selection or a new out-of-sample test. Development is 2022–2023, validation 2024–2025, and the previously inspected partial-year evaluation is January–September 2026. All accounting uses the saved primary 20 bps, lag1 paths. No signal, target, order, basket, fee rule or original acceptance decision is regenerated or changed.

## Scope and evidence

- 27 strategy–period paths, 216 coin–period contributions and 243 joint regression coefficients: one intercept and eight slopes per path.
- `required_source_pins.json` traces 143 saved inputs through their old final manifests. The owned `outputs/access_freeze.json` fixes the code, design and source list before these additional fits; it does not undo earlier inspection of the underlying results.
- Saved held weights, targets, source return marks, event masks and NAV paths are used only to independently reconcile accounting. All source files and old report artifacts remain unchanged.

## What the tables mean

Per-coin gross P&L is held weight × audited asset return. Fees allocate the actual full-L1 ordinary, forced-event and terminal changes to each coin. Contributions are linked using the **net strategy NAV immediately before each accounting interval**. Net coin contributions sum to the complete period's compounded net return. Gross contributions linked on the net NAV path must not be mistaken for the separately compounded zero-fee strategy return.

Whole-period contribution intervals use 4,000 seeded, synchronized circular 28-day calendar-block samples. Each draw resamples the realized daily gross/fee component vectors and rebuilds its own net NAV before relinking contributions. It does not regenerate signals or add fees at block boundaries. The intervals are approximate marginal conditional path-resampling intervals, not independent coin returns, full trading-rule resimulations, or selection-adjusted evidence.

The joint model regresses simple UTC daily net strategy returns on an intercept and the same eight basket coins' contemporaneous simple daily returns. Alpha is 365 × the daily intercept, **not CAGR or an achieved annual return**. Each beta is a conditional historical sensitivity, not a portfolio weight, causal effect, or proposed hedge.

Factor days with any genuine intraday/lifecycle missing return are explicitly excluded from that regression, without zero filling, while full strategy accounting remains intact. The matched BTC-only model uses the exact same dates; the legacy full-period BTC-only HAC(7) values are retained separately. This prevents confusing a changed sample with a changed factor model.

Primary regression intervals use calendar-aware Bartlett HAC(27) with an n/(n−k) covariance correction and approximate normal Wald limits; HAC(7) sensitivity is also exported. Missing factor dates remain in the calendar when measuring lag distances. Model diagnostics include rank, standardized condition number, VIF, R², leverage and Cook's distance. Rank-deficient models are unavailable, not silently simplified. Extreme influential observations can still make asymptotic intervals fragile even without a multicollinearity warning.

Marginal 95% coefficient intervals are not multiplicity-adjusted. The full 243-coefficient family additionally retains two-sided Holm-adjusted HAC p-values and approximate Bonferroni simultaneous intervals. Neither procedure corrects the project's original universe/configuration/strategy search or makes this historical evaluation pristine.

## Outputs and verification

`outputs/report_payload.json` contains all period-specific report projections. CSVs retain every joint coefficient, matched and legacy BTC comparison, coin contribution, bootstrap interval, model diagnostic and included/excluded regression date. Compact daily model inputs and daily attribution components permit independent numerical inspection without distributing raw market panels or rerunning strategies.

The new reports retain the original financial results and nine-case acceptance criteria. Additional factor coefficients do not replace the original mean-return hypothesis tests, and no new winner is selected.

The executed analysis code is frozen. A technical custody amendment in `audit/volatile_log_custody.json` records that the redirected stdout log continued growing after its intermediate hash was captured. The 19 scientific outputs and original computation receipt are unchanged; no fit was repeated to address this logging issue.

Use `/Users/cosdis/.venvs/myenv/bin/python` on the originating machine. The synthetic accounting/inference tests do not load market data. A portable numerical verifier is supplied with the publication; it verifies the new daily-input diagnostics, not a complete recreation of all raw archives or the original project-wide strategy search.

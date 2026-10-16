# Final reading list — three updated reports

These are revised editions of the same three reports, not three additional research reports. The October 15 editions remain unchanged archival evidence. The updated primary reading list is:

1. **Development and robustness** — `01_development/01_development_and_robustness.pdf` (16 pages). The new appendix contains all nine frozen identities' 2022–2023 per-coin attribution and joint-basket regression diagnostics. Track B identities were selected later using validation; showing their development histories is explicitly retrospective.
2. **Validation and frozen selection** — `02_validation/02_validation_and_frozen_selection.pdf` (17 pages). The appendix covers 2024–2025 for the same nine cases.
3. **2026 evaluation and conclusions** — `03_2026_evaluation/03_2026_evaluation_and_conclusions.pdf` (20 pages). The appendix covers the previously inspected January–September 2026 partial-year evaluation.

Each PDF has a same-content offline HTML edition and source-backed interactive preview. Full-precision per-period CSV companions retain every coin, confidence interval and diagnostic; they are supporting evidence, not a fourth report.

## What was added

For each of 27 strategy–period paths: all eight coins' gross contributions, allocated fees, net contributions and conditional block-bootstrap confidence intervals; one joint annualized alpha and eight conditional betas with calendar-aware HAC confidence intervals; and the unchanged legacy BTC-only model plus a matched-sample BTC comparator.

Accounting contributions cover the complete strategy calendar. Joint regressions explicitly exclude missing factor days only from their own labeled sample. Alpha is 365 times an arithmetic daily regression intercept, not CAGR. Marginal confidence intervals are not jointly 95%; the full 243-coefficient family also retains Holm p-values and Bonferroni bands. These additions are post-hoc diagnostics, not correction for the original strategy/universe search, causal claims, new selection gates or deployment approval.

The complete method, input/output pins, frozen code and independent audits are in `research/basket_factor_attribution_20261016/` at the repository root. No strategy was rerun, no new prices were acquired, and no original baskets, targets, performance metrics, risk limits, selections or nine-case acceptance decisions changed.

The root report manifest verifies this full local revised edition. The bounded GitHub distribution has a separate verifier and documents which raw/archive and authoring artifacts are intentionally omitted. Historical frozen receipts do not claim omitted inputs are present in a public clone.

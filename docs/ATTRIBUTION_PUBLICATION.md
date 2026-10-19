# Publication and numerical inspection guide

The current edition still has **three primary reports**, one for development,
one for validation, and one for January–September 2026. Each now includes all
nine unchanged frozen strategies' accounting contributions from all eight
coins and joint-model alpha/beta confidence intervals. Only the October 16 final-report edition remains in the current checkout.
The superseded reader edition is recoverable from Git history, not duplicated
as another visible final-report folder. This October 19 cleanup does not
change any report or scientific result; see the [current publication guide](FINAL_REPORTS_PUBLICATION.md).

## What was added, and what was not changed

Each report contains 72 coin–strategy rows and 81 joint coefficient slots for
its period. Full precision CSVs beside each HTML preserve those rows, model
diagnostics, legacy and matched BTC comparisons, and every regression date.
The technical diagnostic directory retains all 216 coin contributions, 243
joint coefficients and 27 joint models across the three periods.

Original financial returns, Sharpe, turnover, drawdowns, baskets, parameters,
fees, selections and nine-case acceptance decisions are unchanged. This is
**ex-post explanatory research**, not a fresh OOS test, a causal experiment, a
new winner, a hedge recommendation or deployment approval. The January–September
2026 evaluation remains a previously inspected, nine-month historical window.

**Accounting is not regression.** Gross coin P&L and positive allocated fees
are linked using the net strategy NAV before each interval. Net contributions
sum to the period's compounded net return. These whole-period contributions
are fractions/percentage points of initial capital, not standalone coin returns
or annualized returns. Gross contributions linked to net NAV are not the
separately compounded zero-cost strategy return.

The joint regression uses an intercept and all eight frozen basket coins'
contemporaneous simple daily returns. Annual alpha is 365 times the daily
arithmetic intercept, **not CAGR or achieved annual return**. A joint beta is
conditional sensitivity holding the other seven factors fixed; it is not a
portfolio weight, causal attribution or prescribed hedge. Model fits are
in-sample descriptive diagnostics, not validated prediction models.

## Uncertainty, missingness and multiplicity

Joint and matched-calendar BTC models use approximate marginal normal-Wald
95% intervals with Bartlett **calendar HAC(27)** and an n/(n−k) correction.
Actual calendar distances remain intact across excluded factor days; missing
factor returns are not filled with zero and dates are not compressed. Full
strategy accounting and attribution calendars remain intact. Legacy BTC-only
full-calendar estimates and their original **HAC(7)** intervals are retained
separately. Compare joint against matched BTC to distinguish added factors
from changed observation dates; comparisons with legacy BTC also change the
covariance convention.

The diagnostic family contains **243 slots: 27 joint alphas and 216 betas**.
CSV exports retain Holm-adjusted p-values and approximate Bonferroni familywise
intervals for that family. Displayed marginal intervals are not adjusted.
Neither procedure corrects the earlier universe/configuration/period/strategy
search. No significance row changes the shortlist or original acceptance tests.

Coin-contribution intervals use **4,000 seeded synchronized circular 28-day
calendar-block samples**. Each draw resamples daily gross/fee component vectors
jointly, rebuilds its own net NAV and relinks contributions. It does not rerun
signals or add invented block-boundary fees. Invalid draws would make affected
intervals unavailable, never silently disappear. These are marginal conditional
path-resampling intervals, not independent coin return intervals or full
trading-rule resimulations.

Retain lifecycle exclusions, legacy LUNA/LUNC, FTM/S and MATIC/POL slot labels,
rank/condition/VIF diagnostics, leverage and Cook's distance. Low collinearity
does not remove heavy-tail or influential-observation fragility; no observation
or coin was dropped in response to its result.

## Portable checks

From the checkout root, this standard-library-only command performs **read-only
inspection/checksum verification**, without loading prices or running models:

```sh
python3 scripts/verify_latest_final_reports.py
```

It checks current file hashes and links, all 250 historical input dispositions,
19 relocated provenance JSONs and 26 exact-byte aliases, period row counts and
identities, archived-snapshot original-query preservation, scientific
receipt/custody relationships, and exactly three current PDF/HTML pairs. The
seven superseded reader files are deliberately absent; their historical hashes
and recoverable Git commit are recorded, not silently reported as current
verified bytes. The three navigation amendments retain old and new hashes.
The original local seals also describe deliberately omitted app/QA artifacts
and historical raw inputs; they are historical custody records, not assertions
that those complete archives are present or newly checked in this clone.

Historical publication manifests and verifiers remain unchanged. The old
`verify_final_reports_publication.py` and `verify_basket_attribution_publication.py`
are not current-layout entry points: use a separate checkout at commit
`b965678aacec9f653c27a41a9351dda3ee913dd6` to restore their original layout.
The current maintenance manifest is
`provenance/latest_final_reports_20261019.json`. The sealed report README
continues to describe its creation-time archival layout; the current
[publication guide](FINAL_REPORTS_PUBLICATION.md) supersedes that wording
without altering the report seal.

For **optional numerical reproduction of the saved diagnostics**, install the
pinned dependencies in `requirements.lock.txt`, then run:

```sh
python3 scripts/reproduce_basket_attribution.py
```

This imports the unchanged independent statistical oracle, verifies supplied
scientific bytes before decoding, and works only on temporary copies of the
compact daily model inputs and daily gross/fee components. It independently
reproduces all 27 joint, 27 matched BTC and 27 legacy BTC models; coefficients,
calendar HAC intervals, multiplicity corrections, contribution intervals and
sample calendars. Three large deterministic bootstrap-index arrays are not
duplicated in Git: the verifier regenerates all three from their fixed seed,
checks their exact original SHA-256 hashes, and removes temporary files after
the audit. No original study or report artifacts are overwritten.

The optional script does **not** reconstruct hourly source returns, the trading
rules, signal/target/held paths, raw market archives, or the full project-wide
strategy search. The independent accounting audit records that earlier local
reconciliation; its receipt is evidence, not a new full raw-source verification.
The 143 original source pins remain historical metadata, not 143 bundled market
files. Synthetic tests can be run without market data:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider research/basket_factor_attribution_20261016/tests -q
```

Only `outputs/computation.log` is retained from stdout logs because the explicit
custody amendment governs its final hash. Its intermediate hash was captured
while redirection was still growing; the original computation receipt is
preserved and all 19 scientific output hashes are unchanged. This was not a
refit or a change to numerical evidence.

## Offline reading and distribution boundaries

Download each top-level HTML to open it locally; GitHub's ordinary file view is
not an HTML application host. Keep each report's adjacent `exports/` directory
for CSV download links, or download the whole checkout. Each updated top-level
HTML is the same report as its PDF, not an extra study. Duplicate app builds,
private runtime caches, QA images, raw/hourly panels, held paths and the large
research campaigns are excluded. The large pre-existing cohort CSVs reuse
identical Git objects when referenced in the new dated edition.

Theoretical shorts, omitted borrow/funding and drift-maintenance trading,
idealized observed-close execution, survivor-universe/search effects and the
short retrospective evaluation still limit interpretation. Nothing here
places orders, monitors positions or contacts a mentor.

Data-derived evidence retains [NOTICE](../NOTICE.md) and
[dataset license](../licenses/DATA_LICENSE.md) attribution and non-commercial/
share-alike conditions. No new software license grant is implied.

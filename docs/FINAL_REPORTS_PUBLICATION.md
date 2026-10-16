# Publication guide: the final three reports

This is a presentation-only distribution of the completed restarted crypto
research. The final reading list contains only three reports:

1. [Development and robustness](../final_reports_20261015/01_development/01_development_and_robustness.pdf) — 2022–2023 development and robustness.
2. [Validation and frozen selection](../final_reports_20261015/02_validation/02_validation_and_frozen_selection.pdf) — 2024–2025 validation and the unchanged shortlist.
3. [2026 evaluation and conclusions](../final_reports_20261015/03_2026_evaluation/03_2026_evaluation_and_conclusions.pdf) — January–September 2026, 273 days.

Each top-level HTML beside its PDF is the same-content interactive/offline
edition. Download the HTML to open it locally; GitHub's ordinary file view is
not an HTML application host. Download the whole checkout to retain the third
report's relative CSV download links. No cloud runtime or exchange account is
needed to read the delivered reports.

## BTC alpha and beta

**Report 3, page 2**, already includes BTC alpha/year and BTC beta for every one
of the nine frozen strategies. The accompanying
[nine-strategy metrics CSV](../final_reports_20261015/03_2026_evaluation/exports/nine_primary_metrics.csv)
retains the saved numerical evidence, including regression uncertainty.

The metrics use a regression of UTC daily strategy returns on UTC daily BTC
returns with an intercept. Beta is the slope; alpha/year is the daily intercept
multiplied by 365, not CAGR, not cumulative return, and not proof of independent
alpha. There is no risk-free-rate subtraction in this saved convention.
The original regression uses HAC standard errors with seven lags. Estimated
near-zero beta does not establish realized or future risk neutrality.

For the unchanged A03 case, the saved annualized BTC alpha and BTC beta are:

| Period | Annualized BTC alpha | BTC beta |
| --- | ---: | ---: |
| Development, 2022–2023 | +27.32% | +0.0174 |
| Validation, 2024–2025 | −8.40% | −0.0259 |
| Partial-year evaluation, Jan–Sep 2026 | +37.71% | +0.0277 |

These are existing saved estimates, not new evaluations. The nine-month alpha
is an annualized regression intercept and should not be described as an
achieved full-year return. The 2026 period had previously been inspected and
is retrospective rather than pristine prospective/live evidence. No winner
was newly selected and no model was promoted for deployment.

## What this publication does and does not reproduce

The distribution contains three exact PDFs, their three exact portable HTMLs,
single-copy report CSV exports/tables, reviewed snapshots, source pins, original
delivery receipts and the original sealed publication records. A bounded set
of 84 small saved reporting inputs is under `provenance/report_source_inputs/`.
Two additional source identities map by exact SHA-256 to the already delivered
cohort CSVs, avoiding duplicate copies. The distribution manifest records all
86 source identities and their delivered locations.

Run this **read-only, standard-library-only** check from the repository root:

```sh
python3 scripts/verify_final_reports_publication.py
```

It checks every distributed file's checksum, the original final-seal identity,
all saved-source aliases, three new reader PDFs, file-size limits, the report
HTML download targets and the publication guide's internal links. It acquires
no data, runs no strategy and writes no files. This supports inspection and
checksum reproducibility of the delivered findings. It does **not** rebuild
the reports, rerun backtests, or certify full engine/data-archive reproduction.

The original `final_delivery_manifest.json` is retained byte-for-byte as
**historical evidence of the full local delivery**. It lists local app/QA
artifacts deliberately omitted from this bounded distribution. Its historical
1,004-file preservation receipt is not a claim that all those files, or the
225 earlier reader artifacts, are present or rechecked in this clone. Original
archive paths and local machine paths inside frozen receipts remain historical
metadata, not portable prerequisites. Use the new distribution verifier for
this publication, not the full-local-delivery verifier.

Excluded: duplicated authoring/runtime builds, app caches, browser screenshots,
logs, old reader PDFs, raw market archives/panels, multi-gigabyte campaign
outputs and unrelated local work. Existing pre-restart `studies/` content and
remote repository changes are preserved. Its earlier root reproduction
commands still describe that earlier distribution, not a full reproduction of
this restarted campaign.

## Interpretation and use

Primary costs remain 20 bps one-way full-L1 target changes. The saved lag1 is
an idealized observed-close fill, not an elapsed one-hour execution delay.
Theoretical shorting, omitted borrow/funding and weight-drift trades, survivor
universe/search effects, short evaluation length and execution/capacity limits
remain. Cohort summaries describe correlated strategy paths, not an investable
portfolio. Read the reports' unsuccessful results and uncertainty alongside
their point estimates.

Data-derived reports, results and exports retain the attribution and
non-commercial/share-alike conditions in [NOTICE](../NOTICE.md) and the
[dataset license](../licenses/DATA_LICENSE.md). No software license grant is
added and no live orders, publication to a hosting service, monitoring or
mentor contact is performed by this release.

# Final reports: one latest edition

The current checkout contains **one final-report edition**, `final_reports/`,
with exactly three report titles. The superseded October 15 PDFs, HTMLs and
reader directory have been removed from the current tree, not rewritten into a
new study. The directory rename is file organization and navigation only.

1. [Development and robustness](../final_reports/01_development/01_development_and_robustness.pdf) — 2022–2023, 16 pages.
2. [Validation and frozen selection](../final_reports/02_validation/02_validation_and_frozen_selection.pdf) — 2024–2025, 17 pages.
3. [2026 evaluation and conclusions](../final_reports/03_2026_evaluation/03_2026_evaluation_and_conclusions.pdf) — January–September 2026, 273 days, 20 pages.

Each adjacent top-level HTML is the same report in portable offline form, not
another version or study. Download it to open locally; GitHub's ordinary file
view is not an HTML application host. Retain each report's `exports/` directory
for its relative CSV links, or download the whole checkout. No cloud runtime
or exchange account is needed to read these files.

## What the current edition includes

For all nine unchanged frozen strategies in all three periods, the appendices
show each of eight coins' gross contribution, allocated transaction costs and
net contribution with block-bootstrap intervals; joint basket alpha and eight
conditional betas with HAC intervals; and legacy plus matched-sample BTC-only
comparisons. Full-precision CSVs include model/calendar diagnostics and the
243-coefficient multiplicity correction. The unchanged saved
[nine-strategy 2026 metrics](../final_reports/03_2026_evaluation/exports/nine_primary_metrics.csv)
remain available alongside this additional explanatory analysis.

**No baskets, parameters, signals, targets, returns, Sharpe, turnover,
drawdowns, frozen selections or original acceptance decisions changed.** No
new prices were accessed and no strategy or diagnostic model was refitted for
this cleanup. The 2026 window remains previously inspected retrospective
partial-year evidence. No new winner or deployment approval follows.

See the [method and numerical inspection guide](ATTRIBUTION_PUBLICATION.md)
for interval conventions, conditional beta interpretation and limitations.

## Current read-only verification

From the repository root:

```sh
python3 scripts/verify_final_reports.py
```

This standard-library-only check reads the current
[layout manifest](../provenance/final_reports_layout.json), verifies the
byte-identical relocation from the prior dated directory, then verifies
all 250 prior attribution-publication artifact/baseline identities through
explicit dispositions, and checks the unchanged current report and scientific
bytes. It verifies 19 byte-identical relocated provenance JSONs, 26 aliases to
unchanged latest-edition tables/exports, seven retired old reader files, and
three historical documentation/navigation amendments. The current undated
layout additionally records four narrow navigation/custody amendments; all
65 published report files remain byte-identical. Three archived snapshots still
verify that the original reviewed query objects are unchanged. It also checks
three current PDF/HTML pairs and current CSV/link targets. It fetches no data,
fits no models, runs no strategy and writes no files.

## Provenance without a second report edition

The 19 unique earlier snapshots, receipts and provenance JSONs live under
`provenance/prior_report_evidence_20261015/`. This directory contains **no PDF
or HTML reports**. The 26 earlier table/export identities refer by exact hash
to the already delivered current copies, rather than duplicating them.

The folder is deliberately undated. Publication dates remain only in
historical provenance rather than the current reader-directory name. The
65 published report files and all local sealed report artifacts were moved
without changing their bytes.

The earlier publication manifests, scientific seals and verifiers are retained
byte-for-byte as historical evidence. Their references describe the layout at
the time of creation, not missing portable prerequisites or promises that
retired files still exist. In particular, the sealed October 16 report README's
sentence saying the October 15 edition remains was true when that seal was
created; this guide and the current layout manifest supersede that
layout statement without rewriting the sealed report bytes.

To inspect or run the **historical publication checks**, use a separate
checkout at commit
[`b965678aacec9f653c27a41a9351dda3ee913dd6`](https://github.com/Agul-quant/Cryptocurrency-statistical-arbitrage/commit/b965678aacec9f653c27a41a9351dda3ee913dd6).
Do not run the old `verify_final_reports_publication.py`,
`verify_basket_attribution_publication.py` or `verify_latest_final_reports.py`
as the current-layout check. Those
scripts intentionally still require their original historical working trees.
Git history preserves the prior edition without presenting a second visible
final-report edition in the current checkout.

The original full-local seals also describe omitted app/QA artifacts, source
archives and earlier research. Their historical preservation counts are not a
claim that all raw data or complete local authoring files are bundled here.
Earlier pre-restart `studies/` material remains unchanged; it is not a second
version of the restarted final reports.

Data-derived reports and results retain [NOTICE](../NOTICE.md) and the
[dataset license](../licenses/DATA_LICENSE.md) attribution and non-commercial/
share-alike conditions. No new software license grant, orders, scheduled
monitoring, hosting publication or mentor contact is implied.

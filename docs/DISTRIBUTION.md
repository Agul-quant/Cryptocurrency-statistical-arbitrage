# Local distribution and historical evidence

There are two distributions of the same research:

1. **Git checkout:** local Python sources, tests, pinned requirements, all saved
   reports/notebooks/results, complete hourly frozen evidence, normalized
   five-minute inputs and selected paths in lossless binary parts. Run
   `python scripts/local_project.py restore` after cloning. No Git LFS or hosted
   execution is required. The five-minute raw ZIP/checksum cache is optional
   and absent from Git, with every original digest retained in provenance.
2. **Full local archive:** the same sources/results plus the original cached
   five-minute raw ZIPs/checksums and the restored large Parquets. It omits
   duplicate `data_parts/`, the `.git` directory, scratch output, Python bytecode,
   installed environments and private course material. Required local analysis
   files are already present; restoration can verify and reuse them without
   requiring split parts.

The repository keeps the exact original study artifacts under `studies/`.
`provenance/study_snapshot.json` records every copied study file's SHA256 and
byte count. This release manifest is a packaging check, not a new historical
research freeze. `provenance/large_file_parts.json` records the concatenation
order and each part/whole-file digest. No scientific data was recompressed or
reserialized when dividing the two large files.

Original machine-specific paths remain inside historical sources/receipts so
their captured byte hashes are not silently changed. The portable entry points
use the checkout-relative study folders instead. They do not validate external
original ZIP bundles that are not distributed. Two legacy tests requiring those
external historical ZIPs are explicitly skipped in the portable test run; all
other freeze, numerical, scheduling and statistical tests remain enabled.

The revised original report is included beside the frozen original report.
`scripts/rebuild_universe_report.py` creates a fresh PDF in `local_outputs/`
using pinned results and the existing reporting implementation; it does not
edit the study snapshots, select new models or load new market prices.

Historical study commands that download or evaluate new research are retained
as source evidence, not as the portable release entry points. Do not reset
freeze receipts or characterize already-inspected periods as new tests. For
new strategies, create a separate experiment and retain unsuccessful outcomes.

The exact prior project ZIP bundles and the private assignment DOCX are not
part of either distribution. Their previous hashes, source names and historical
preservation claims remain recorded, without asserting that an absent bundle
was checked on a new machine.

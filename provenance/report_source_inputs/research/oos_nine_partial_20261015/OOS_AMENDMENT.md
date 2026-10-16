# Approved OOS window amendment — frozen before access

The direct human approval changes only the evaluation calendar of the approved
nine-strategy draft: **1 January–30 September 2026**, with the closing endpoint
**1 October 2026 at00:00 UTC** (30September20:00 NewYork EDT).
Start:1January00:00UTC (31December2025 19:00NewYork EST).
This is **273 complete UTC days /6552 elapsed hours**, not a full year.
Every accounting interval satisfies start<bar_end<=end. No candle opening at
the ending endpoint is included.

All nine frozen baskets/case dictionaries, seven cost/delay scenarios,
HAC27/28-day synchronized bootstrap/10000 draws/seed20261015/Holm9,
40% observed-hour drawdown budget and each unrounded turnover cap are unchanged.
No reselection, candidate pruning, ensemble or intra-run risk-stop is introduced.
The budgets are full-path acceptance diagnostics; failures remain in the record.
The drawdown gate is <=40%; turnover is annualized on273days and compared with
the unchanged 1.5x historical maximum cap. Annualization uses365, not273.

Expected workload:18 zero-cost base simulations,63financial outcomes,
9primary inference slots. Complete calendars, flat days, cash start and once-only
terminal liquidation are preserved. Cash interest is zero.

The governing JSON and code/environment/source-policy pins are sealed in
outputs/access_freeze.json before the first price-byte verification/decode.
Outputs/first_2026_access.json records the later owned first-access boundary.
Existing official-checksum archives may be reused read-only; missing archives,
bad checksums or unexplained gaps stop evaluation without fill or truncation.

Earlier project iterations inspected January–September2026. This run is a
**retrospective temporal evaluation**, not pristine blind or prospective OOS.
The freeze records process chronology; it cannot erase prior exposure or the
large basket/configuration search. Holm9 is not a correction for those searches.
Partial-year inference is approximate and potentially low-powered.
Theoretical shorts omit borrow/funding, realistic fills, capacity and ordinary
weight-drift maintenance. Research acceptance does not establish deployability.

The approved parent draft and all prior studies remain unchanged. Technical
corrections, if required, must be logged with cause, affected scope and hashes;
they do not permit strategy or threshold changes after seeing outcomes.

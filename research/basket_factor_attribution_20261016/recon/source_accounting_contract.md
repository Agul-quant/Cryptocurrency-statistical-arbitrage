# Saved-path attribution source and accounting contract

This is implementation/audit documentation, not an additional reader-facing report.

## Read-only evidence scope

- Nine unchanged registry identities: A01, A02, A03, A04, B01, B03, B04, B05, B06.
- Three independently cash-initialized periods: development 2022–2023, validation
  2024–2025, and January–September 2026, ending October 1 at 00:00 UTC.
- Exactly 27 saved primary paths at 20 bps and lag1; no targets, trades,
  rebalances, model selection, fees or simulations are regenerated.
- `research/post_oos_diagnostics_20261015/shared/input_manifest.json` provides the
  path/base/held/target pins. `attribution/manifest.json` identifies the previously
  audited hourly coin ledgers. Both are directly pinned by that study's completed
  final delivery manifest. The expected-input whitelist is
  `required_source_pins.json`; it is derived from sealed JSON metadata before
  any new-study data decode.
- Source union contains **21** economic slots. Basket membership remains the
  original eight slots for each strategy. LUNA denotes the legacy Terra/LUNC
  economic slot, not Terra 2; MATIC/POL and FTM/S retain the documented lifecycle
  mappings and cash gaps. No new source archive is needed.
- The owned gate verifies code/design/input-list pins and records access before
  actual source/path hashing and before any Parquet decode. No old acquisition
  gate or runner is called.

## Exact per-coin accounting

For interval `t`, coin `i`, let `w[t,i]` be the saved pre-event held weight,
`p[t,i]` the post-event target when an audited forced event occurs (otherwise
`w[t,i]`), and `p[0,i]=0` for the period's initial cash portfolio.

1. Coin gross increment: `g[t,i] = w[t,i] * asset_return[t,i]`.
2. Ordinary full-L1 units: `abs(w[t,i] - p[t-1,i])`.
3. Forced-event units: `abs(p[t,i] - w[t,i])`.
4. Terminal units: `abs(p[T,i])` at the **single final interval only**.
5. Coin fee increment: `f[t,i] = 0.002 * (ordinary + forced + terminal)`.
6. Portfolio net increment: `r[t] = sum_i(g[t,i] - f[t,i])`.
7. Period NAV: `V[t] = V[t-1] * (1+r[t])`, with `V[0]=1`.
8. Linked coin gross/fee/net contribution: `V[t-1]` times the respective
   increment, summed across the full period.

The linked net contributions sum exactly to `V[T]-1`. Plain sums of hourly
returns or stand-alone coin buy-and-hold returns are not this decomposition.
Gross contributions use **net strategy NAV before the interval** and are not a
separate frictionless strategy path. All eight costs remain allocated to their
own traded coin. No ordinary drift-maintenance fees are invented.

The 2022 legacy LUNA partial event remains in its documented 01:00 UTC accounting
bucket, with the actual preceding partial earned move; returns are not prorated
by exposure time. Other coins keep their inherited completed-hour accounting.
Event metadata remains attached for audit. This does not verify executable
fills, theoretical shortability, funding, borrow or real capacity.

## Daily vectors and resampled contributions

Within each UTC day, aggregate the hourly gross and fee **linked** contributions
and divide each vector by the actual strategy NAV at that day's start. The
eight resulting gross-minus-fee entries sum to that day's compounded strategy
net return. These daily vectors—not the already period-NAV-linked hourly
values—are suitable for synchronized block resampling. Each bootstrap sample
must rebuild its own aggregate daily NAV and link its resampled coin vectors
with that new NAV. It does not create new block-boundary trading costs or rerun
the strategy rules.

Exactly 730 development, 731 validation and 273 partial-2026 strategy days stay
in each accounting path; no strategy day is excluded for regression-factor
availability. The closing midnight endpoint belongs to the preceding UTC day.

## Coin-factor returns and unavailable observations

The unchanged pure `asset_returns` helper supplies hourly simple coin returns.
The explicit same-day March 2023 whole-venue 11:00-to-15:00 bridge is booked once
with four elapsed hours. This is not interpolation or a general gap-fill rule.

A full-day coin factor is available only when every accounting subinterval has
a finite, observed, holding-permitted return and no forced-exit bucket for that
coin. A missing interior interval makes the day unknown even when both daily
endpoint prices exist. Individual migration/lifecycle cash gaps are never
bridged and their coin returns are never filled with zero. Missing factors do
not erase strategy P&L or contribution observations.

Joint eight-coin regression therefore has an explicitly reported complete-case
calendar that can be smaller than the full strategy calendar. A matched-sample
BTC-only comparison separates model changes from sample changes. Calendar-lag
HAC covariance must respect actual day distances rather than compressing a
multi-month lifecycle gap into adjacent observations. Legacy full-period
BTC-only point estimates and HAC(7) confidence intervals remain unchanged.

## Independent comparisons required

For each of all 27 paths, verify gross returns, full-L1 units, ordinary and forced
units, fees, net returns, compounded NAV, every saved hourly coin contribution,
and all eight terminal/period coin contributions. Compare all 216 aggregate
coin rows to the prior coin ledger. Report exact calendar coverage, maximum
residual errors and missing factor counts. Pure synthetic tests cover valid
all-cash paths, entry/forced/terminal fees, tamper failures, within-day linking,
intrabucket missingness, lifecycle unknowns, global bridge accounting and
midnight labels.

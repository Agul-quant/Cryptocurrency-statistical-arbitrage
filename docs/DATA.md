# Data sources and complete research dataset

## Source and scope

**Provider:** [Binance Vision public data](https://data.binance.vision/),
**venue:** Binance spot, **quote currency:** USDT, **frequency:** one hour.
See the [official data documentation](https://github.com/binance/binance-public-data)
and [source terms](https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md).

The included data are the **complete normalized 22-instrument hourly inputs for
this study's tiered basket universe**, not all cryptocurrencies, all 30 initial
screen names, or the full raw OHLCV schema. Each frozen strategy trades eight
economic slots; the nine frozen baskets together use 21 of the 22. SAND is in
the screening universe but not in those nine baskets. It is retained in the
complete dataset, without changing any strategy or result.

- [Universe and coverage inventory](../data/universe.csv): all 30 initial ranks,
  with explicit `in_tiered_basket_search_22` and `in_frozen_nine_union_21` flags.
  Hourly coverage columns are populated for the 22 distributed instruments;
  blank coverage for ranks 23–30 does **not** imply zero observations.
- [Dataset dictionary](../metadata/dataset.json): fields, timestamps, periods,
  source templates and scope.
- [Current source verification](../metadata/source_verification.json) and
  [normalized input hashes](../data/manifest.json).

## How the universe was selected

The recorded source discovery contained **757 USDT directories**. The historical
liquidity screen had **259 eligible candidates**, ranked by median daily
**quote-asset volume in USDT** over 90 daily endpoints from **3 October to
31 December 2021** (underlying trading dates 2 October–30 December). The
**1 January 2022, 00:00 UTC** decision used an information cutoff 24 hours earlier.
The top 30 formed the initial pool; ranks 1–22 form this study's basket universe.

[All 757 discovered liquidity candidates](../data/historical_liquidity_candidates.csv)
and [the ranked initial 30](../data/historical_liquidity_top30.csv) retain the
metric, window, cutoff, eligibility and rank fields. The directory discovery and
available archive vintages do not reconstruct a perfectly point-in-time census
of every Binance listing. The archive inventory is not exhaustive exchange
membership evidence, and fixed asset/exposure classifications are not an
independent point-in-time metadata reconstruction. Ranking is conditional on
source coverage; it does not eliminate survivorship or source-availability bias.

| Ranks | Instruments, in liquidity order | Basket rule |
| --- | --- | --- |
| 1–2 | BTC, ETH | Both fixed |
| 3–9 | SHIB, BNB, SOL, XRP, DOT, SAND, LUNA | Choose two |
| 10–16 | AVAX, DOGE, ADA, FTM, TRX, MATIC, MANA | Choose two |
| 17–22 | FIL, GALA, LINK, AXS, LTC, VET | Choose two |

This defines **6,615 eight-coin baskets**. Instrument names ending in `USDT`
identify fixed economic slots. In particular, `LUNAUSDT` means Terra Classic
and its LUNC continuation, **not** the separately launched Terra 2.0 asset.

## Included files and coverage

Every aligned panel has **43,824 UTC endpoints**, from **1 October 2021,
01:00 UTC** through **1 October 2026, 00:00 UTC**, inclusive. Ordinary rows are
completed-bar endpoints (`open_time + 1 hour`), not the bar's opening time.
Source millisecond timestamps before 2025 and microsecond timestamps from 2025
are normalized to UTC. The event-specific final LUNA quote keeps its documented
sub-hour timing in the corresponding accounting bucket.

| File | Shape | Meaning |
| --- | --- | --- |
| [`prices.parquet`](../data/prices.parquet) | 43,824 × 22 | Float64 source close marks, USDT |
| [`quote_volume.parquet`](../data/quote_volume.parquet) | 43,824 × 22 | Float64 bar quote-asset volume, USDT; not base-token volume |
| [`observed.parquet`](../data/observed.parquet) | 43,824 × 22 | Boolean valid source observation |
| [`tradable.parquet`](../data/tradable.parquet) | 43,824 × 22 | Boolean permission for new positions under lifecycle rules |
| [`hold_allowed.parquet`](../data/hold_allowed.parquet) | 43,824 × 22 | Boolean permission to retain exposure |
| [`mandatory_exit.parquet`](../data/mandatory_exit.parquet) | 43,824 × 22 | Boolean forced lifecycle exit |
| [`decision_allowed.parquet`](../data/decision_allowed.parquet) | 43,824 × 1 | Shared venue-wide decision permission |

Each float panel has **964,128 cells**, including **3,041 missing values**;
missing marks/volumes remain NaN, not filled observations. The Boolean masks
contain no unknown values. [Availability ranges](../data/availability_ranges.csv)
show each missing or inactive interval. Missingness is concentrated in the
known LUNA, MATIC and FTM lifecycle gaps and one venue-wide missing endpoint.

| Role | UTC calendar period | Days | Evaluation hours |
| --- | --- | ---: | ---: |
| Warmup | October–December 2021 | — | Included source history |
| Development | 1 January 2022–31 December 2023 | 730 | 17,520 |
| Validation | 1 January 2024–31 December 2025 | 731 | 17,544 |
| Partial-year OOS | 1 January–30 September 2026 | 273 | 6,552 |

The final endpoint is the close of the last OOS accounting interval. It does not
include October 2026 returns. Data availability and trade eligibility are
separate: a quoted final price may be retained while new entry is prohibited.

## Raw-source catalogs and checksum evidence

The normalized panels are supplied directly; **raw ZIP archives are not bundled**.
The source catalogs provide exact URLs, ZIP SHA-256 hashes and `.CHECKSUM`
sidecar hashes:

- [1,319 monthly one-hour archives](../data/source_archive_inventory.csv),
  covering **25 physical symbols** because LUNC, POL and S continue the LUNA,
  MATIC and FTM economic slots.
- [Three daily metadata-correction archives](../data/metadata_correction_sources.csv).
- [857 daily-bar monthly archives for historical liquidity](../data/liquidity_source_archive_inventory.csv).

Every listed cached ZIP and sidecar was rehashed for this package, including
checking the sidecar's published digest and filename against the actual ZIP.
This is recorded local-cache verification, **not** a claim that a fresh public
checkout contains or re-downloads those raw files. Verification of the included
panels works offline. No new market data were acquired for this packaging step.

Monthly hourly URL template:

```text
https://data.binance.vision/data/spot/monthly/klines/{source_symbol}/1h/{source_symbol}-1h-{YYYY-MM}.zip
```

Append `.CHECKSUM` to obtain its sidecar. Daily repairs use
`data/spot/daily/klines/{source_symbol}/1h/{source_symbol}-1h-{YYYY-MM-DD}.zip`.
Liquidity archives use the monthly template with `1d` in place of `1h`.

Raw Binance klines have 12 fields: open time, open, high, low, close, base-asset
volume, close time, quote-asset volume, number of trades, taker-buy base volume,
taker-buy quote volume and an unused field. The distributed normalized dataset
retains **close, quote volume and accounting masks**, not every raw field.
For SOL/SAND/TRX on 24 December 2021, **only the diagnosed close-time fields**
were applied from the verified daily archives. Normalized monthly prices and
quote volumes were retained unchanged. Other differences elsewhere in the daily
archives were not substituted; the daily files are not global replacements.

## Suspensions and token continuations

Known lifecycle gaps are deliberate cash/inactive-slot periods, not errors to
fill. The engine preserves the final earned return and exit cost, prevents new
entries during the gap and does not bridge a tradable return across migrations.
It never substitutes a new coin for an inactive slot.

- **Venue halt, 24 March 2023:** the allowed accounting bridge is 11:00–15:00 UTC;
  the 14:00 endpoint is missing across all 22 coins. Shared decision permissions
  prohibit decisions inside the halt. [Binance source](https://www.binance.com/en/blog/from-our-ceo/6789340645608890113).
- **Terra Classic:** the final quote at 13 May 2022, 00:39:59.999 UTC is
  0.00005 USDT, accounted in the 01:00 bucket. The slot is inactive until the
  LUNC restart; the first complete endpoint is 9 September 2022, 09:00 UTC.
  [Trading suspension](https://www.binance.com/en/support/announcement/detail/514e0ba636e843bda47d5d740b7dadf4) ·
  [LUNC reopening](https://www.binance.com/en/support/announcement/detail/1e237033f63945d6b6acaf39f058d152).
- **MATIC → POL, 1:1:** forced exit 10 September 2024, 02:00 UTC; holding stops
  at 03:00. The first complete POL endpoint is 13 September, 11:00 UTC.
  [Binance migration notice](https://www.binance.com/en/support/announcement/detail/6a6de383727f4659a3050f7982e1620f).
- **FTM → S, 1:1:** forced exit 13 January 2025, 02:00 UTC; holding stops
  at 03:00. The first complete S endpoint is 16 January, 09:00 UTC.
  [Binance migration notice](https://www.binance.com/en/support/announcement/detail/aec6fcbc84b749eeab6690e6bcac2f3d).

Missing archives or checksum failures outside this explicit policy are not
silently filled or treated as a listing event. Details of accounting and
statistical missing-factor handling are in [Methods](METHODS.md).

## Use and reproduction

The included 22-slot source supports all baskets in the stated tiered universe.
The supplied research runner deliberately reproduces **only the nine fixed
strategies**, not the complete 6,615 × 168 retained search. Supporting campaign/cohort
outputs remain saved results. Current daily factor and attribution inputs are
also included under `data/diagnostics/`.

Run `python scripts/verify_project.py` to check the current package and
`python scripts/run_research.py` to reproduce and reconcile the 27 primary paths.
These commands do not download prices, revise the frozen strategies or change
selections. [CC BY-NC-SA 4.0](../licenses/DATA_LICENSE.md) and applicable Binance
source terms govern the data and derived artifacts; see [NOTICE](../NOTICE.md).

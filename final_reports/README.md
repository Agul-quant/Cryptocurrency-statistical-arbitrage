# Final reports

## The eight-coin basket design

Each strategy uses **BTC and ETH plus six other coins**: two from historical liquidity ranks 3–9, two from ranks 10–16, and two from ranks 17–22. This gives **6,615 eligible baskets** from the top 22 of the initial 30-coin pool. Liquidity was ranked using 90 daily quote-volume endpoints in late 2021. The nine frozen strategies may use different baskets; each basket stays fixed through development, validation and the 2026 evaluation. The later fixed all-22 studies remove that basket-selection step. [Full universe, ranking and data sources](../docs/DATA.md).

## Main finding: performance did not persist across periods

**All four development-selected A strategies lost in 2024–2025; all five validation-selected B strategies lost in January–September 2026.** The families are shared, while baskets and parameters differ. This pattern is consistent with the search fitting each selection period rather than establishing a stable edge.

The separate fixed all-22 studies also failed to maintain positive net returns across all three periods:

| Separate fixed study | 2022–2023 net | 2024–2025 net | Jan–Sep 2026 net |
| --- | ---: | ---: | ---: |
| 28-day weekly momentum | +5.61% | −17.43% | −20.94% |
| 28-day weekly reversal | −33.59% | −15.66% | +9.91% |

Primary results are net of **20 bps one-way full-L1 transaction costs**. These are separate fixed studies, not ranked alternatives, a combined strategy or another winner selection. Their saved period performance and descriptive uncertainty do not revise their acceptance criteria. All fee/delay sensitivities remain available. Exactly three final PDFs remain.

## Two separate Sharpe conventions

The reports show **√365 and √252** Sharpe annualization conventions, using the **same complete UTC daily return observations, including weekends**. The √252 value equals the √365 value multiplied by `sqrt(252/365)`; this changes the scale, not the strategy, sample or P&L. CAGR, volatility, turnover annualization and annual alpha retain calendar/365-day conventions.

## Read the reports in order

1. **[Development and robustness](01_development/01_development_and_robustness.pdf)** — 2022–2023: the strategy/basket grid and development robustness. [Offline HTML](01_development/01_development_and_robustness.html).
2. **[Validation and frozen selection](02_validation/02_validation_and_frozen_selection.pdf)** — 2024–2025: unchanged Track A tests and explicitly validation-informed Track B selections. [Offline HTML](02_validation/02_validation_and_frozen_selection.html).
3. **[2026 OOS evaluation and conclusions](03_2026_evaluation/03_2026_evaluation_and_conclusions.pdf)** — 1 January–30 September 2026: the nine frozen strategies, original corrected inference and explanatory diagnostics. [Offline HTML](03_2026_evaluation/03_2026_evaluation_and_conclusions.html).

All three include separately labelled fixed all-22 study sections and full-precision companion exports. Tables retain strategy returns and risks, per-coin gross/fee/net contributions, joint eight-coin alpha/betas and confidence intervals, with BTC-only estimates for comparison.

## Data and interpretation

**Source:** Binance public Data Vision spot-USDT one-hour klines. The complete normalized study dataset covers all **22 screening-universe economic slots** and **43,824 UTC close endpoints**, from **1 October 2021 at 01:00 through 1 October 2026 at 00:00**, including warm-up. [Data sources, field definitions, inventory and coverage](../docs/DATA.md).

Track B validation performance is selection-conditioned. The 2026 period has **273 days**, not a full year, and later factor/cohort diagnostics are explanatory rather than new confirmation. The additional fixed studies use historical windows already examined in the wider project. Momentum retains its disclosed pre-input-access chronology exception; reversal met its new-study pre-decode seal. No new winner or deployment approval is claimed.

See the [current methods](../docs/METHODS.md), [fixed momentum specification and evidence](../docs/FIXED_ALL22_PROTOCOL.md), and [separate fixed reversal specification and evidence](../docs/FIXED_ALL22_REVERSAL_PROTOCOL.md).

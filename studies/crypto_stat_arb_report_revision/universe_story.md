# Research story and choice of universe

## Start with the course question

The assignment asks whether momentum or reversal in cryptocurrency price-volume data can survive trading costs. It permits a flexible research design but does not prescribe any coin names, a universe size, or an asset-selection rule. The original project operationalized that question with an hourly, cross-sectional backtest and a fixed universe before comparing strategy parameters.

## How the eight coins were defined

The configured instruments are BTCUSDT, ETHUSDT, LTCUSDT, ADAUSDT, LINKUSDT, DOGEUSDT, DOTUSDT and SOLUSDT. The retained report describes them as eight present-day recognizable coins and a **purposive survivor sample**. They were specified directly in the configuration and downloader; they were not produced by a recorded market-cap, liquidity, correlation or profitability screen. The precise reason for choosing each coin, or choosing eight rather than another number, is not documented.

Using a single exchange and the same USDT quote currency gives a consistent source and numeraire. The eight pairs have archived hourly data from December 2021 through December 2025, subject to the disclosed halt and metadata exceptions. These are practical advantages of the setup, not evidence that they were formal historical selection criteria.

## What was the bigger pool?

**No larger candidate pool was enumerated in the retained project.** There is no recorded initial coin count, rejected-asset list, ranking, or point-in-time eligibility table. All Binance spot USDT pairs would be a natural broader opportunity set for a different study, but the original project did not demonstrate that it screened that set. It would therefore be incorrect to claim that these were the eight most liquid coins or that only eight survived a market-wide screen.

## Data checking is not universe selection

Acquisition started with the eight configured pairs and verified 392 monthly archives: 49 per pair. The subsequent audit checked coverage, checksums, duplicates, OHLCV consistency and the documented exceptions. It did not compare these eight with excluded coins. The 18 candidates in the original research were **strategy configurations** (nine momentum and nine reversal), not 18 competing coins; 2024 selected signal parameters while the asset universe stayed fixed.

## What this means for the story

The findings are conditional on this fixed survivor universe, not a point-in-time representation of the full crypto market. Failed, delisted and newly listed alternatives were not represented, so generalization is limited. This revised report preserves the original 18-configuration study and its initial 2025 evaluation; later exploratory scans and the 2026 historical holdout remain separate.

**Universe evidence:** supplied ClassProject.docx; configs/research.toml; src/crypto_stat_arb/data.py; data/raw/manifest.json; data/processed/data_quality.json; README.md; and the preserved report implementation. No retrospective asset-screening story has been invented.

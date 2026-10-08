"""Strict checksum-verified five-minute Binance spot source, without price fills.

Raw source bytes are retained. The sole timing repair changes one SOL close-time
metadata field, using a verified same-granularity official daily record. The
March 2023 suspension is independently audited at five-minute resolution before
any strategy evaluation. Prices are indexed by exclusive UTC bar endpoints.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import csv
import hashlib
from http.client import IncompleteRead
import io
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .core import utc_now, sha256_file, write_json

SYMBOLS = ["BTCUSDT", "ETHUSDT", "LTCUSDT", "ADAUSDT", "LINKUSDT", "DOGEUSDT", "DOTUSDT", "SOLUSDT"]
BAR_MINUTES = 5
STEP = pd.Timedelta(minutes=BAR_MINUTES)
BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"
SOURCE_DOC = "https://github.com/binance/binance-public-data"
TERMS_URL = SOURCE_DOC + "/blob/master/TERMS_AND_CONDITIONS.md"
HALT_SOURCE = "https://www.binance.com/en/blog/from-our-ceo/6789340645608890113"
HALT_BRIDGES = [{"start": "2023-03-24T11:25:00+00:00", "end": "2023-03-24T14:05:00+00:00", "source": HALT_SOURCE}]
ALLOWED_MISSING_ENDPOINTS = [v.isoformat() for v in pd.date_range("2023-03-24T12:45:00Z", "2023-03-24T14:00:00Z", freq="5min")]
RAW_COLUMNS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades", "taker_buy_volume", "taker_buy_quote_volume", "ignore"]
BAR_COLUMNS = ["symbol", "open", "high", "low", "close", "volume", "quote_volume", "trades"]
UNIT_SWITCH = pd.Timestamp("2025-01-01", tz="UTC")
KNOWN_SHORT_CLOSE_TIMES = {
    ("ADAUSDT", 1640321700000): 1640321992654,
    ("BTCUSDT", 1640321700000): 1640321994362,
    ("DOGEUSDT", 1640321700000): 1640321995588,
    ("DOTUSDT", 1640321700000): 1640321995682,
    ("ETHUSDT", 1640321700000): 1640321996158,
    ("LINKUSDT", 1640321700000): 1640321997827,
    ("LTCUSDT", 1640321700000): 1640321998040,
    ("ADAUSDT", 1679661300000): 1679661580151,
    ("BTCUSDT", 1679661300000): 1679661581646,
    ("DOGEUSDT", 1679661300000): 1679661582562,
    ("DOTUSDT", 1679661300000): 1679661582630,
    ("ETHUSDT", 1679661300000): 1679661583061,
    ("LINKUSDT", 1679661300000): 1679661584685,
    ("LTCUSDT", 1679661300000): 1679661584908,
    ("SOLUSDT", 1679661300000): 1679661586948,
}


class DataQualityError(ValueError):
    """Integrity, schema, or source-backed coverage gate failed."""


def _utc(value) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tz is None else stamp.tz_convert("UTC")


def checksum_digest(content: str, filename: str) -> str:
    lines = [s.strip() for s in content.splitlines() if s.strip()]
    match = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?(.+)", lines[0]) if len(lines) == 1 else None
    if match is None or match.group(2) != filename:
        raise DataQualityError(f"Expected one SHA256 record for exact filename {filename}")
    return match.group(1).lower()


def verify_checksum(archive: Path, checksum: Path) -> str:
    expected = checksum_digest(Path(checksum).read_text(), Path(archive).name)
    actual = sha256_file(archive)
    if actual != expected:
        raise DataQualityError(f"SHA256 mismatch: {Path(archive).name}")
    return actual


def _fetch(url: str, attempts: int = 4) -> bytes:
    error = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": "crypto-intraday-educational-research/1.0"})
            with urlopen(request, timeout=50) as response:
                return response.read()
        except HTTPError as exc:
            error = exc
            if exc.code not in (408, 429, 500, 502, 503, 504):
                raise
        except (URLError, TimeoutError, ConnectionError, OSError, IncompleteRead) as exc:
            error = exc
        if attempt < attempts - 1:
            time.sleep(2 ** attempt)
    raise DataQualityError(f"Source retrieval failed: {url}") from error


def _atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def acquire_archive(root: Path, symbol: str, date: str, *, daily=False, old=None) -> dict:
    name = f"{symbol}-5m-{date}.zip"
    cadence = "daily" if daily else "monthly"
    url = f"https://data.binance.vision/data/spot/{cadence}/klines/{symbol}/5m/{name}"
    directory = Path(root) / "data/raw" / ("repairs" if daily else symbol)
    archive, checksum = directory / name, directory / (name + ".CHECKSUM")
    resumed = archive.exists() and checksum.exists()
    if resumed:
        digest = verify_checksum(archive, checksum)
    else:
        checksum_bytes = _fetch(url + ".CHECKSUM")
        expected = checksum_digest(checksum_bytes.decode(), name)
        content = _fetch(url)
        digest = hashlib.sha256(content).hexdigest()
        if digest != expected:
            raise DataQualityError(f"Downloaded source/checksum mismatch: {name}")
        _atomic_bytes(archive, content)
        _atomic_bytes(checksum, checksum_bytes)
    return {
        "symbol": symbol, "month": date[:7], "date": date, "interval": "5m",
        "archive_path": str(archive.relative_to(root)), "source_url": url,
        "checksum_url": url + ".CHECKSUM", "sha256": digest,
        "checksum_sha256": sha256_file(checksum), "bytes": archive.stat().st_size,
        "downloaded_utc": (old or {}).get("downloaded_utc", datetime.fromtimestamp(archive.stat().st_mtime, timezone.utc).isoformat()),
        "verified_utc": utc_now(), "resumed_checksum_cache": resumed,
        "timestamp_unit": "us" if date >= "2025-01" else "ms",
    }


def _source_rows(path: Path) -> list[list[str]]:
    try:
        with ZipFile(path) as archive:
            expected = path.stem + ".csv"
            if [n for n in archive.namelist() if not n.endswith("/")] != [expected]:
                raise DataQualityError(f"Unexpected ZIP members: {path.name}")
            rows = list(csv.reader(io.StringIO(archive.read(expected).decode("utf-8"))))
    except (BadZipFile, UnicodeDecodeError, KeyError) as error:
        raise DataQualityError(f"Invalid source ZIP: {path.name}") from error
    if not rows or any(len(row) != 12 for row in rows):
        raise DataQualityError(f"Expected nonempty 12-column kline CSV: {path.name}")
    return rows


def prepare_exception_policy(root: Path, symbols: list[str], months: list[str]) -> dict:
    """Verify minute-grain source evidence and lock the pre-performance policy."""
    daily_records, repair = [], None
    if "2021-12" in months and "SOLUSDT" in symbols:
        record = acquire_archive(root, "SOLUSDT", "2021-12-24", daily=True)
        monthly = root / "data/raw/SOLUSDT/SOLUSDT-5m-2021-12.zip"
        original = [r for r in _source_rows(monthly) if r[0] == "1640321700000"]
        corrected = [r for r in _source_rows(root / record["archive_path"]) if r[0] == "1640321700000"]
        if len(original) != 1 or len(corrected) != 1:
            raise DataQualityError("Official minute metadata repair lacks unique intended row")
        differences = [i for i, (a, b) in enumerate(zip(original[0], corrected[0])) if a != b]
        if differences != [6] or original[0][6] != "1640322000475" or corrected[0][6] != "1640321999999":
            raise DataQualityError("Only the exact close-time metadata field may be repaired")
        repair = {**record, "open_time": 1640321700000, "original_close_time": 1640322000475,
                  "corrected_close_time": 1640321999999, "original_monthly_sha256": sha256_file(monthly),
                  "original_raw_row": original[0], "official_daily_raw_row": corrected[0],
                  "changed_columns": ["close_time"], "all_other_fields_byte_identical": True,
                  "price_or_volume_repair": False, "original_monthly_retained": True}
        daily_records.append(record)
    bridges, missing = [], []
    if "2023-03" in months:
        for symbol in symbols:
            record = acquire_archive(root, symbol, "2023-03-24", daily=True)
            daily = _source_rows(root / record["archive_path"])
            monthly = _source_rows(root / f"data/raw/{symbol}/{symbol}-5m-2023-03.zip")
            start = pd.Timestamp("2023-03-24", tz="UTC")
            expected = pd.date_range(start + STEP, start + pd.Timedelta(days=1), freq="5min")
            dates = pd.DatetimeIndex(pd.to_datetime([int(r[0]) for r in daily], unit="ms", utc=True)) + STEP
            if [v.isoformat() for v in expected.difference(dates)] != ALLOWED_MISSING_ENDPOINTS:
                raise DataQualityError("Daily source differs from exact predeclared suspension gaps")
            raw_by_open = {r[0]: r for r in monthly}
            if any(raw_by_open.get(r[0]) != r for r in daily):
                raise DataQualityError("Monthly/daily source differs on suspension-day raw fields")
            endpoints = {int(r[0]): r for r in daily}
            for stamp in ["2023-03-24T11:20:00Z", "2023-03-24T14:00:00Z"]:
                r = endpoints[int(pd.Timestamp(stamp).timestamp() * 1000)]
                if float(r[5]) <= 0 or int(r[8]) <= 0:
                    raise DataQualityError("Bridge bounds must be complete actual traded source bars")
            # Observed partial-bar trading stops after 11:27; all subsequent
            # recorded 11:30–12:35 opens are explicit no-trade source rows.
            interior = [r for r in daily if 1679657400000 <= int(r[0]) <= 1679661300000]
            if any(float(r[5]) != 0 or int(r[8]) != 0 for r in interior):
                raise DataQualityError("Unexpected traded candle inside documented suspension")
            record["missing_endpoints"] = ALLOWED_MISSING_ENDPOINTS
            record["monthly_daily_raw_identical"] = True
            daily_records.append(record)
        bridges, missing = HALT_BRIDGES, ALLOWED_MISSING_ENDPOINTS
    policy = {
        "bar_minutes": 5, "halt_bridges": bridges, "allowed_missing_endpoints": missing,
        "halt_policy": "Retain prehalt holdings; observe price14:05/price11:25 once over160min; no interior valuation or execution; never fill prices",
        "official_metadata_repair": repair,
        "known_short_close_times": [{"symbol": s, "raw_open_time": o, "raw_close_time": c} for (s, o), c in sorted(KNOWN_SHORT_CLOSE_TIMES.items())],
        "source_documentation": SOURCE_DOC, "terms_url": TERMS_URL,
        "scientific_status": "Source-quality policy; no portfolio or strategy outcomes used",
    }
    path = root / "outputs/data_exception_policy.json"
    if path.exists():
        existing = json.loads(path.read_text())
        old_repair = existing.get("official_metadata_repair")
        for key in ["bar_minutes", "halt_bridges", "allowed_missing_endpoints", "known_short_close_times"]:
            if existing[key] != policy[key]:
                raise DataQualityError(f"Previously locked source policy changed: {key}")
        repair_keys = ["original_monthly_sha256", "sha256", "checksum_sha256", "original_raw_row", "official_daily_raw_row", "changed_columns"]
        if bool(old_repair) != bool(repair) or (repair and any(old_repair[k] != repair[k] for k in repair_keys)):
            raise DataQualityError("Previously locked repair source changed")
        policy["locked_at_utc"] = existing["locked_at_utc"]
    else:
        policy["locked_at_utc"] = utc_now()
        write_json(path, policy)
    write_json(root / "data/raw/repairs/manifest.json", {"source": "Binance Vision", "files": daily_records, "metadata_repair": repair})
    return policy


def normalize_archive(archive: Path, symbol: str, month: str, *, allow_documented_exceptions=False, repair_record=None) -> pd.DataFrame:
    rows = _source_rows(Path(archive))
    raw = pd.DataFrame(rows, columns=RAW_COLUMNS)
    try:
        frame = raw.apply(pd.to_numeric, errors="raise")
    except (ValueError, TypeError) as error:
        raise DataQualityError(f"Nonnumeric kline field: {archive.name}") from error
    if not np.isfinite(frame.to_numpy(dtype=float)).all():
        raise DataQualityError(f"Nonfinite kline field: {archive.name}")
    for column in ["open_time", "close_time", "trades", "ignore"]:
        if (frame[column] != np.floor(frame[column])).any():
            raise DataQualityError(f"Noninteger {column}: {archive.name}")
        frame[column] = frame[column].astype("int64")
    if (frame["ignore"] != 0).any():
        raise DataQualityError("Unknown nonzero ignored schema field")
    prices = frame[["open", "high", "low", "close"]]
    if (prices <= 0).any().any() or ((frame["low"] > prices.min(axis=1)) | (frame["high"] < prices.max(axis=1))).any():
        raise DataQualityError(f"Invalid positive ordered OHLC: {archive.name}")
    volumes = frame[["volume", "quote_volume", "trades", "taker_buy_volume", "taker_buy_quote_volume"]]
    if (volumes < 0).any().any() or ((frame.taker_buy_volume > frame.volume + 1e-8) | (frame.taker_buy_quote_volume > frame.quote_volume + 1e-6)).any():
        raise DataQualityError(f"Invalid quantity/trade fields: {archive.name}")
    start = pd.Timestamp(month + "-01", tz="UTC")
    unit = "us" if start >= UNIT_SWITCH else "ms"
    scale = 1_000_000 if unit == "us" else 1000
    expected_close = frame.open_time + 300 * scale - 1
    anomalies = []
    for position in frame.index[frame.close_time != expected_close]:
        opened, closed = int(frame.at[position, "open_time"]), int(frame.at[position, "close_time"])
        anomaly = {"symbol": symbol, "archive": archive.name, "timestamp_unit": unit,
                   "raw_open_time": opened, "raw_close_time": closed,
                   "expected_close_time": int(expected_close[position]),
                   "open_time_utc": pd.to_datetime(opened, unit=unit, utc=True).isoformat()}
        if repair_record and symbol == "SOLUSDT" and opened == repair_record["open_time"]:
            if (sha256_file(archive) != repair_record["original_monthly_sha256"] or raw.loc[position].tolist() != repair_record["original_raw_row"] or repair_record["changed_columns"] != ["close_time"] or repair_record["all_other_fields_byte_identical"] is not True):
                raise DataQualityError("Repair provenance differs from exact original source bytes")
            frame.at[position, "close_time"] = repair_record["corrected_close_time"]
            if frame.at[position, "close_time"] != expected_close[position]:
                raise DataQualityError("Official metadata correction is not a five-minute endpoint")
            anomaly["policy"] = "official_daily_close_time_repair_only"
        elif allow_documented_exceptions and unit == "ms" and KNOWN_SHORT_CLOSE_TIMES.get((symbol, opened)) == closed and opened <= closed < expected_close[position]:
            anomaly["policy"] = "documented_shortened_source_metadata_warning"
        else:
            raise DataQualityError(f"Unknown close-time anomaly: {archive.name}: {opened} {closed}")
        anomalies.append(anomaly)
    if (frame.open_time % (300 * scale) != 0).any():
        raise DataQualityError(f"Unaligned five-minute open: {archive.name}")
    try:
        index = pd.DatetimeIndex(pd.to_datetime(frame.open_time, unit=unit, utc=True))
    except (ValueError, OverflowError) as error:
        raise DataQualityError(f"Invalid explicit {unit} timestamp: {archive.name}") from error
    if ((index < start) | (index >= start + pd.offsets.MonthBegin(1))).any():
        raise DataQualityError(f"Timestamp outside archive month: {archive.name}")
    if index.has_duplicates:
        raise DataQualityError(f"Duplicate five-minute candles: {archive.name}")
    result = frame[[c for c in BAR_COLUMNS if c != "symbol"]].copy()
    for column in result.columns:
        result[column] = result[column].astype("int64" if column == "trades" else "float64")
    result.insert(0, "symbol", symbol)
    result.index = pd.DatetimeIndex(index + STEP, name="bar_end")
    result = result.sort_index()
    result.attrs["original_close_time_anomalies"] = anomalies
    return result


def audit_bars(bars: pd.DataFrame, symbols: list[str], start: pd.Timestamp, end: pd.Timestamp, *, allow_documented_halt=False) -> dict:
    """Audit raw observed rows; retain absent timestamps as absent, never fill."""
    if start.tz is None or end.tz is None or end <= start:
        raise DataQualityError("Require increasing timezone-aware coverage")
    expected = pd.date_range(start + STEP, end, freq="5min", name="bar_end")
    if not isinstance(bars.index, pd.DatetimeIndex) or str(bars.index.tz) != "UTC":
        raise DataQualityError("Expected UTC endpoint index")
    duplicate = int(bars.reset_index().duplicated(["bar_end", "symbol"]).sum())
    per_symbol = {}
    allowed = [v for v in ALLOWED_MISSING_ENDPOINTS if start < pd.Timestamp(v) <= end]
    for symbol in symbols:
        rows = bars[bars.symbol == symbol]
        observed = pd.DatetimeIndex(rows.index).unique()
        missing, extra = expected.difference(observed), observed.difference(expected)
        per_symbol[symbol] = {"rows": len(rows), "expected_rows": len(expected), "coverage_fraction": len(expected.intersection(observed)) / len(expected), "missing_count": len(missing),
                              "missing_bar_ends": [v.isoformat() for v in missing], "extra_count": len(extra),
                              "extra_bar_ends": [v.isoformat() for v in extra],
                              "first_bar_end": observed.min().isoformat() if len(rows) else None,
                              "last_bar_end": observed.max().isoformat() if len(rows) else None}
        for column in ["volume", "trades"]:
            if column in rows:
                per_symbol[symbol]["zero_" + column + "_count"] = int((rows[column] == 0).sum())
    unexpected = sorted(set(bars.symbol) - set(symbols))
    missing_count = sum(r["missing_count"] for r in per_symbol.values())
    extra_count = sum(r["extra_count"] for r in per_symbol.values())
    pass_clean = not (duplicate or missing_count or extra_count or unexpected)
    documented = (allow_documented_halt and not duplicate and not extra_count and not unexpected and bool(allowed)
                  and all(r["missing_bar_ends"] == allowed for r in per_symbol.values()))
    status = "pass" if pass_clean else "pass_with_documented_exceptions" if documented else "fail"
    bridges = [b for b in HALT_BRIDGES if start <= pd.Timestamp(b["start"]) and pd.Timestamp(b["end"]) <= end] if allow_documented_halt else []
    return {"status": status, "generated_utc": utc_now(), "source": "Binance Vision spot monthly klines",
            "symbols": symbols, "start_open_time": start.isoformat(), "end_open_time_exclusive": end.isoformat(),
            "interval": "5m", "bar_minutes": 5, "bar_endpoint": "open_time + 5 minutes; exclusive UTC completed-bar endpoint",
            "timezone": "UTC", "rows": len(bars), "expected_rows": len(expected) * len(symbols), "panel_rows": len(expected),
            "missing_count": missing_count, "extra_count": extra_count, "duplicate_count": duplicate,
            "unexpected_symbols": unexpected, "per_symbol": per_symbol,
            "allowed_missing_endpoints": allowed if documented else [], "halt_bridges": bridges,
            "implicit_fill": False, "cross_venue_substitution": False,
            "timestamp_units": {"before_2025-01-01": "ms", "from_2025-01-01": "us"},
            "license": "CC BY-NC-SA 4.0; non-commercial educational research", "attribution": "Source: Binance Vision", "terms_url": TERMS_URL}


def download_and_prepare(root: Path, config: dict) -> dict:
    root = Path(root).resolve()
    settings = config["data"]
    symbols = list(settings.get("symbols", SYMBOLS))
    if symbols != SYMBOLS or settings.get("interval", "5m") != "5m":
        raise ValueError("Fixed eight-asset five-minute educational source required")
    start, end = _utc(settings["start"]), _utc(settings.get("end", settings.get("end_exclusive")))
    if start >= end or any(t.day != 1 or t != t.normalize() for t in [start, end]):
        raise ValueError("Require full increasing UTC monthly bounds")
    months = pd.date_range(start, end, freq="MS", inclusive="left").strftime("%Y-%m").tolist()
    processed = root / "data/processed"
    processed.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "data/raw/manifest.json"
    old = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    old_by_key = {(r["symbol"], r["month"]): r for r in old.get("files", [])}
    records, failures = [], []
    with ThreadPoolExecutor(max_workers=min(8, max(1, int(settings.get("download_workers", 8))))) as executor:
        futures = {executor.submit(acquire_archive, root, symbol, month, old=old_by_key.get((symbol, month))): (symbol, month) for symbol in symbols for month in months}
        for done, future in enumerate(as_completed(futures), 1):
            try:
                records.append(future.result())
            except Exception as error:
                symbol, month = futures[future]
                failures.append({"symbol": symbol, "month": month, "error": str(error)})
            if done % 32 == 0 or done == len(futures):
                print(f"Five-minute archives verified {len(records)}/{len(futures)}; failures {len(failures)}", flush=True)
    records.sort(key=lambda r: (r["month"], symbols.index(r["symbol"])))
    manifest = {"source": "Binance Vision", "source_documentation": SOURCE_DOC, "terms_url": TERMS_URL,
                "generated_utc": utc_now(), "symbols": symbols, "interval": "5m", "start": start.isoformat(), "end_exclusive": end.isoformat(),
                "expected_archive_count": len(symbols) * len(months), "verified_archive_count": len(records),
                "total_archive_bytes": sum(r["bytes"] for r in records), "files": records, "acquisition_failures": failures,
                "license": "CC BY-NC-SA 4.0", "use": "Non-commercial educational historical research", "attribution": "Source: Binance Vision"}
    write_json(manifest_path, manifest)
    if failures:
        write_json(processed / "data_quality.json", {"status": "fail", "acquisition_failures": failures})
        raise DataQualityError("Incomplete source acquisition; no evaluation permitted")
    writer, anomalies = None, []
    temporary = processed / "bars.parquet.tmp"
    try:
        policy = prepare_exception_policy(root, symbols, months)
        for month in months:
            frames = []
            for record in [r for r in records if r["month"] == month]:
                frame = normalize_archive(root / record["archive_path"], record["symbol"], month,
                                          allow_documented_exceptions=True, repair_record=policy["official_metadata_repair"])
                record["rows"] = len(frame)
                record["original_close_time_anomalies"] = frame.attrs["original_close_time_anomalies"]
                anomalies.extend(frame.attrs["original_close_time_anomalies"])
                frame.attrs = {}
                frames.append(frame)
            chunk = pd.concat(frames).reset_index().sort_values(["bar_end", "symbol"]).set_index("bar_end")
            table = pa.Table.from_pandas(chunk, preserve_index=True)
            if writer is None:
                writer = pq.ParquetWriter(temporary, table.schema, compression="zstd")
            writer.write_table(table)
        writer.close()
        writer = None
        temporary.replace(processed / "bars.parquet")
        bars = pd.read_parquet(processed / "bars.parquet", columns=["symbol", "volume", "trades"])
        audit = audit_bars(bars, symbols, start, end, allow_documented_halt=True)
        audit.update({"archive_count": len(records), "verified_archive_bytes": manifest["total_archive_bytes"],
                      "normalized_parquet_sha256": sha256_file(processed / "bars.parquet"),
                      "original_close_time_anomaly_count": len(anomalies), "original_close_time_anomalies": anomalies,
                      "official_metadata_repair_count": sum(a["policy"] == "official_daily_close_time_repair_only" for a in anomalies),
                      "remaining_metadata_warning_count": sum(a["policy"] == "documented_shortened_source_metadata_warning" for a in anomalies),
                      "official_metadata_repairs": [policy["official_metadata_repair"]] if policy["official_metadata_repair"] else [],
                      "source_policy_locked_at_utc": policy["locked_at_utc"], "source_policy_sha256": sha256_file(root / "outputs/data_exception_policy.json"),
                      "halt_policy": policy["halt_policy"], "daily_verification_archive_count": 9 if policy["official_metadata_repair"] and policy["halt_bridges"] else len(json.loads((root / "data/raw/repairs/manifest.json").read_text())["files"]),
                      "all_partial_no_trade_raw_bars_retained": True})
        write_json(processed / "data_quality.json", audit)
        write_json(root / "outputs/data_quality_receipt.json", audit)
        write_json(manifest_path, manifest)
        if audit["status"] == "fail":
            raise DataQualityError("Unexplained source coverage gap; no price fills or evaluation permitted")
        print(f"Five-minute audit {audit['status']}: {audit['rows']} rows; {audit['missing_count']} missing cells", flush=True)
        return audit
    except Exception as error:
        if writer is not None:
            writer.close()
        write_json(manifest_path, manifest)
        if not (processed / "data_quality.json").exists() or json.loads((processed / "data_quality.json").read_text()).get("status") != "fail":
            write_json(processed / "data_quality.json", {"status": "fail", "schema_error": str(error)})
        raise


def load_panel(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Load audited full calendar panels; source absences remain explicit NaNs."""
    root = Path(root)
    processed = root / "data/processed"
    audit = json.loads((processed / "data_quality.json").read_text())
    if audit.get("status") not in ("pass", "pass_with_documented_exceptions"):
        raise DataQualityError("Data quality gate failed")
    if sha256_file(processed / "bars.parquet") != audit["normalized_parquet_sha256"]:
        raise DataQualityError("Normalized Parquet differs from its audited SHA256")
    if audit.get("source_policy_sha256") and sha256_file(root / "outputs/data_exception_policy.json") != audit["source_policy_sha256"]:
        raise DataQualityError("Locked source-quality policy changed")
    bars = pd.read_parquet(processed / "bars.parquet", columns=["symbol", "close", "quote_volume"])
    current = audit_bars(bars, audit["symbols"], _utc(audit["start_open_time"]), _utc(audit["end_open_time_exclusive"]), allow_documented_halt=True)
    for key in ["status", "rows", "missing_count", "extra_count", "duplicate_count", "allowed_missing_endpoints", "halt_bridges"]:
        if current[key] != audit[key]:
            raise DataQualityError(f"Loaded source coverage differs from audit: {key}")
    expected = pd.date_range(_utc(audit["start_open_time"]) + STEP, _utc(audit["end_open_time_exclusive"]), freq="5min", name="bar_end")
    panels = []
    for field in ["close", "quote_volume"]:
        panel = bars.reset_index().pivot(index="bar_end", columns="symbol", values=field).reindex(index=expected, columns=audit["symbols"])
        panel.columns.name = None
        values = panel.to_numpy(dtype=float)
        known = values[~np.isnan(values)]
        if (not np.isfinite(known).all() or (field == "close" and (known <= 0).any())
                or (field == "quote_volume" and (known < 0).any())):
            raise DataQualityError("Invalid normalized panel values")
        absent = panel.isna()
        if [v.isoformat() for v in panel.index[absent.any(axis=1)]] != audit["allowed_missing_endpoints"] or not absent.loc[absent.any(axis=1)].all(axis=1).all():
            raise DataQualityError("Unknown or partial-asset missing prices; no filling allowed")
        panel.attrs = {"bar_minutes": 5, "allowed_missing_endpoints": audit["allowed_missing_endpoints"], "halt_bridges": audit["halt_bridges"]}
        panels.append(panel)
    return panels[0], panels[1], audit


def reconcile_hourly(root: Path, close: pd.DataFrame, volume: pd.DataFrame) -> dict:
    """Compare actual same-venue source bars without editing archived references."""
    reference = Path("/Users/cosdis/Desktop/job/quant_projects/crypto_stat_arb_extensions/datasets/full/data/processed/bars.parquet")
    if not reference.exists():
        raise DataQualityError("Preserved hourly reference unavailable")
    old = pd.read_parquet(reference, columns=["symbol", "close", "quote_volume"])
    hourly_close = old.reset_index().pivot(index="bar_end", columns="symbol", values="close").reindex(columns=SYMBOLS)
    hourly_volume = old.reset_index().pivot(index="bar_end", columns="symbol", values="quote_volume").reindex(columns=SYMBOLS)
    hourly_close.columns.name = hourly_volume.columns.name = None
    common = hourly_close.index.intersection(close.index)
    new_close = close.loc[common]
    old_close = hourly_close.loc[common]
    both = new_close.notna() & old_close.notna()
    mismatch = both & new_close.ne(old_close)
    # Timestamp groups are (previous whole hour, current whole hour]. Source
    # zero-trade bars are preserved. Unknown/missing 5m bins do not become zero.
    sums = volume.resample("h", closed="right", label="right").sum(min_count=12).reindex(common)
    counts = volume.notna().astype(int).resample("h", closed="right", label="right").sum().reindex(common)
    old_volume = hourly_volume.loc[common]
    complete = counts.eq(12) & old_volume.notna()
    difference = sums - old_volume
    matches = np.isclose(sums, old_volume, rtol=1e-12, atol=1e-6)
    volume_mismatch = complete & ~matches
    def records(mask, a, b):
        result = []
        for position, column in np.argwhere(mask.to_numpy()):
            result.append({"bar_end": common[position].isoformat(), "symbol": SYMBOLS[column],
                           "five_minute_value": float(a.iloc[position, column]), "hourly_value": float(b.iloc[position, column]),
                           "difference": float(a.iloc[position, column] - b.iloc[position, column])})
        return result
    evaluation = common >= pd.Timestamp("2022-01-01", tz="UTC")
    prior = ~evaluation
    receipt = {"generated_utc": utc_now(), "reference_path": str(reference), "reference_sha256": sha256_file(reference),
               "reference_read_only": True, "comparison_start": common.min().isoformat(), "comparison_end": common.max().isoformat(),
               "hourly_endpoints": len(common), "price_cells_compared": int(both.to_numpy().sum()),
               "price_exact_mismatch_count": int(mismatch.to_numpy().sum()), "price_mismatches": records(mismatch, new_close, old_close),
               "complete_volume_cells_compared": int(complete.to_numpy().sum()), "volume_mismatch_count": int(volume_mismatch.to_numpy().sum()),
               "volume_mismatches": records(volume_mismatch, sums, old_volume), "volume_sum_rtol": 1e-12, "volume_sum_atol": 1e-6,
               "incomplete_five_minute_volume_cells": int((counts.ne(12) & old_volume.notna()).to_numpy().sum()),
               "incomplete_hours": [v.isoformat() for v in common[counts.ne(12).any(axis=1)]],
               "evaluation_price_cells_compared": int(both.loc[evaluation].to_numpy().sum()),
               "evaluation_price_exact_mismatch_count": int(mismatch.loc[evaluation].to_numpy().sum()),
               "evaluation_volume_mismatch_count": int(volume_mismatch.loc[evaluation].to_numpy().sum()),
               "warmup_price_exact_mismatch_count": int(mismatch.loc[prior].to_numpy().sum()),
               "warmup_volume_mismatch_count": int(volume_mismatch.loc[prior].to_numpy().sum()),
               "warmup_exclusion": "December2021 is not evaluated. Earliest Jan1 signal has maximum30min lookback; source divergences before Dec28 do not touch evaluated lookbacks.",
               "no_price_or_volume_replacements": True,
               "interpretation": "Granularity consistency check, not permission to substitute values; all divergences retained and disclosed"}
    receipt["status"] = "exact_close_and_tolerance_volume_match" if not receipt["price_exact_mismatch_count"] and not receipt["volume_mismatch_count"] else "source_granularity_discrepancies_retained"
    if receipt["evaluation_price_exact_mismatch_count"] or receipt["evaluation_volume_mismatch_count"]:
        receipt["evaluation_source_discrepancy_requires_review"] = True
    else:
        receipt["evaluation_source_discrepancy_requires_review"] = False
    write_json(Path(root) / "outputs/data_hourly_reconciliation.json", receipt)
    return receipt

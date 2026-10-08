"""Checksum-verified Binance Vision candles for non-commercial course research.

No exchange account, trading API, credential, fill, or venue substitution is used.
Spot archive timestamps explicitly switch from milliseconds to microseconds in
January 2025. The normalized index is the *exclusive* UTC hourly bar endpoint.
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

DEFAULT_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "LTCUSDT", "ADAUSDT", "LINKUSDT", "DOGEUSDT",
    "DOTUSDT", "SOLUSDT",
]
BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"
SOURCE_DOC = "https://github.com/binance/binance-public-data"
TERMS_URL = SOURCE_DOC + "/blob/master/TERMS_AND_CONDITIONS.md"
RAW_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "trades", "taker_buy_volume", "taker_buy_quote_volume", "ignore",
]
BAR_COLUMNS = ["symbol", "open", "high", "low", "close", "volume", "quote_volume", "trades"]
UNIT_SWITCH = pd.Timestamp("2025-01-01", tz="UTC")
HALT_SOURCE = "https://www.binance.com/en/blog/from-our-ceo/6789340645608890113"
ALLOWED_MISSING_ENDPOINTS = ["2023-03-24T14:00:00+00:00"]
HALT_BRIDGES = [{"start": "2023-03-24T11:00:00+00:00", "end": "2023-03-24T15:00:00+00:00", "source": HALT_SOURCE}]
# Exact observed source metadata, not a generic timing tolerance. Unknown,
# negative, future, or overlong close timestamps continue to fail validation.
KNOWN_SHORT_CLOSE_TIMES = {
    ("ADAUSDT", 1640318400000): 1640321992654,
    ("BTCUSDT", 1640318400000): 1640321994362,
    ("DOGEUSDT", 1640318400000): 1640321995588,
    ("DOTUSDT", 1640318400000): 1640321995682,
    ("ETHUSDT", 1640318400000): 1640321996158,
    ("LINKUSDT", 1640318400000): 1640321997827,
    ("LTCUSDT", 1640318400000): 1640321998040,
    ("ADAUSDT", 1679659200000): 1679661580151,
    ("BTCUSDT", 1679659200000): 1679661581646,
    ("DOGEUSDT", 1679659200000): 1679661582562,
    ("DOTUSDT", 1679659200000): 1679661582630,
    ("ETHUSDT", 1679659200000): 1679661583061,
    ("LINKUSDT", 1679659200000): 1679661584685,
    ("LTCUSDT", 1679659200000): 1679661584908,
    ("SOLUSDT", 1679659200000): 1679661586948,
}


class DataQualityError(ValueError):
    """Data fails a documented schema, integrity, or coverage requirement."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_timestamp(value: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tz is None else timestamp.tz_convert("UTC")


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _checksum_digest(content: str, filename: str) -> str:
    """Accept standard sha256sum records only, with the intended archive name."""
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if len(lines) != 1:
        raise DataQualityError("Checksum must contain exactly one SHA256 record")
    match = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?(.+)", lines[0])
    if match is None or Path(match.group(2)).name != filename:
        raise DataQualityError(f"Invalid checksum record for {filename}")
    return match.group(1).lower()


def verify_checksum(archive: Path, checksum: Path) -> str:
    expected = _checksum_digest(checksum.read_text(), archive.name)
    actual = _sha256(archive)
    if actual != expected:
        raise DataQualityError(f"SHA256 mismatch for {archive.name}")
    return actual


def _fetch_bytes(url: str, attempts: int = 4) -> bytes:
    last_error = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": "crypto-stat-arb-course-research/1.0"})
            with urlopen(request, timeout=45) as response:
                return response.read()
        except HTTPError as error:
            last_error = error
            if error.code not in (408, 429, 500, 502, 503, 504):
                raise
        except (URLError, TimeoutError, ConnectionError, OSError, IncompleteRead) as error:
            last_error = error
        if attempt + 1 < attempts:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Download failed after {attempts} attempts: {url}") from last_error


def _atomic_bytes(path: Path, content: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def _acquire_archive(raw_root: Path, symbol: str, month: str, old: dict | None = None) -> dict:
    filename = f"{symbol}-1h-{month}.zip"
    url = f"{BASE_URL}/{symbol}/1h/{filename}"
    directory = raw_root / symbol
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / filename
    checksum = directory / (filename + ".CHECKSUM")
    resumed = False
    if archive.exists() and checksum.exists():
        try:
            digest = verify_checksum(archive, checksum)
            resumed = True
        except DataQualityError:
            resumed = False
    if not resumed:
        checksum_content = _fetch_bytes(url + ".CHECKSUM")
        expected = _checksum_digest(checksum_content.decode("utf-8"), filename)
        archive_content = _fetch_bytes(url)
        digest = hashlib.sha256(archive_content).hexdigest()
        if digest != expected:
            # A source replacement during retrieval gets a bounded retry; never
            # overwrite a cached archive with bytes that fail verification.
            for attempt in range(3):
                time.sleep(2 ** attempt)
                checksum_content = _fetch_bytes(url + ".CHECKSUM")
                expected = _checksum_digest(checksum_content.decode("utf-8"), filename)
                archive_content = _fetch_bytes(url)
                digest = hashlib.sha256(archive_content).hexdigest()
                if digest == expected:
                    break
            else:
                raise DataQualityError(f"Downloaded SHA256 mismatch for {filename}")
        _atomic_bytes(archive, archive_content)
        _atomic_bytes(checksum, checksum_content)
    return {
        "symbol": symbol, "month": month, "interval": "1h",
        "archive_path": str(archive.relative_to(raw_root.parent.parent)),
        "source_url": url, "checksum_url": url + ".CHECKSUM", "sha256": digest,
        "checksum_sha256": _sha256(checksum), "bytes": archive.stat().st_size,
        "downloaded_utc": (old or {}).get(
            "downloaded_utc", datetime.fromtimestamp(archive.stat().st_mtime, timezone.utc).isoformat()
        ) if resumed else _utc_now(),
        "verified_utc": _utc_now(), "resumed_checksum_cache": resumed,
        "timestamp_unit": "us" if month >= "2025-01" else "ms",
    }


def _prepare_sol_metadata_repair(root: Path) -> dict:
    """Retain a verified same-venue daily source; change exactly one metadata field."""
    directory = root / "data/raw/repairs"
    directory.mkdir(parents=True, exist_ok=True)
    filename = "SOLUSDT-1h-2021-12-24.zip"
    url = f"https://data.binance.vision/data/spot/daily/klines/SOLUSDT/1h/{filename}"
    archive, checksum = directory / filename, directory / (filename + ".CHECKSUM")
    if not (archive.exists() and checksum.exists()):
        checksum_bytes = _fetch_bytes(url + ".CHECKSUM")
        archive_bytes = _fetch_bytes(url)
        expected = _checksum_digest(checksum_bytes.decode(), filename)
        if hashlib.sha256(archive_bytes).hexdigest() != expected:
            raise DataQualityError("Official daily repair archive checksum mismatch")
        _atomic_bytes(archive, archive_bytes)
        _atomic_bytes(checksum, checksum_bytes)
    digest = verify_checksum(archive, checksum)
    monthly = root / "data/raw/SOLUSDT/SOLUSDT-1h-2021-12.zip"
    def source_row(path: Path) -> list[str]:
        with ZipFile(path) as zipped:
            rows = list(csv.reader(zipped.read(path.stem + ".csv").decode().splitlines()))
        matches = [row for row in rows if row[0] == "1640318400000"]
        if len(matches) != 1 or len(matches[0]) != 12:
            raise DataQualityError("Official repair source lacks the unique intended 12-field row")
        return matches[0]
    original, corrected = source_row(monthly), source_row(archive)
    differing_columns = [index for index, values in enumerate(zip(original, corrected)) if values[0] != values[1]]
    if (differing_columns != [6] or original[6] != "1640322000475" or
            corrected[6] != "1640321999999"):
        raise DataQualityError("Official repair must match every original field except exact close_time")
    record = {
        "symbol": "SOLUSDT", "open_time": 1640318400000, "timestamp_unit": "ms",
        "original_close_time": 1640322000475, "corrected_close_time": 1640321999999,
        "original_monthly_path": str(monthly.relative_to(root)), "original_monthly_sha256": _sha256(monthly),
        "official_daily_path": str(archive.relative_to(root)), "source_url": url,
        "checksum_url": url + ".CHECKSUM", "sha256": digest, "checksum_sha256": _sha256(checksum),
        "downloaded_utc": datetime.fromtimestamp(archive.stat().st_mtime, timezone.utc).isoformat(),
        "verified_utc": _utc_now(), "original_raw_row": original, "official_daily_raw_row": corrected,
        "changed_columns": ["close_time"], "all_other_fields_byte_identical": True,
        "original_monthly_retained": True, "price_or_volume_repair": False,
    }
    _write_json(directory / "manifest.json", {
        "source": "Binance Vision", "license": "CC BY-NC-SA 4.0", "attribution": "Source: Binance Vision",
        "terms_url": TERMS_URL, "repairs": [record],
    })
    return record


def normalize_archive(archive: Path, symbol: str, month: str, *,
                      allow_documented_exceptions: bool = False, repair_record: dict | None = None) -> pd.DataFrame:
    """Parse one exact monthly 1h archive, rejecting invalid or duplicate rows."""
    try:
        with ZipFile(archive) as zipped:
            expected_csv = archive.stem + ".csv"
            files = [name for name in zipped.namelist() if not name.endswith("/")]
            if files != [expected_csv]:
                raise DataQualityError(f"Unexpected ZIP members: {archive.name}: {files}")
            frame = pd.read_csv(io.BytesIO(zipped.read(expected_csv)), header=None, dtype=str)
    except (BadZipFile, pd.errors.ParserError, pd.errors.EmptyDataError) as error:
        raise DataQualityError(f"Invalid archive: {archive.name}") from error
    if frame.shape[1] != len(RAW_COLUMNS) or frame.empty:
        raise DataQualityError(f"Expected nonempty 12-column kline schema: {archive.name}")
    frame.columns = RAW_COLUMNS
    raw_frame = frame.copy()
    try:
        frame = frame.apply(pd.to_numeric, errors="raise")
    except (ValueError, TypeError) as error:
        raise DataQualityError(f"Non-numeric kline values: {archive.name}") from error
    if not np.isfinite(frame.to_numpy()).all():
        raise DataQualityError(f"Non-finite kline values: {archive.name}")
    for column in ("open_time", "close_time", "trades"):
        if not (frame[column] == np.floor(frame[column])).all():
            raise DataQualityError(f"Noninteger {column}: {archive.name}")
        frame[column] = frame[column].astype("int64")
    prices = frame[["open", "high", "low", "close"]]
    if (prices <= 0).any().any():
        raise DataQualityError(f"Nonpositive price: {archive.name}")
    if ((frame["low"] > prices.min(axis=1)) | (frame["high"] < prices.max(axis=1))).any():
        raise DataQualityError(f"OHLC ordering violation: {archive.name}")
    quantities = frame[["volume", "quote_volume", "trades", "taker_buy_volume", "taker_buy_quote_volume"]]
    if (quantities < 0).any().any():
        raise DataQualityError(f"Negative volume/trades: {archive.name}")
    if ((frame.taker_buy_volume > frame.volume + 1e-8) |
            (frame.taker_buy_quote_volume > frame.quote_volume + 1e-6)).any():
        raise DataQualityError(f"Taker volume exceeds total volume: {archive.name}")
    month_start = pd.Timestamp(f"{month}-01", tz="UTC")
    month_end = month_start + pd.offsets.MonthBegin(1)
    unit = "us" if month_start >= UNIT_SWITCH else "ms"
    scale = 1_000_000 if unit == "us" else 1_000
    expected_close = frame.open_time + 3600 * scale - 1
    anomalies = []
    for index in frame.index[frame.close_time != expected_close]:
        opened, closed = int(frame.loc[index, "open_time"]), int(frame.loc[index, "close_time"])
        anomaly = {
            "symbol": symbol, "archive": archive.name, "timestamp_unit": unit,
            "raw_open_time": opened, "raw_close_time": closed,
            "open_time_utc": pd.to_datetime(opened, unit=unit, utc=True).isoformat(),
            "raw_close_time_utc": pd.to_datetime(closed, unit=unit, utc=True).isoformat(),
            "expected_close_time": int(expected_close[index]),
            "offset_from_expected_seconds": (closed - int(expected_close[index])) / scale,
        }
        if (repair_record and symbol == repair_record["symbol"] and opened == repair_record["open_time"]):
            if (_sha256(archive) != repair_record["original_monthly_sha256"] or
                    raw_frame.loc[index].tolist() != repair_record["original_raw_row"] or
                    repair_record.get("all_other_fields_byte_identical") is not True or
                    repair_record["changed_columns"] != ["close_time"]):
                raise DataQualityError("Source bytes no longer match the documented official metadata repair")
            frame.loc[index, "close_time"] = repair_record["corrected_close_time"]
            if frame.loc[index, "close_time"] != expected_close[index]:
                raise DataQualityError("Official metadata repair has invalid endpoint")
            anomaly["policy"] = "official_daily_close_time_repair_only"
        elif (allow_documented_exceptions and unit == "ms" and
              KNOWN_SHORT_CLOSE_TIMES.get((symbol, opened)) == closed and
              opened <= closed < int(expected_close[index])):
            anomaly["policy"] = "documented_shortened_source_metadata_warning"
        else:
            raise DataQualityError(f"Close time not endpoint-minus-one {unit}: {archive.name}")
        anomalies.append(anomaly)
    if not (frame.open_time % (3600 * scale) == 0).all():
        raise DataQualityError(f"Open time is not an aligned UTC hour: {archive.name}")
    try:
        open_time = pd.to_datetime(frame.open_time, unit=unit, utc=True)
    except (ValueError, OverflowError) as error:
        raise DataQualityError(f"Invalid {unit} timestamps: {archive.name}") from error
    if not ((open_time >= month_start) & (open_time < month_end)).all():
        raise DataQualityError(f"Timestamp outside archive month: {archive.name}")
    if open_time.duplicated().any():
        raise DataQualityError(f"Duplicate hourly bars: {archive.name}")
    normalized = frame[[column for column in BAR_COLUMNS if column != "symbol"]].copy()
    normalized.insert(0, "symbol", symbol)
    normalized.index = pd.DatetimeIndex(open_time + pd.Timedelta(hours=1), name="bar_end")
    normalized = normalized.sort_index()
    normalized.attrs["original_close_time_anomalies"] = anomalies
    return normalized


def audit_bars(bars: pd.DataFrame, symbols: list[str], start: pd.Timestamp, end: pd.Timestamp, *,
               allow_documented_halt: bool = False) -> dict:
    """Audit actual rows against a full exclusive-end UTC hourly grid; never fill."""
    if start.tz is None or end.tz is None:
        raise DataQualityError("Coverage bounds must be timezone-aware")
    expected = pd.date_range(start + pd.Timedelta(hours=1), end, freq="h", name="bar_end")
    duplicate_count = int(bars.reset_index().duplicated(["bar_end", "symbol"]).sum())
    per_symbol = {}
    for symbol in symbols:
        rows = bars[bars.symbol == symbol]
        observed = pd.DatetimeIndex(rows.index).unique()
        missing = expected.difference(observed)
        extra = observed.difference(expected)
        per_symbol[symbol] = {
            "rows": len(rows), "expected_rows": len(expected),
            "coverage_fraction": len(expected.intersection(observed)) / len(expected),
            "first_bar_end": rows.index.min().isoformat() if len(rows) else None,
            "last_bar_end": rows.index.max().isoformat() if len(rows) else None,
            "missing_count": len(missing), "missing_bar_ends": [value.isoformat() for value in missing],
            "extra_count": len(extra), "extra_bar_ends": [value.isoformat() for value in extra],
            "zero_volume_count": int((rows.volume == 0).sum()),
            "zero_trades_count": int((rows.trades == 0).sum()),
        }
    missing_count = sum(item["missing_count"] for item in per_symbol.values())
    extra_count = sum(item["extra_count"] for item in per_symbol.values())
    unexpected = sorted(set(bars.symbol) - set(symbols))
    status = "pass" if missing_count == extra_count == duplicate_count == 0 and not unexpected else "fail"
    if (allow_documented_halt and set(symbols) == set(DEFAULT_SYMBOLS) and not unexpected and
            missing_count == 8 and extra_count == duplicate_count == 0 and
            all(item["missing_bar_ends"] == ALLOWED_MISSING_ENDPOINTS for item in per_symbol.values())):
        status = "pass_with_documented_exceptions"
    return {
        "status": status,
        "generated_utc": _utc_now(), "source": "Binance Vision spot monthly klines",
        "symbols": symbols, "start_open_time": start.isoformat(), "end_open_time_exclusive": end.isoformat(),
        "bar_endpoint": "exclusive hourly endpoint: open_time + 1 hour",
        "timezone": "UTC", "interval": "1h", "rows": len(bars),
        "expected_rows": len(expected) * len(symbols), "hourly_panel_rows": len(expected),
        "missing_count": missing_count, "extra_count": extra_count,
        "duplicate_count": duplicate_count, "unexpected_symbols": unexpected,
        "per_symbol": per_symbol, "implicit_fill": False, "cross_venue_substitution": False,
        "allowed_missing_endpoints": ALLOWED_MISSING_ENDPOINTS if status == "pass_with_documented_exceptions" else [],
        "halt_bridges": HALT_BRIDGES if status == "pass_with_documented_exceptions" else [],
        "halt_policy": "Positions retained; no valuation or execution inside the documented observed-interval bridge; no filled prices",
        "timestamp_units": {"before_2025-01-01": "ms", "from_2025-01-01": "us"},
        "license": "CC BY-NC-SA 4.0; non-commercial research only",
        "attribution": "Source: Binance Vision (data.binance.vision)", "terms_url": TERMS_URL,
    }


def download_and_prepare(root: Path, config: dict) -> dict:
    """Acquire, verify, normalize, and audit monthly archives; return audit dict.

    Gaps are recorded in data_quality.json and retained without repair. A caller
    must halt research on failed coverage; load_panel enforces that requirement.
    """
    root = Path(root).resolve()
    settings = config["data"]
    symbols = list(settings.get("symbols", DEFAULT_SYMBOLS))
    if not symbols or len(set(symbols)) != len(symbols) or any(not re.fullmatch(r"[A-Z0-9]+", s) for s in symbols):
        raise ValueError("Provide unique uppercase alphanumeric Binance symbols")
    if settings.get("interval", "1h") != "1h":
        raise ValueError("This course normalizer supports 1h data only")
    start, end = _utc_timestamp(settings["start"]), _utc_timestamp(settings["end"])
    if start >= end or start != start.normalize() or end != end.normalize():
        raise ValueError("Require increasing midnight UTC dates")
    if start.day != 1 or end.day != 1:
        raise ValueError("Require full monthly acquisition bounds, end exclusive")
    raw_root, processed = root / "data/raw", root / "data/processed"
    raw_root.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    manifest_path = raw_root / "manifest.json"
    old_manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    old_entries = {(entry["symbol"], entry["month"]): entry for entry in old_manifest.get("files", [])}
    months = pd.date_range(start, end, freq="MS", inclusive="left").strftime("%Y-%m").tolist()
    tasks = [(symbol, month) for symbol in symbols for month in months]
    records, failures = [], []
    workers = min(4, max(1, int(settings.get("download_workers", 4))))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_acquire_archive, raw_root, symbol, month,
                                  old_entries.get((symbol, month))): (symbol, month) for symbol, month in tasks}
        for done, future in enumerate(as_completed(futures), start=1):
            symbol, month = futures[future]
            try:
                records.append(future.result())
            except Exception as error:
                failures.append({"symbol": symbol, "month": month, "error": str(error)})
            if done % 32 == 0 or done == len(tasks):
                print(f"Archives verified: {len(records)}/{len(tasks)}; failures: {len(failures)}", flush=True)
    records.sort(key=lambda record: (symbols.index(record["symbol"]), record["month"]))
    manifest = {
        "source": "Binance Vision", "source_documentation": SOURCE_DOC, "terms_url": TERMS_URL,
        "license": "CC BY-NC-SA 4.0", "use": "non-commercial educational historical backtesting",
        "attribution": "Source: Binance Vision (data.binance.vision)",
        "generated_utc": _utc_now(), "symbols": symbols, "interval": "1h",
        "start": start.isoformat(), "end_exclusive": end.isoformat(),
        "expected_archive_count": len(tasks), "verified_archive_count": len(records),
        "total_archive_bytes": sum(record["bytes"] for record in records),
        "files": records, "acquisition_failures": failures,
    }
    _write_json(manifest_path, manifest)
    if failures:
        _write_json(processed / "data_quality.json", {"status": "fail", "acquisition_failures": failures})
        raise DataQualityError(f"{len(failures)} archives failed acquisition; see raw manifest")
    frames, original_metadata_anomalies = [], []
    repair_record = (_prepare_sol_metadata_repair(root)
                     if "SOLUSDT" in symbols and "2021-12" in months else None)
    manifest["official_metadata_repairs"] = [repair_record] if repair_record else []
    try:
        for record in records:
            frame = normalize_archive(root / record["archive_path"], record["symbol"], record["month"],
                                      allow_documented_exceptions=True, repair_record=repair_record)
            original_metadata_anomalies.extend(frame.attrs["original_close_time_anomalies"])
            record["original_close_time_anomalies"] = frame.attrs["original_close_time_anomalies"]
            frames.append(frame)
            record["rows"] = len(frame)
            record["first_bar_end"] = frame.index.min().isoformat()
            record["last_bar_end"] = frame.index.max().isoformat()
    except DataQualityError as error:
        _write_json(manifest_path, manifest)
        _write_json(processed / "data_quality.json", {"status": "fail", "schema_error": str(error)})
        raise
    bars = pd.concat(frames).reset_index().sort_values(["bar_end", "symbol"]).set_index("bar_end")
    audit = audit_bars(bars, symbols, start, end, allow_documented_halt=True)
    audit["n_rawrows"] = len(bars)
    audit["n_elapsed_hours"] = audit["hourly_panel_rows"]
    audit["original_close_time_anomaly_count"] = len(original_metadata_anomalies)
    audit["original_close_time_anomalies"] = original_metadata_anomalies
    audit["official_metadata_repair_count"] = sum(a["policy"] == "official_daily_close_time_repair_only" for a in original_metadata_anomalies)
    audit["remaining_metadata_warning_count"] = sum(a["policy"] == "documented_shortened_source_metadata_warning" for a in original_metadata_anomalies)
    audit["official_metadata_repairs"] = [repair_record] if repair_record else []
    audit["archive_count"] = len(records)
    audit["verified_archive_bytes"] = manifest["total_archive_bytes"]
    parquet_path = processed / "bars.parquet"
    temporary = processed / "bars.parquet.tmp"
    bars.to_parquet(temporary, engine="pyarrow", index=True)
    temporary.replace(parquet_path)
    audit["normalized_parquet_sha256"] = _sha256(parquet_path)
    _write_json(processed / "data_quality.json", audit)
    _write_json(manifest_path, manifest)
    print(f"Data audit {audit['status']}: {audit['rows']} rows; {audit['missing_count']} missing; "
          f"{audit['duplicate_count']} duplicates", flush=True)
    return audit


def load_panel(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Load verified panels, preserving only the documented halt's absent hour."""
    processed = Path(root) / "data/processed"
    audit = json.loads((processed / "data_quality.json").read_text())
    if audit.get("status") not in ("pass", "pass_with_documented_exceptions"):
        raise DataQualityError("Data quality gate failed; inspect data/processed/data_quality.json")
    parquet = processed / "bars.parquet"
    if _sha256(parquet) != audit["normalized_parquet_sha256"]:
        raise DataQualityError("Normalized parquet no longer matches audited SHA256")
    bars = pd.read_parquet(parquet)
    if not isinstance(bars.index, pd.DatetimeIndex) or str(bars.index.tz) != "UTC" or bars.index.name != "bar_end":
        raise DataQualityError("Expected UTC bar_end DatetimeIndex")
    if list(bars.columns) != BAR_COLUMNS:
        raise DataQualityError("Unexpected normalized bar columns")
    symbols = audit["symbols"]
    current_audit = audit_bars(bars, symbols, _utc_timestamp(audit["start_open_time"]),
                               _utc_timestamp(audit["end_open_time_exclusive"]), allow_documented_halt=True)
    if current_audit["status"] != audit["status"]:
        raise DataQualityError("Normalized coverage no longer matches the audit")
    expected_index = pd.date_range(_utc_timestamp(audit["start_open_time"]) + pd.Timedelta(hours=1),
                                  _utc_timestamp(audit["end_open_time_exclusive"]), freq="h", name="bar_end")
    close = bars.reset_index().pivot(index="bar_end", columns="symbol", values="close").reindex(index=expected_index, columns=symbols)
    quote_volume = bars.reset_index().pivot(index="bar_end", columns="symbol", values="quote_volume").reindex(index=expected_index, columns=symbols)
    close.columns.name = quote_volume.columns.name = None
    for panel in (close, quote_volume):
        if np.isinf(panel.to_numpy()).any():
            raise DataQualityError("Nonfinite normalized panel values")
        missing = panel.index[panel.isna().any(axis=1)].strftime("%Y-%m-%dT%H:%M:%S%z").tolist()
        expected_missing = [pd.Timestamp(value).strftime("%Y-%m-%dT%H:%M:%S%z")
                            for value in current_audit["allowed_missing_endpoints"]]
        if missing != expected_missing or any(not panel.loc[stamp].isna().all() for stamp in panel.index[panel.isna().any(axis=1)]):
            raise DataQualityError("Unknown missing panel values; no implicit fill is allowed")
        if panel.notna().any().any() and not np.isfinite(panel.to_numpy()[panel.notna().to_numpy()]).all():
            raise DataQualityError("Nonfinite normalized panel values")
        panel.attrs["allowed_missing_endpoints"] = current_audit["allowed_missing_endpoints"]
        panel.attrs["halt_bridges"] = current_audit["halt_bridges"]
    return close, quote_volume, audit

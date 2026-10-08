from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile
import json

import pandas as pd
import pytest

from crypto_stat_arb.data import (
    ALLOWED_MISSING_ENDPOINTS, DEFAULT_SYMBOLS, DataQualityError, _acquire_archive,
    _fetch_bytes, _prepare_sol_metadata_repair, audit_bars, load_panel, normalize_archive, verify_checksum,
)


def _row(timestamp: str, unit: str = "ms") -> list:
    scale = 1_000_000 if unit == "us" else 1_000
    opened = pd.Timestamp(timestamp).value // (1_000 if unit == "us" else 1_000_000)
    return [opened, 100, 105, 95, 102, 10, opened + 3600 * scale - 1, 1000, 20, 5, 500, 0]


def _archive(tmp_path: Path, month: str, rows: list[list], symbol="BTCUSDT") -> Path:
    path = tmp_path / f"{symbol}-1h-{month}.zip"
    with ZipFile(path, "w") as zipped:
        zipped.writestr(path.stem + ".csv", "\n".join(",".join(map(str, row)) for row in rows))
    return path


@pytest.mark.parametrize("month,stamp,unit,endpoint", [
    ("2024-12", "2024-12-31T23:00:00Z", "ms", "2025-01-01T00:00:00Z"),
    ("2025-01", "2025-01-01T00:00:00Z", "us", "2025-01-01T01:00:00Z"),
])
def test_explicit_timestamp_boundary(tmp_path, month, stamp, unit, endpoint):
    path = _archive(tmp_path, month, [_row(stamp, unit)])
    frame = normalize_archive(path, "BTCUSDT", month)
    assert frame.index.name == "bar_end"
    assert str(frame.index.tz) == "UTC"
    assert frame.index[0] == pd.Timestamp(endpoint)
    assert frame.iloc[0]["trades"] == 20


def test_wrong_post_switch_units_rejected(tmp_path):
    path = _archive(tmp_path, "2025-01", [_row("2025-01-01T00:00:00Z", "ms")])
    with pytest.raises(DataQualityError):
        normalize_archive(path, "BTCUSDT", "2025-01")


@pytest.mark.parametrize("column,value,match", [
    (1, 0, "Nonpositive"), (2, 99, "ordering"), (3, 103, "ordering"),
    (5, -1, "Negative"), (8, 1.5, "Noninteger"), (4, float("nan"), "Non-finite"),
    (6, 123, "Close time"), (9, 50, "Taker volume"),
])
def test_invalid_schema_values(tmp_path, column, value, match):
    row = _row("2024-12-01T00:00:00Z")
    row[column] = value
    with pytest.raises(DataQualityError, match=match):
        normalize_archive(_archive(tmp_path, "2024-12", [row]), "BTCUSDT", "2024-12")


def test_wrong_column_count(tmp_path):
    row = _row("2024-12-01T00:00:00Z")[:-1]
    with pytest.raises(DataQualityError, match="12-column"):
        normalize_archive(_archive(tmp_path, "2024-12", [row]), "BTCUSDT", "2024-12")


def test_duplicate_bar_rejected(tmp_path):
    row = _row("2024-12-01T00:00:00Z")
    with pytest.raises(DataQualityError, match="Duplicate"):
        normalize_archive(_archive(tmp_path, "2024-12", [row, row]), "BTCUSDT", "2024-12")


def test_gap_audit_does_not_fill(tmp_path):
    rows = [_row("2024-12-01T00:00:00Z"), _row("2024-12-01T02:00:00Z")]
    frame = normalize_archive(_archive(tmp_path, "2024-12", rows), "BTCUSDT", "2024-12")
    audit = audit_bars(frame, ["BTCUSDT"], pd.Timestamp("2024-12-01T00:00:00Z"),
                       pd.Timestamp("2024-12-01T03:00:00Z"))
    assert audit["status"] == "fail"
    assert audit["missing_count"] == 1
    assert audit["per_symbol"]["BTCUSDT"]["missing_bar_ends"] == ["2024-12-01T02:00:00+00:00"]
    assert len(frame) == 2
    assert audit["implicit_fill"] is False


def test_checksum_verified_and_mismatch_rejected(tmp_path):
    archive = _archive(tmp_path, "2024-12", [_row("2024-12-01T00:00:00Z")])
    checksum = archive.with_name(archive.name + ".CHECKSUM")
    digest = sha256(archive.read_bytes()).hexdigest()
    checksum.write_text(f"{digest}  {archive.name}\n")
    assert verify_checksum(archive, checksum) == digest
    archive.write_bytes(b"corrupted")
    with pytest.raises(DataQualityError, match="mismatch"):
        verify_checksum(archive, checksum)


def test_checksum_filename_validated(tmp_path):
    archive = _archive(tmp_path, "2024-12", [_row("2024-12-01T00:00:00Z")])
    checksum = archive.with_name(archive.name + ".CHECKSUM")
    checksum.write_text(f"{sha256(archive.read_bytes()).hexdigest()}  wrong.zip\n")
    with pytest.raises(DataQualityError, match="Invalid checksum"):
        verify_checksum(archive, checksum)


def test_verified_archive_resumes_without_network(tmp_path, monkeypatch):
    raw = tmp_path / "data/raw"
    directory = raw / "BTCUSDT"
    directory.mkdir(parents=True)
    archive = _archive(directory, "2024-12", [_row("2024-12-01T00:00:00Z")])
    digest = sha256(archive.read_bytes()).hexdigest()
    archive.with_name(archive.name + ".CHECKSUM").write_text(f"{digest}  {archive.name}\n")
    def unexpected_network(*args, **kwargs):
        pytest.fail("A checksum-valid cached archive must not be redownloaded")
    monkeypatch.setattr("crypto_stat_arb.data._fetch_bytes", unexpected_network)
    record = _acquire_archive(raw, "BTCUSDT", "2024-12", {"downloaded_utc": "2026-01-01T00:00:00+00:00"})
    assert record["resumed_checksum_cache"]
    assert record["sha256"] == digest
    assert record["downloaded_utc"] == "2026-01-01T00:00:00+00:00"


def test_fetch_transient_failure_retries(monkeypatch):
    from urllib.error import HTTPError
    calls = []
    sleeps = []
    def failing_request(*args, **kwargs):
        calls.append(1)
        raise HTTPError("https://example.invalid", 503, "Unavailable", {}, None)
    monkeypatch.setattr("crypto_stat_arb.data.urlopen", failing_request)
    monkeypatch.setattr("crypto_stat_arb.data.time.sleep", sleeps.append)
    with pytest.raises(RuntimeError, match="3 attempts"):
        _fetch_bytes("https://example.invalid", attempts=3)
    assert len(calls) == 3
    assert sleeps == [1, 2]


def test_fetch_not_found_does_not_retry(monkeypatch):
    from urllib.error import HTTPError
    calls = []
    def missing_request(*args, **kwargs):
        calls.append(1)
        raise HTTPError("https://example.invalid", 404, "Not found", {}, None)
    monkeypatch.setattr("crypto_stat_arb.data.urlopen", missing_request)
    with pytest.raises(HTTPError):
        _fetch_bytes("https://example.invalid")
    assert len(calls) == 1


def test_only_exact_known_shortened_metadata_allowed(tmp_path):
    row = _row("2021-12-24T04:00:00Z")
    row[6] = 1640321994362
    path = _archive(tmp_path, "2021-12", [row])
    frame = normalize_archive(path, "BTCUSDT", "2021-12", allow_documented_exceptions=True)
    assert frame.index[0] == pd.Timestamp("2021-12-24T05:00:00Z")
    assert frame.attrs["original_close_time_anomalies"][0]["raw_close_time"] == row[6]
    row[6] += 1
    with pytest.raises(DataQualityError, match="Close time"):
        normalize_archive(_archive(tmp_path, "2021-12", [row]), "BTCUSDT", "2021-12",
                          allow_documented_exceptions=True)


def test_unknown_future_metadata_still_fails(tmp_path):
    row = _row("2021-12-24T04:00:00Z")
    row[6] += 1
    with pytest.raises(DataQualityError, match="Close time"):
        normalize_archive(_archive(tmp_path, "2021-12", [row]), "BTCUSDT", "2021-12",
                          allow_documented_exceptions=True)


def test_official_same_venue_repair_changes_only_close_metadata(tmp_path):
    monthly_directory, repair_directory = tmp_path / "data/raw/SOLUSDT", tmp_path / "data/raw/repairs"
    monthly_directory.mkdir(parents=True)
    repair_directory.mkdir(parents=True)
    row = _row("2021-12-24T04:00:00Z")
    row[6] = 1640322000475
    monthly = _archive(monthly_directory, "2021-12", [row], "SOLUSDT")
    original_bytes = monthly.read_bytes()
    corrected = row.copy()
    corrected[6] = 1640321999999
    daily = _archive(repair_directory, "2021-12-24", [corrected], "SOLUSDT")
    daily.with_name(daily.name + ".CHECKSUM").write_text(f"{sha256(daily.read_bytes()).hexdigest()}  {daily.name}\n")
    record = _prepare_sol_metadata_repair(tmp_path)
    frame = normalize_archive(monthly, "SOLUSDT", "2021-12", repair_record=record)
    assert record["all_other_fields_byte_identical"]
    assert record["changed_columns"] == ["close_time"]
    assert monthly.read_bytes() == original_bytes
    assert frame.iloc[0]["close"] == row[4]
    assert frame.attrs["original_close_time_anomalies"][0]["policy"] == "official_daily_close_time_repair_only"
    corrected[4] += 1
    daily = _archive(repair_directory, "2021-12-24", [corrected], "SOLUSDT")
    daily.with_name(daily.name + ".CHECKSUM").write_text(f"{sha256(daily.read_bytes()).hexdigest()}  {daily.name}\n")
    with pytest.raises(DataQualityError, match="every original field"):
        _prepare_sol_metadata_repair(tmp_path)


def _halt_bars():
    endpoints = pd.date_range("2023-03-24T11:00:00Z", "2023-03-24T16:00:00Z", freq="h")
    endpoints = endpoints.drop(pd.Timestamp(ALLOWED_MISSING_ENDPOINTS[0]))
    bars = pd.DataFrame([
        {"bar_end": endpoint, "symbol": symbol, "open": 100., "high": 101., "low": 99.,
         "close": 100., "volume": 10., "quote_volume": 1000., "trades": 20}
        for endpoint in endpoints for symbol in DEFAULT_SYMBOLS
    ]).set_index("bar_end")
    return bars


def test_exact_all_asset_halt_gap_allowed_but_extra_gap_fails():
    bars = _halt_bars()
    start, end = pd.Timestamp("2023-03-24T10:00:00Z"), pd.Timestamp("2023-03-24T16:00:00Z")
    audit = audit_bars(bars, DEFAULT_SYMBOLS, start, end, allow_documented_halt=True)
    assert audit["status"] == "pass_with_documented_exceptions"
    assert audit["missing_count"] == 8
    assert audit["implicit_fill"] is False
    failed = audit_bars(bars.iloc[1:], DEFAULT_SYMBOLS, start, end, allow_documented_halt=True)
    assert failed["status"] == "fail"


@pytest.mark.parametrize("corruption", [None, "nan", "inf"])
def test_loader_preserves_halt_nan_attributes_and_rejects_other_invalid_values(tmp_path, corruption):
    bars = _halt_bars()
    if corruption:
        bars.iloc[0, bars.columns.get_loc("close")] = float(corruption)
    processed = tmp_path / "data/processed"
    processed.mkdir(parents=True)
    parquet = processed / "bars.parquet"
    bars.to_parquet(parquet)
    audit = audit_bars(bars, DEFAULT_SYMBOLS, pd.Timestamp("2023-03-24T10:00:00Z"),
                       pd.Timestamp("2023-03-24T16:00:00Z"), allow_documented_halt=True)
    audit["normalized_parquet_sha256"] = sha256(parquet.read_bytes()).hexdigest()
    (processed / "data_quality.json").write_text(json.dumps(audit))
    if corruption:
        with pytest.raises(DataQualityError):
            load_panel(tmp_path)
    else:
        close, quote_volume, loaded = load_panel(tmp_path)
        assert close.loc[ALLOWED_MISSING_ENDPOINTS[0]].isna().all()
        assert int(close.isna().sum().sum()) == 8
        assert close.shape == (6, 8)
        assert list(close.columns) == DEFAULT_SYMBOLS
        assert close.attrs["allowed_missing_endpoints"] == ALLOWED_MISSING_ENDPOINTS
        assert quote_volume.attrs["halt_bridges"] == close.attrs["halt_bridges"]

"""Synthetic source-integrity checks; no external downloads or strategy runs."""
from pathlib import Path
from zipfile import ZipFile
import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from crypto_intraday_5m import data


def row(stamp="2024-01-01T00:00:00Z", **changes):
    timestamp = pd.Timestamp(stamp)
    unit = "us" if timestamp >= data.UNIT_SWITCH else "ms"
    scale = 1_000_000 if unit == "us" else 1000
    opened = int(timestamp.timestamp()) * scale
    values = [opened, 100, 102, 99, 101, 10, opened + 300 * scale - 1, 1010, 4, 4, 404, 0]
    for column, value in changes.items():
        values[data.RAW_COLUMNS.index(column)] = value
    return [str(v) for v in values]


def archive(tmp_path, rows, symbol="BTCUSDT", month="2024-01", name=None):
    path = tmp_path / (name or f"{symbol}-5m-{month}.zip")
    with ZipFile(path, "w") as zipped:
        zipped.writestr(path.stem + ".csv", "\n".join(",".join(r) for r in rows) + "\n")
    return path


@pytest.mark.parametrize("stamp,month", [("2024-01-01T00:00:00Z", "2024-01"), ("2025-01-01T00:00:00Z", "2025-01")])
def test_timestamp_unit_switch_and_completed_endpoint(tmp_path, stamp, month):
    path = archive(tmp_path, [row(stamp)], month=month)
    frame = data.normalize_archive(path, "BTCUSDT", month)
    assert frame.index[0] == pd.Timestamp(stamp) + pd.Timedelta(minutes=5)
    assert str(frame.index.tz) == "UTC"
    assert list(frame.columns) == data.BAR_COLUMNS
    assert frame.loc[frame.index[0], "close"] == 101


def test_millisecond_data_rejected_after_unit_switch(tmp_path):
    wrong = row("2024-01-01T00:00:00Z")
    path = archive(tmp_path, [wrong], month="2025-01")
    with pytest.raises(data.DataQualityError):
        data.normalize_archive(path, "BTCUSDT", "2025-01")


def test_checksum_valid_binary_marker(tmp_path):
    path = archive(tmp_path, [row()])
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    checksum = path.with_name(path.name + ".CHECKSUM")
    checksum.write_text(f"{digest} *{path.name}\n")
    assert data.verify_checksum(path, checksum) == digest


@pytest.mark.parametrize("content", ["nope", "f" * 64 + " wrong.zip", "f" * 64 + " ../BTCUSDT-5m-2024-01.zip", "f" * 64 + " BTCUSDT-5m-2024-01.zip\n" + "e" * 64 + " BTCUSDT-5m-2024-01.zip"])
def test_checksum_rejects_malformed_wrong_or_multiple_record(content):
    with pytest.raises(data.DataQualityError):
        data.checksum_digest(content, "BTCUSDT-5m-2024-01.zip")


def test_checksum_content_mutation_fails(tmp_path):
    path = archive(tmp_path, [row()])
    checksum = path.with_name(path.name + ".CHECKSUM")
    checksum.write_text(hashlib.sha256(path.read_bytes()).hexdigest() + " " + path.name)
    path.write_bytes(path.read_bytes() + b"tampered")
    with pytest.raises(data.DataQualityError, match="SHA256"):
        data.verify_checksum(path, checksum)


@pytest.mark.parametrize("changes", [
    {"close": "nan"}, {"close": "inf"}, {"open": 0}, {"low": 101}, {"high": 100},
    {"volume": -1}, {"quote_volume": -1}, {"trades": -1}, {"trades": 1.5},
    {"taker_buy_volume": 11}, {"taker_buy_quote_volume": 1011}, {"ignore": 1},
    {"open_time": 1704067200001}, {"close_time": 1704067500000}, {"close_time": 1704067499998},
])
def test_invalid_schema_values_fail(tmp_path, changes):
    path = archive(tmp_path, [row(**changes)])
    with pytest.raises(data.DataQualityError):
        data.normalize_archive(path, "BTCUSDT", "2024-01")


def test_duplicate_candles_fail(tmp_path):
    path = archive(tmp_path, [row(), row()])
    with pytest.raises(data.DataQualityError, match="Duplicate"):
        data.normalize_archive(path, "BTCUSDT", "2024-01")


def test_wrong_archive_month_fails(tmp_path):
    path = archive(tmp_path, [row("2024-02-01T00:00:00Z")])
    with pytest.raises(data.DataQualityError, match="month"):
        data.normalize_archive(path, "BTCUSDT", "2024-01")


@pytest.mark.parametrize("bad_rows", [[row()[:-1]], [row() + ["0"]], []])
def test_csv_schema_width_or_empty_fails(tmp_path, bad_rows):
    path = archive(tmp_path, bad_rows)
    with pytest.raises(data.DataQualityError, match="12-column"):
        data.normalize_archive(path, "BTCUSDT", "2024-01")


def test_unexpected_zip_member_fails(tmp_path):
    path = archive(tmp_path, [row()])
    with ZipFile(path, "a") as zipped:
        zipped.writestr("untrusted.txt", "extra")
    with pytest.raises(data.DataQualityError, match="members"):
        data.normalize_archive(path, "BTCUSDT", "2024-01")


def test_exact_known_shortened_metadata_only_is_allowlisted(tmp_path):
    source = row("2021-12-24T04:55:00Z", close_time=1640321994362)
    path = archive(tmp_path, [source], month="2021-12")
    with pytest.raises(data.DataQualityError, match="anomaly"):
        data.normalize_archive(path, "BTCUSDT", "2021-12")
    frame = data.normalize_archive(path, "BTCUSDT", "2021-12", allow_documented_exceptions=True)
    assert frame.index[0] == pd.Timestamp("2021-12-24T05:00:00Z")
    assert frame.attrs["original_close_time_anomalies"][0]["policy"] == "documented_shortened_source_metadata_warning"
    assert frame.iloc[0]["close"] == 101


def test_unknown_nearby_shortened_time_is_not_allowed(tmp_path):
    path = archive(tmp_path, [row("2021-12-24T04:55:00Z", close_time=1640321994361)], month="2021-12")
    with pytest.raises(data.DataQualityError, match="anomaly"):
        data.normalize_archive(path, "BTCUSDT", "2021-12", allow_documented_exceptions=True)


def repair_source(tmp_path):
    source = row("2021-12-24T04:55:00Z", close_time=1640322000475)
    path = archive(tmp_path, [source], symbol="SOLUSDT", month="2021-12")
    record = {"open_time": 1640321700000, "original_monthly_sha256": data.sha256_file(path),
              "original_raw_row": source, "corrected_close_time": 1640321999999,
              "changed_columns": ["close_time"], "all_other_fields_byte_identical": True}
    return path, record


def test_official_metadata_repair_retains_prices_and_raw_bytes(tmp_path):
    path, record = repair_source(tmp_path)
    before = path.read_bytes()
    frame = data.normalize_archive(path, "SOLUSDT", "2021-12", repair_record=record)
    assert path.read_bytes() == before
    assert frame.iloc[0]["close"] == 101
    assert frame.iloc[0]["quote_volume"] == 1010
    assert frame.attrs["original_close_time_anomalies"][0]["policy"] == "official_daily_close_time_repair_only"


@pytest.mark.parametrize("bad_field,value", [("original_monthly_sha256", "f" * 64), ("all_other_fields_byte_identical", False), ("changed_columns", ["close"]), ("corrected_close_time", 1640322000000)])
def test_repair_requires_exact_source_provenance(tmp_path, bad_field, value):
    path, record = repair_source(tmp_path)
    record[bad_field] = value
    with pytest.raises(data.DataQualityError):
        data.normalize_archive(path, "SOLUSDT", "2021-12", repair_record=record)


def basic_bars(index, symbols=("BTCUSDT",)):
    return pd.DataFrame([{"bar_end": stamp, "symbol": symbol, "volume": 0, "trades": 0, "close": 100, "quote_volume": 0} for stamp in index for symbol in symbols]).set_index("bar_end")


def test_unknown_calendar_gap_fails_and_is_not_filled():
    index = pd.date_range("2024-01-01T00:05:00Z", periods=3, freq="5min", name="bar_end")
    bars = basic_bars(index.delete(1))
    audit = data.audit_bars(bars, ["BTCUSDT"], index[0] - data.STEP, index[-1], allow_documented_halt=True)
    assert audit["status"] == "fail"
    assert audit["missing_count"] == 1
    assert len(bars) == 2
    assert audit["implicit_fill"] is False


def test_full_documented_halt_missing_grid_and_source_bounds():
    start = pd.Timestamp("2023-03-24T00:00:00Z")
    index = pd.date_range(start + data.STEP, start + pd.Timedelta(days=1), freq="5min", name="bar_end")
    observed = index.difference(pd.DatetimeIndex([pd.Timestamp(s) for s in data.ALLOWED_MISSING_ENDPOINTS]))
    bars = basic_bars(observed, data.SYMBOLS)
    audit = data.audit_bars(bars, data.SYMBOLS, start, start + pd.Timedelta(days=1), allow_documented_halt=True)
    assert audit["status"] == "pass_with_documented_exceptions"
    assert audit["missing_count"] == 128
    assert audit["allowed_missing_endpoints"] == data.ALLOWED_MISSING_ENDPOINTS
    assert audit["halt_bridges"] == data.HALT_BRIDGES
    bridge = audit["halt_bridges"][0]
    assert bridge["source"].startswith("https://www.binance.com/")
    assert pd.Timestamp(bridge["end"]) - pd.Timestamp(bridge["start"]) == pd.Timedelta(minutes=160)


def test_partial_asset_gap_inside_known_halt_fails():
    start = pd.Timestamp("2023-03-24T00:00:00Z")
    index = pd.date_range(start + data.STEP, start + pd.Timedelta(days=1), freq="5min", name="bar_end")
    bars = basic_bars(index, data.SYMBOLS)
    # One missing BTC row is not the verified all-venue source anomaly.
    bars = bars[~((bars.index == pd.Timestamp(data.ALLOWED_MISSING_ENDPOINTS[0])) & bars.symbol.eq("BTCUSDT"))]
    assert data.audit_bars(bars, data.SYMBOLS, start, start + pd.Timedelta(days=1), allow_documented_halt=True)["status"] == "fail"


def test_documented_halt_is_not_accepted_without_explicit_flag():
    start = pd.Timestamp("2023-03-24T00:00:00Z")
    index = pd.date_range(start + data.STEP, start + pd.Timedelta(days=1), freq="5min", name="bar_end").difference(pd.DatetimeIndex(data.ALLOWED_MISSING_ENDPOINTS))
    assert data.audit_bars(basic_bars(index, data.SYMBOLS), data.SYMBOLS, start, start + pd.Timedelta(days=1))["status"] == "fail"


def test_loader_rejects_failed_audit(tmp_path):
    directory = tmp_path / "data/processed"
    directory.mkdir(parents=True)
    (directory / "data_quality.json").write_text(json.dumps({"status": "fail"}))
    with pytest.raises(data.DataQualityError, match="gate"):
        data.load_panel(tmp_path)


def test_loader_checks_hash_and_does_not_fill(tmp_path):
    directory = tmp_path / "data/processed"
    directory.mkdir(parents=True)
    index = pd.date_range("2024-01-01T00:05:00Z", periods=3, freq="5min", name="bar_end")
    bars = basic_bars(index, data.SYMBOLS)
    path = directory / "bars.parquet"
    bars.to_parquet(path)
    audit = data.audit_bars(bars, data.SYMBOLS, index[0] - data.STEP, index[-1], allow_documented_halt=True)
    audit["normalized_parquet_sha256"] = data.sha256_file(path)
    (directory / "data_quality.json").write_text(json.dumps(audit))
    close, volume, _ = data.load_panel(tmp_path)
    assert close.shape == (3, 8) and volume.eq(0).all().all()
    assert close.attrs["bar_minutes"] == 5
    path.write_bytes(path.read_bytes() + b"modified")
    with pytest.raises(data.DataQualityError, match="SHA256"):
        data.load_panel(tmp_path)


def test_acquisition_rejects_hourly_interval_or_changed_universe(tmp_path):
    with pytest.raises(ValueError, match="eight-asset"):
        data.download_and_prepare(tmp_path, {"data": {"interval": "1h", "symbols": data.SYMBOLS}})


def test_hourly_reconciliation_separates_warmup_and_evaluation(tmp_path, monkeypatch):
    warm = pd.date_range("2021-12-23T02:05:00Z", periods=12, freq="5min", name="bar_end")
    active = pd.date_range("2022-01-01T00:05:00Z", periods=12, freq="5min", name="bar_end")
    index = warm.append(active)
    close = pd.DataFrame(100.0, index=index, columns=data.SYMBOLS)
    volume = pd.DataFrame(10.0, index=index, columns=data.SYMBOLS)
    hourly = basic_bars(pd.DatetimeIndex([warm[-1], active[-1]], name="bar_end"), data.SYMBOLS)
    hourly["quote_volume"] = 120.0
    close.loc[warm[-1], "BTCUSDT"] = 101
    monkeypatch.setattr(data.pd, "read_parquet", lambda *args, **kwargs: hourly)
    monkeypatch.setattr(data, "sha256_file", lambda *args: "a" * 64)
    receipt = data.reconcile_hourly(tmp_path, close, volume)
    assert receipt["price_exact_mismatch_count"] == 1
    assert receipt["warmup_price_exact_mismatch_count"] == 1
    assert receipt["evaluation_price_exact_mismatch_count"] == 0
    assert receipt["evaluation_volume_mismatch_count"] == 0
    assert receipt["evaluation_source_discrepancy_requires_review"] is False
    assert close.loc[warm[-1], "BTCUSDT"] == 101


def test_unknown_evaluation_hourly_discrepancy_marked_for_review(tmp_path, monkeypatch):
    index = pd.date_range("2022-01-01T00:05:00Z", periods=12, freq="5min", name="bar_end")
    close = pd.DataFrame(100.0, index=index, columns=data.SYMBOLS)
    volume = pd.DataFrame(10.0, index=index, columns=data.SYMBOLS)
    hourly = basic_bars(pd.DatetimeIndex([index[-1]], name="bar_end"), data.SYMBOLS)
    hourly["quote_volume"] = 121.0
    monkeypatch.setattr(data.pd, "read_parquet", lambda *args, **kwargs: hourly)
    monkeypatch.setattr(data, "sha256_file", lambda *args: "a" * 64)
    receipt = data.reconcile_hourly(tmp_path, close, volume)
    assert receipt["evaluation_volume_mismatch_count"] == 8
    assert receipt["evaluation_source_discrepancy_requires_review"] is True

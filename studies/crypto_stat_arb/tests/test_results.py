"""Independent integrity checks against real cached research outputs.

These checks skip before the research run exists; ordinary pure unit tests do
not require a download. Delivered cached outputs make all checks executable.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


@pytest.fixture(scope="module")
def outputs():
    root = Path(__file__).resolve().parents[1]
    required = [root / "outputs" / name for name in ["selection.json", "run_manifest.json", "final_metrics.csv",
                                                     "selected_returns.parquet", "selected_weights.parquet"]]
    if not all(p.exists() for p in required):
        pytest.skip("Run the cached research pipeline before real-output integrity checks")
    return root, json.loads(required[0].read_text()), json.loads(required[1].read_text()), pd.read_csv(required[2]), pd.read_parquet(required[3])


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def test_selection_receipt_precedes_test_and_matches_inputs(outputs):
    root, selection, manifest, _, _ = outputs
    assert pd.Timestamp(selection["selection_timestamp_utc"]) < pd.Timestamp(manifest["test_evaluation_started_at_utc"])
    assert selection["test_evaluated_before_selection"] is False
    assert digest(root / "outputs/selection.json") == manifest["selection_sha256"]
    assert digest(root / "outputs/experiments.csv") == selection["selection_evidence_sha256"]
    assert digest(root / "data/processed/bars.parquet") == manifest["data_parquet_sha256"]
    for name, fingerprint in manifest["source_code_sha256"].items():
        assert digest(root / "src/crypto_stat_arb" / name) == fingerprint


def test_all_configurations_retained_and_selected_from_validation(outputs):
    root, selection, _, _, _ = outputs
    experiments = pd.read_csv(root / "outputs/experiments.csv")
    assert len(experiments) == 36
    assert experiments.strategy_id.nunique() == 18
    assert set(experiments.split) == {"development", "validation"}
    for chosen in selection["selected"]:
        candidates = experiments.loc[(experiments.split == "validation") & (experiments.family == chosen["family"])]
        winner = candidates.sort_values(["sharpe", "mean_hourly_turnover", "strategy_id"], ascending=[False, True, True]).iloc[0]
        assert winner.strategy_id == chosen["strategy_id"]
    expected_combo = all(s["validation_net_sharpe"] > 0 and s["validation_annual_return"] > 0 for s in selection["selected"])
    assert selection["combination_eligible"] == expected_combo


def test_accounting_reconciles_for_every_return_observation(outputs):
    _, _, _, _, returns = outputs
    np.testing.assert_allclose(returns.net_return, returns.gross_return - returns.cost, rtol=0, atol=1e-15)
    np.testing.assert_allclose(returns.cost, returns.turnover * returns.cost_bps * 1e-4, rtol=0, atol=1e-15)
    for _, group in returns.groupby(["strategy_id", "split", "cost_bps", "execution_lag"]):
        group = group.sort_values("bar_end")
        equity = np.cumprod(1 + group.net_return.to_numpy())
        np.testing.assert_allclose(equity, group.equity, rtol=1e-12, atol=1e-14)
        peak = np.maximum.accumulate(np.r_[1., equity])[1:]
        np.testing.assert_allclose(equity / peak - 1, group.drawdown, rtol=1e-12, atol=1e-14)


def test_final_test_metrics_independently_recomputed(outputs):
    _, _, _, metrics, returns = outputs
    for _, row in metrics.loc[metrics.split == "test"].iterrows():
        group = returns.loc[(returns.strategy_id == row.strategy_id) & (returns.split == row.split) &
                            (returns.cost_bps == row.cost_bps) & (returns.execution_lag == row.execution_lag)].sort_values("bar_end")
        assert len(group) == 8760
        days = (pd.DatetimeIndex(group.bar_end) - pd.Timedelta(nanoseconds=1)).floor("D")
        daily = pd.Series(1 + group.net_return.to_numpy(), index=days).groupby(level=0).prod() - 1
        assert len(daily) == 365
        assert row.total_return == pytest.approx(group.equity.iloc[-1] - 1, abs=1e-12)
        assert row.cagr == pytest.approx(row.total_return, abs=1e-12)
        assert row.annual_return == pytest.approx(daily.mean() * 365, abs=1e-12)
        assert row.annual_volatility == pytest.approx(daily.std(ddof=1) * np.sqrt(365), abs=1e-12)
        assert row.sharpe == pytest.approx(daily.mean() / daily.std(ddof=1) * np.sqrt(365), abs=1e-12)
        assert row.max_drawdown == pytest.approx(-group.drawdown.min(), abs=1e-12)
        assert row.n_hours == row.n_observations == 8760


def test_halt_is_invested_observed_interval_not_filled_prices(outputs):
    root, _, _, metrics, returns = outputs
    from crypto_stat_arb.data import load_panel
    from crypto_stat_arb.backtest import generate_targets, observed_asset_returns
    close, _, audit = load_panel(root)
    missing = pd.Timestamp("2023-03-24T14:00:00Z")
    assert close.loc[missing].isna().all()
    assert audit["missing_count"] == 8
    assert audit["implicit_fill"] is False
    observed = observed_asset_returns(close)
    begin, end = pd.Timestamp("2023-03-24T11:00:00Z"), pd.Timestamp("2023-03-24T15:00:00Z")
    np.testing.assert_allclose(observed.loc[end], close.loc[end] / close.loc[begin] - 1)
    for hour in (12, 13, 14):
        assert pd.Timestamp(f"2023-03-24T{hour}:00:00Z") not in observed.index
    for _, row in metrics.loc[(metrics.split == "development") & (metrics.family != "combination")].iterrows():
        group = returns.loc[(returns.strategy_id == row.strategy_id) & (returns.split == "development") &
                            (returns.cost_bps == row.cost_bps) & (returns.execution_lag == row.execution_lag)]
        bridge = group.loc[group.bar_end.eq(end)].iloc[0]
        targets = generate_targets(close, row.family, int(row.lookback_h), int(row.rebalance_h))
        target_time = begin - pd.Timedelta(hours=int(row.execution_lag) - 1)
        expected = float((targets.loc[target_time] * (close.loc[end] / close.loc[begin] - 1)).sum())
        assert bridge.gross_return == pytest.approx(expected, abs=1e-12)
        assert bridge.interval_hours == 4
        assert row.n_hours == 17520
        assert row.n_observations == 17517


def test_selected_weights_are_neutral_and_cost_robustness_monotonic(outputs):
    root, _, _, metrics, _ = outputs
    weights = pd.read_parquet(root / "outputs/selected_weights.parquet")
    pivot = weights.pivot(index=["strategy_id", "split", "bar_end"], columns="symbol", values="weight")
    np.testing.assert_allclose(pivot.sum(axis=1), 0, atol=1e-14)
    assert (pivot.abs().sum(axis=1) <= 1 + 1e-14).all()
    for _, group in metrics.loc[(metrics.split == "test") & (metrics.execution_lag == 1)].groupby("strategy_id"):
        ordered = group.sort_values("cost_bps")
        assert list(ordered.cost_bps) == [0, 20, 40]
        assert np.diff(ordered.total_return).max() <= 1e-12


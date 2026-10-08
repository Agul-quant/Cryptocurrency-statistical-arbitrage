"""Runner accounting and retained-real-output checks for the isolated scan."""
from pathlib import Path
import importlib.util
import json
import sys

import numpy as np
import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('scale_scan_runner', HERE / 'reproduce.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

from crypto_stat_arb.backtest import simulate
from crypto_stat_arb.metrics import daily_returns
from crypto_stat_arb.runner import sha256_file


@pytest.mark.parametrize('cost', [0, 5, 10, 15, 20, 40])
def test_cost_transform_matches_core_simulator(cost):
    index = pd.date_range('2024-01-01', periods=97, freq='h', tz='UTC')
    prices = pd.DataFrame({'a': 100 * 1.001 ** np.arange(len(index)),
                           'b': 100 * .999 ** np.arange(len(index))}, index=index)
    targets = runner.generate_scaled_targets(prices, 'momentum', 1, 4)
    gross = simulate(prices, targets, index[24], index[-1], 0, 1)
    transformed = runner.apply_cost(gross, cost)
    direct = simulate(prices, targets, index[24], index[-1], cost, 1)
    pd.testing.assert_frame_equal(transformed.frame, direct.frame)
    pd.testing.assert_frame_equal(transformed.held_weights, direct.held_weights)


def test_bootstrap_is_deterministic_and_constant_return_exact():
    series = pd.Series(np.full(365, .001))
    a = runner.block_interval(series, 28, 17, 100)
    b = runner.block_interval(series, 28, 17, 100)
    assert a == b
    np.testing.assert_allclose([a['arithmetic_annual_mean'], a['ci95_low'], a['ci95_high']], .365)


def test_grid_same_for_both_signal_signs():
    grid = pd.DataFrame(runner.experiments())
    assert len(grid) == 156 and grid.experiment_id.nunique() == 156
    left = grid.loc[grid.family == 'momentum', ['lookback_h', 'rebalance_h']].reset_index(drop=True)
    right = grid.loc[grid.family == 'reversal', ['lookback_h', 'rebalance_h']].reset_index(drop=True)
    pd.testing.assert_frame_equal(left, right)


@pytest.fixture
def outputs():
    if not (HERE / 'scan_manifest.json').exists():
        pytest.skip('The cached real time-scale scan has not been executed yet.')
    return pd.read_csv(HERE / 'metrics.csv'), json.loads((HERE / 'scan_manifest.json').read_text())


def test_complete_real_grid_and_calendar_coverage(outputs):
    metrics, manifest = outputs
    assert len(metrics) == 936
    assert not metrics.duplicated(['experiment_id', 'split', 'cost_bps']).any()
    assert len(metrics.groupby(['experiment_id', 'split']).size()) == 468
    for split, hours, observations, days in [('development', 15960, 15957, 665),
                                            ('validation', 8784, 8784, 366), ('test', 8760, 8760, 365)]:
        group = metrics.loc[metrics.split == split]
        assert len(group) == 312
        assert group.n_hours.eq(hours).all()
        assert group.n_observations.eq(observations).all()
        assert group.n_days.eq(days).all()
    assert manifest['evaluation_splits']['development']['start'] == '2022-03-07'


def test_all_saved_input_output_and_source_hashes(outputs):
    _, manifest = outputs
    for name, expected in manifest['original_artifact_sha256'].items():
        assert sha256_file(ROOT / name) == expected
    for name, expected in manifest['output_sha256'].items():
        assert sha256_file(HERE / name) == expected
    for name, expected in manifest['extension_source_sha256'].items():
        assert sha256_file(HERE / name) == expected
    assert sha256_file(HERE / 'grid_spec.json') == manifest['grid_spec_sha256']
    assert manifest['original_artifacts_unchanged'] is True


def test_selection_is_2024_only_and_before_new_scan_test(outputs):
    _, manifest = outputs
    validation = pd.read_csv(HERE / 'validation_metrics.csv')
    receipt = json.loads((HERE / 'selection.json').read_text())
    assert validation.split.eq('validation').all()
    assert sha256_file(HERE / 'validation_metrics.csv') == receipt['selection_evidence_sha256']
    for name, cost in [('gross_selected', 0), ('net_selected', 20)]:
        reproduced = runner.select(validation, cost)
        for saved, actual in zip(receipt[name], reproduced):
            for key in ['experiment_id', 'family', 'lookback_h', 'rebalance_h', 'validation_cost_bps']:
                assert saved[key] == actual[key]
            np.testing.assert_allclose(saved['validation_sharpe'], actual['validation_sharpe'], atol=1e-12)
    assert pd.Timestamp(receipt['frozen_at_utc']) < pd.Timestamp(manifest['exploratory_test_started_at_utc'])
    assert 'previously inspected' in manifest['research_status']


def test_original_configuration_validation_and_test_parity(outputs):
    metrics, _ = outputs
    original_grid = pd.read_csv(ROOT / 'outputs/experiments.csv')
    original_selected = pd.read_csv(ROOT / 'outputs/final_metrics.csv')
    names = ['total_return', 'sharpe', 'max_drawdown', 'total_turnover', 'annual_volatility']
    for old in original_grid.loc[original_grid.split == 'validation'].itertuples():
        new = metrics.loc[(metrics.family == old.family) & (metrics.lookback_h == old.lookback_h)
                          & (metrics.rebalance_h == old.rebalance_h) & (metrics.split == 'validation')
                          & (metrics.cost_bps == 20)].iloc[0]
        for name in names:
            np.testing.assert_allclose(new[name], getattr(old, name), rtol=1e-11, atol=1e-11)
    for old in original_selected.loc[(original_selected.split == 'test')
                                    & (original_selected.execution_lag == 1)
                                    & original_selected.cost_bps.isin([0, 20])].itertuples():
        new = metrics.loc[(metrics.family == old.family) & (metrics.lookback_h == old.lookback_h)
                          & (metrics.rebalance_h == old.rebalance_h) & (metrics.split == 'test')
                          & (metrics.cost_bps == old.cost_bps)].iloc[0]
        for name in names:
            np.testing.assert_allclose(new[name], getattr(old, name), rtol=1e-11, atol=1e-11)


def test_gross_net_turnover_and_cost_monotonicity(outputs):
    metrics, _ = outputs
    zero = metrics.loc[metrics.cost_bps == 0].set_index(['experiment_id', 'split'])
    cost = metrics.loc[metrics.cost_bps == 20].set_index(['experiment_id', 'split']).reindex(zero.index)
    assert (cost.total_return < zero.total_return).all()
    np.testing.assert_allclose(cost.total_turnover, zero.total_turnover, atol=1e-12)
    np.testing.assert_allclose(cost.total_cost_sum, cost.total_turnover * .002, atol=1e-12)
    left = zero.reset_index().query("family == 'momentum'").set_index(['lookback_h', 'rebalance_h', 'split'])
    right = zero.reset_index().query("family == 'reversal'").set_index(['lookback_h', 'rebalance_h', 'split']).reindex(left.index)
    np.testing.assert_allclose(left.total_turnover, right.total_turnover, atol=1e-12)
    # Opposite hourly returns compound to a product no greater than one.
    assert (((1 + left.total_return) * (1 + right.total_return)) <= 1 + 1e-12).all()


def test_candidate_frames_independently_reconcile_metrics(outputs):
    metrics, _ = outputs
    returns = pd.read_parquet(HERE / 'candidate_returns.parquet')
    for (sid, split, cost), group in returns.groupby(['experiment_id', 'split', 'cost_bps']):
        frame = group.sort_values('bar_end').set_index('bar_end')
        assert not frame.index.has_duplicates
        net = frame.gross_return.to_numpy() - frame.turnover.to_numpy() * cost * 1e-4
        equity = np.cumprod(1 + net)
        np.testing.assert_allclose(frame.net_return, net, atol=1e-14)
        np.testing.assert_allclose(frame.equity, equity, rtol=1e-12)
        hourly = pd.Series(net, index=frame.index)
        hourly.attrs['interval_hours'] = {endpoint.isoformat(): int(duration)
                                        for endpoint, duration in frame.interval_hours.items() if duration != 1}
        daily = daily_returns(hourly)
        match = metrics.loc[(metrics.experiment_id == sid) & (metrics.split == split)
                            & (metrics.cost_bps == cost)].iloc[0]
        np.testing.assert_allclose(equity[-1] - 1, match.total_return, atol=1e-12)
        np.testing.assert_allclose(daily.mean() / daily.std(ddof=1) * np.sqrt(365), match.sharpe, atol=1e-11)
        drawdown = equity / np.maximum.accumulate(np.r_[1, equity])[1:] - 1
        np.testing.assert_allclose(-drawdown.min(), match.max_drawdown, atol=1e-12)


def test_yearly_windows_and_validation_test_reconciliation(outputs):
    metrics, _ = outputs
    annual = pd.read_csv(HERE / 'annual_metrics.csv')
    assert len(annual) == 1248
    assert annual.loc[annual.year == 2022, 'partial_year'].eq(True).all()
    assert annual.loc[annual.year != 2022, 'partial_year'].eq(False).all()
    for year, split in [(2024, 'validation'), (2025, 'test')]:
        a = annual.loc[annual.year == year].set_index(['experiment_id', 'cost_bps']).sort_index()
        b = metrics.loc[metrics.split == split].set_index(['experiment_id', 'cost_bps']).sort_index()
        np.testing.assert_allclose(a.total_return, b.total_return, rtol=1e-11, atol=1e-11)

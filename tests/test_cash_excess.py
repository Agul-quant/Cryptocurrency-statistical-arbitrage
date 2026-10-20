"""Cash-benchmark math, missingness, reproducibility and source integrity tests."""
from pathlib import Path
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
import numpy as np
import pandas as pd
import pytest

PACKET = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get('CRYPTO_CASH_SOURCE_ROOT', PACKET))
SPEC = importlib.util.spec_from_file_location('cash_excess_under_test', PACKET/'src/crypto_research/cash_excess.py')
cash = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cash)


def days(n, start='2024-01-01'):
    return pd.date_range(start, periods=n, freq='D', tz='UTC')


def test_nominal_rate_is_not_three_percent_effective():
    c = cash.cash_daily_rate(.03)
    assert c == .03/365
    effective = math.expm1(365*math.log1p(c))
    assert effective == pytest.approx(.030453263600509834)
    assert effective != pytest.approx(.03)


def test_leap_year_uses_731_actual_days():
    result = cash.performance(np.zeros(731), days(731))
    assert result['last_utc_day'] == '2025-12-31'
    assert result['cash_compounded_return'] == pytest.approx(.06192120248645947)
    assert result['cash_compounded_return'] > cash.performance(np.zeros(730), days(730))['cash_compounded_return']


def test_relative_compounding_not_arithmetic_excess_compounding():
    r = np.array([.05, -.02, .1])
    c = cash.cash_daily_rate()
    p = cash.performance(r, days(3))
    expected = np.prod(1+r)/(1+c)**3-1
    assert p['wealth_relative_excess_return'] == pytest.approx(expected)
    assert np.prod(1+(r-c)/(1+c))-1 == pytest.approx(expected)
    assert abs(np.prod(1+r-c)-1-expected) > 1e-7
    assert p['relative_annualized_growth'] == pytest.approx((1+expected)**(365/3)-1)


def test_sharpe_and_constant_volatility_identity():
    r = np.array([.015, -.006, .004, -.012, .01])
    p = cash.performance(r, days(len(r)))
    assert p['cash_excess_sharpe'] == pytest.approx(p['raw_sharpe']-.03/p['raw_annual_daily_volatility'])
    assert p['arithmetic_excess_annual_volatility'] == p['raw_annual_daily_volatility']
    assert p['relative_return_annual_volatility'] == pytest.approx(p['raw_annual_daily_volatility']/(1+cash.cash_daily_rate()))


def test_drawdown_includes_initial_nav_and_marks_return_at_day_end():
    result = cash.drawdown_from_daily_returns(np.array([-.1, 1/9, 0.]), days(3))
    assert result['max_drawdown'] == pytest.approx(.1)
    assert result['dd_peak_utc'] == '2024-01-01T00:00:00+00:00'
    assert result['dd_trough_utc'] == '2024-01-02T00:00:00+00:00'
    assert result['dd_recovery_utc'] == '2024-01-03T00:00:00+00:00'
    assert result['dd_underwater_days'] == 2
    assert result['time_underwater_fraction'] == pytest.approx(1/3)


def test_all_cash_and_benchmark_paths_have_undefined_sharpe():
    c = cash.cash_daily_rate()
    cash_path = cash.performance(np.zeros(100), days(100))
    assert np.isnan(cash_path['raw_sharpe']) and np.isnan(cash_path['cash_excess_sharpe'])
    assert cash_path['raw_daily_max_drawdown'] == 0
    assert cash_path['relative_daily_max_drawdown'] == pytest.approx(1-(1+c)**-100)
    assert cash_path['relative_daily_dd_peak_utc'] == '2024-01-01T00:00:00+00:00'
    assert cash_path['relative_daily_dd_trough_utc'] == '2024-04-10T00:00:00+00:00'
    assert cash_path['relative_daily_dd_recovery_censored']
    benchmark_path = cash.performance(np.full(100, c), days(100))
    assert benchmark_path['wealth_relative_excess_return'] == pytest.approx(0., abs=1e-15)
    assert benchmark_path['relative_daily_max_drawdown'] == 0
    assert np.isnan(benchmark_path['cash_excess_sharpe'])
    assert not benchmark_path['relative_daily_dd_recovery_censored']


def test_relative_drawdown_not_smaller_than_raw_daily_drawdown():
    rng = np.random.default_rng(33)
    for _ in range(10):
        r = rng.normal(.001, .025, 300)
        p = cash.performance(r, days(len(r)))
        assert p['relative_daily_max_drawdown'] >= p['raw_daily_max_drawdown']-1e-13


def test_calendar_rejects_gaps_duplicates_or_reordering():
    original = days(20)
    for invalid in (original.delete(3), original.insert(3, original[3]), original[::-1]):
        with pytest.raises(ValueError):
            cash.validate_calendar(invalid, start='2024-01-01', n=20)


def test_arithmetic_excess_regression_can_be_below_minus_one():
    x = np.linspace(-.1, .1, 20)
    y = np.linspace(-1.01, -.99, 20)+np.sin(np.arange(20))*.001
    fit = cash.fit_factor_model(y, x)
    assert np.isfinite(fit['params']).all()


def test_unknown_factors_excluded_not_zero_filled_or_calendar_compressed():
    rng = np.random.default_rng(6)
    x = rng.normal(0, .02, (100, 2))
    y = .0005+x@np.array([.2, -.3])+rng.normal(0, .01, 100)
    x[[5, 8, 9, 50], 0] = np.nan
    model = cash.fit_factor_model(y, x)
    assert model['n_calendar_days'] == 100 and model['n_fit_days'] == 96
    assert np.array_equal(model['mask'], np.isfinite(x).all(axis=1))
    compressed = cash.fit_factor_model(y[model['mask']], x[model['mask']])
    assert not np.allclose(model['covariance'], compressed['covariance'], atol=1e-12, rtol=1e-6)
    with pytest.raises(ValueError, match='unknown'):
        cash.fit_factor_model(y, x, mask=np.ones(100, bool))


def test_factor_point_and_full_covariance_transformation():
    rng = np.random.default_rng(48)
    x = rng.normal(0, .03, (300, 8))
    y = .0003+x@np.arange(8)/50+rng.normal(0, .02, 300)
    x[[5, 6, 40], 1] = np.nan
    c = cash.cash_daily_rate()
    for lag, correction in [(27, True), (7, True), (7, False)]:
        raw = cash.fit_factor_model(y, x, lag=lag, finite_correction=correction)
        actual = cash.fit_factor_model(y-c, x-c, lag=lag, finite_correction=correction)
        expected_p, expected_cov = cash.transformed_cash_parameters(raw['params'], raw['covariance'])
        np.testing.assert_allclose(actual['params'], expected_p, atol=2e-14, rtol=1e-11)
        np.testing.assert_allclose(actual['covariance'], expected_cov, atol=1e-15, rtol=1e-10)
        np.testing.assert_allclose(actual['params'][1:], raw['params'][1:], atol=2e-14, rtol=1e-11)
        np.testing.assert_allclose(actual['covariance'][1:, 1:], raw['covariance'][1:, 1:], atol=1e-15, rtol=1e-10)
        assert abs(actual['covariance'][0, 0]-raw['covariance'][0, 0]) > 1e-12


def test_bootstrap_matches_saved_generator_convention():
    actual = cash.circular_indices(731, replications=5)
    rng = np.random.Generator(np.random.PCG64(20261016))
    expected = []
    for _ in range(5):
        starts = rng.integers(0, 731, math.ceil(731/28))
        expected.append(np.concatenate([(s+np.arange(28))%731 for s in starts])[:731])
    np.testing.assert_array_equal(actual, expected)
    np.testing.assert_array_equal(actual, cash.circular_indices(731, replications=5))


def test_invalid_bootstrap_draws_not_dropped():
    indices = cash.circular_indices(30, replications=40)
    result = cash.bootstrap_intervals(np.zeros(30), indices)
    assert result['cash_excess_sharpe_bootstrap_invalid_draws'] == 40
    assert np.isnan(result['cash_excess_sharpe_bootstrap_ci95_low'])
    assert result['wealth_relative_excess_return_bootstrap_invalid_draws'] == 0
    assert result['bootstrap_any_invalid_draws'] == 40


@pytest.fixture(scope='module')
def production_results():
    config = json.loads((PACKET/'configs/cash_benchmark.json').read_text())
    before = {name: cash.sha256(SOURCE/name) for name in config['input_pins']}
    tables, blobs = cash.calculate(SOURCE, config)
    after = {name: cash.sha256(SOURCE/name) for name in config['input_pins']}
    assert before == after
    return tables, blobs


def test_complete_saved_inputs_reproduce_without_source_writes(production_results):
    tables, blobs = production_results
    assert [len(tables[name]) for name in tables] == [27, 27, 243, 54, 54, 81, 27]
    assert blobs['reconciliation.json']['source_writes'] is False
    assert blobs['reconciliation.json']['bootstrap_any_invalid_draws'] == 0
    for name, frame in tables.items():
        cash.compare_tables(frame, pd.read_csv(PACKET/'results/cash_excess'/name), name)


def test_pinned_source_checks_fail_closed_before_calculation(tmp_path):
    (tmp_path/'metadata').mkdir()
    (tmp_path/'results').mkdir()
    source = tmp_path/'results/daily_returns.csv'
    source.write_text('test')
    digest = cash.sha256(source)
    (tmp_path/'metadata/project_manifest.json').write_text(json.dumps({'files': {'results/daily_returns.csv': {'sha256': digest}}}))
    cfg = {'input_pins': {'results/daily_returns.csv': {'sha256': digest, 'bytes': 4}}}
    with pytest.raises(ValueError, match='seven'):
        cash.verify_inputs(tmp_path, cfg)
    cfg = json.loads((PACKET/'configs/cash_benchmark.json').read_text())
    for name in cfg['input_pins']:
        dest = tmp_path/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE/name, dest)
    (tmp_path/'metadata/project_manifest.json').write_text(json.dumps({'files': cfg['input_pins']}))
    cash.verify_inputs(tmp_path, cfg)
    with source.open('a') as handle:
        handle.write('corrupt')
    with pytest.raises(ValueError, match='checksum'):
        cash.verify_inputs(tmp_path, cfg)


def test_original_turnover_copied_exactly(production_results):
    saved = pd.read_csv(SOURCE/'results/strategy_metrics.csv').set_index(['comparison_id', 'period'])
    for _, row in production_results[0]['performance.csv'].iterrows():
        original = saved.loc[(row.strategy_id, row.period)]
        assert row.original_path_total_turnover == original.total_turnover
        assert row.original_path_annualized_full_l1_turnover == original.annualized_full_l1_turnover


def test_reproduction_cli_rejects_source_destination_before_any_source_write():
    before = cash.sha256(SOURCE/'README.md')
    run = subprocess.run([sys.executable, str(PACKET/'scripts/reproduce_cash_excess.py'),
                          '--source-root', str(SOURCE), '--output', str(SOURCE/'README.md')],
                         capture_output=True, text=True)
    assert run.returncode != 0 and 'inside local_outputs' in run.stderr
    assert cash.sha256(SOURCE/'README.md') == before


def test_reproduction_cli_rejects_symlink_descendant(tmp_path):
    # Use the public project's existing safety helper through the new CLI.
    import tempfile
    (SOURCE/'local_outputs').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=SOURCE/'local_outputs') as directory:
        target = Path(directory)
        (target/'performance.csv').symlink_to(SOURCE/'README.md')
        before = cash.sha256(SOURCE/'README.md')
        run = subprocess.run([sys.executable, str(PACKET/'scripts/reproduce_cash_excess.py'),
                              '--source-root', str(SOURCE), '--output', str(target)],
                             capture_output=True, text=True)
        assert run.returncode != 0 and 'Symlink' in run.stderr
        assert cash.sha256(SOURCE/'README.md') == before


def test_reproduction_receipt_allows_only_bounded_roundoff():
    spec = importlib.util.spec_from_file_location('cash_cli_test', PACKET/'scripts/reproduce_cash_excess.py')
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    original = {'status': 'passed', 'input_sha256': {'file': 'fixed'},
                'max_absolute_numeric_error': 1e-13,
                'checks': {'identity': {'numeric_cells': 3, 'maximum_absolute_error': 1e-16}}}
    changed = json.loads(json.dumps(original))
    changed['max_absolute_numeric_error'] = 2e-13
    changed['checks']['identity']['maximum_absolute_error'] = 2e-16
    cli.compare_reconciliation(changed, original)
    for path, value in [('hash', 'changed'), ('count', 4), ('error', 1e-5), ('error', float('nan'))]:
        invalid = json.loads(json.dumps(changed))
        if path == 'hash':
            invalid['input_sha256']['file'] = value
        elif path == 'count':
            invalid['checks']['identity']['numeric_cells'] = value
        else:
            invalid['checks']['identity']['maximum_absolute_error'] = value
        with pytest.raises(AssertionError):
            cli.compare_reconciliation(invalid, original)

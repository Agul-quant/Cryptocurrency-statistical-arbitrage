"""Exploratory time-scale scan; preserve the original project's locked results.

Run with the user's virtualenv from any working directory. Identical grids for
both signal signs are intentional. 2024 selects candidates; 2025 was already
inspected in the earlier research and is NOT a new independent holdout.
"""
from pathlib import Path
from datetime import datetime, timezone
import json

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from crypto_stat_arb.backtest import BacktestResult, observed_asset_returns, simulate
from crypto_stat_arb.data import load_panel
from crypto_stat_arb.metrics import summarize, daily_returns
from crypto_stat_arb.runner import sha256_file, write_json

from extended_backtest import generate_scaled_targets


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
GRID = {
    'families': ['momentum', 'reversal'],
    'lookbacks_hours': [1, 2, 4, 8, 12, 24, 48, 72, 168, 336, 672, 1440, 2160],
    'rebalances_hours': [1, 4, 12, 24, 72, 168],
    'schedule_anchor_utc': '2022-01-03T00:00:00+00:00',
    'primary_phase_hours': 0,
    'primary_cost_bps': 0,
    'secondary_cost_bps': 20,
    'execution_lag': 1,
}
SPLITS = {
    'development': {'start': '2022-03-07', 'end': '2024-01-01'},
    'validation': {'start': '2024-01-01', 'end': '2025-01-01'},
    'test': {'start': '2025-01-01', 'end': '2026-01-01'},
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def protected_hashes():
    names = ['configs/research.toml', 'outputs/selection.json', 'outputs/experiments.csv',
             'outputs/final_metrics.csv', 'outputs/selected_returns.parquet',
             'outputs/selected_weights.parquet', 'outputs/run_manifest.json',
             'reports/project_report.pdf', 'notebooks/crypto_stat_arb_research.ipynb',
             'notebooks/crypto_stat_arb_research.html', 'data/processed/bars.parquet',
             'src/crypto_stat_arb/backtest.py', 'src/crypto_stat_arb/metrics.py',
             'src/crypto_stat_arb/data.py', 'src/crypto_stat_arb/runner.py']
    return {name: sha256_file(ROOT / name) for name in names}


def apply_cost(gross_result, cost_bps):
    """Change only arithmetic cost accounting; holdings remain identical."""
    frame = gross_result.frame.copy()
    frame['cost'] = frame.turnover * float(cost_bps) * 1e-4
    frame['net_return'] = frame.gross_return - frame.cost
    if not np.isfinite(frame.net_return).all() or (frame.net_return <= -1).any():
        raise ValueError('Nonfinite or bankrupt return under scenario cost.')
    frame['equity'] = (1 + frame.net_return).cumprod()
    frame['drawdown'] = frame.equity / frame.equity.cummax().clip(lower=1) - 1
    return BacktestResult(frame=frame, held_weights=gross_result.held_weights)


def experiments():
    return [{'experiment_id': f'{family}_h{h:04d}_r{r:03d}', 'family': family,
             'lookback_h': h, 'rebalance_h': r}
            for family in GRID['families'] for h in GRID['lookbacks_hours']
            for r in GRID['rebalances_hours']]


def select(validation, cost_bps):
    chosen = []
    for family in GRID['families']:
        candidates = validation.loc[(validation.family == family) & (validation.cost_bps == cost_bps)]
        candidates = candidates.loc[np.isfinite(candidates.sharpe)]
        row = candidates.sort_values(['sharpe', 'mean_hourly_turnover', 'experiment_id'],
                                     ascending=[False, True, True], kind='stable').iloc[0]
        chosen.append({key: (int(row[key]) if key in ['lookback_h', 'rebalance_h'] else row[key])
                       for key in ['experiment_id', 'family', 'lookback_h', 'rebalance_h']}
                      | {'validation_cost_bps': cost_bps, 'validation_sharpe': float(row.sharpe),
                         'validation_total_return': float(row.total_return)})
    return chosen


def save_return_frame(result, experiment, split, cost, lag=1, phase=0):
    frame = result.frame.rename_axis('bar_end').reset_index()
    for key, value in experiment.items():
        frame[key] = value
    frame['split'], frame['cost_bps'], frame['execution_lag'], frame['phase_hours'] = split, cost, lag, phase
    return frame


def block_interval(series, block_days, seed, n_bootstrap=5000):
    """Circular blocks; nominal mean-return CI, NOT selection-adjusted inference."""
    values = series.to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    n = len(values)
    n_blocks = int(np.ceil(n / block_days))
    starts = rng.integers(0, n, size=(n_bootstrap, n_blocks))
    indices = (starts[:, :, None] + np.arange(block_days)) % n
    samples = values[indices.reshape(n_bootstrap, -1)[:, :n]]
    means = samples.mean(axis=1) * 365
    lo, hi = np.quantile(means, [.025, .975])
    return {'arithmetic_annual_mean': float(values.mean() * 365),
            'ci95_low': float(lo), 'ci95_high': float(hi),
            'block_days': block_days, 'bootstrap_samples': n_bootstrap, 'seed': seed}


def main():
    HERE.mkdir(parents=True, exist_ok=True)
    before = protected_hashes()
    started = utc_now()
    spec = {'frozen_at_utc': started, 'grid': GRID, 'evaluation_splits': SPLITS,
            'n_configurations': 156, 'research_status': 'Post-hoc exploratory extension; 2025 previously inspected.',
            'selection_rule': 'Highest 2024 daily Sharpe separately at 0 and 20 bps; ties lower turnover then experiment ID.',
            'original_artifact_sha256': before}
    spec_path = HERE / 'grid_spec.json'
    if spec_path.exists():
        existing = json.loads(spec_path.read_text())
        for key in ['grid', 'evaluation_splits', 'original_artifact_sha256']:
            if existing[key] != spec[key]:
                raise ValueError(f'Existing scan specification differs in {key}; preserve and investigate.')
        spec = existing
    else:
        write_json(spec_path, spec)
    prices, _, audit = load_panel(ROOT)
    benchmark = observed_asset_returns(prices)['BTCUSDT']
    grid = experiments()
    pretest_rows = []
    pretest_prices = prices.loc[prices.index <= pd.Timestamp('2025-01-01', tz='UTC')]
    pretest_benchmark = observed_asset_returns(pretest_prices)['BTCUSDT']
    for number, experiment in enumerate(grid, 1):
        targets = generate_scaled_targets(pretest_prices, experiment['family'], experiment['lookback_h'], experiment['rebalance_h'])
        for split_name in ['development', 'validation']:
            window = SPLITS[split_name]
            gross = simulate(pretest_prices, targets, window['start'], window['end'], 0, 1)
            for cost in [0, 20]:
                result = gross if cost == 0 else apply_cost(gross, cost)
                pretest_rows.append({**experiment, 'split': split_name, 'cost_bps': cost,
                                     'execution_lag': 1, 'phase_hours': 0, **summarize(result, pretest_benchmark)})
        if number % 12 == 0 or number == len(grid):
            print(f'Pretest scale grid {number}/{len(grid)}', flush=True)
    pretest = pd.DataFrame(pretest_rows)
    validation = pretest.loc[pretest.split == 'validation'].copy()
    validation.to_csv(HERE / 'validation_metrics.csv', index=False, float_format='%.17g')
    chosen = {'frozen_at_utc': utc_now(), 'selection_rule': spec['selection_rule'],
              'evidence_file': 'validation_metrics.csv',
              'selection_evidence_sha256': sha256_file(HERE / 'validation_metrics.csv'),
              'gross_selected': select(validation, 0), 'net_selected': select(validation, 20),
              'research_status': spec['research_status']}
    chosen_path = HERE / 'selection.json'
    if chosen_path.exists():
        old = json.loads(chosen_path.read_text())
        for key in ['gross_selected', 'net_selected', 'selection_evidence_sha256']:
            if old[key] != chosen[key]:
                raise ValueError(f'Frozen scan selection differs in {key}.')
        chosen = old
    else:
        write_json(chosen_path, chosen)
    print('Validation candidates fixed:', json.dumps(chosen), flush=True)
    test_started = utc_now()
    selected_ids = {s['experiment_id'] for s in chosen['gross_selected'] + chosen['net_selected']}
    test_rows, annual_rows, return_frames = [], [], []
    test_gross = {}
    for number, experiment in enumerate(grid, 1):
        sid = experiment['experiment_id']
        targets = generate_scaled_targets(prices, experiment['family'], experiment['lookback_h'], experiment['rebalance_h'])
        split = SPLITS['test']
        gross = simulate(prices, targets, split['start'], split['end'], 0, 1)
        for cost in [0, 20]:
            result = gross if cost == 0 else apply_cost(gross, cost)
            stats = summarize(result, benchmark)
            test_rows.append({**experiment, 'split': 'test', 'cost_bps': cost,
                              'execution_lag': 1, 'phase_hours': 0, **stats})
            annual_rows.append({**experiment, 'year': 2025, 'start': split['start'], 'end': split['end'],
                                'partial_year': False, 'cost_bps': cost, **stats})
            if sid in selected_ids:
                return_frames.append(save_return_frame(result, experiment, 'test', cost))
        if sid in selected_ids:
            test_gross[sid] = gross
            for split_name in ['development', 'validation']:
                window = SPLITS[split_name]
                selected_gross = simulate(prices, targets, window['start'], window['end'], 0, 1)
                for cost in [0, 20]:
                    result = selected_gross if cost == 0 else apply_cost(selected_gross, cost)
                    return_frames.append(save_return_frame(result, experiment, split_name, cost))
        for year in [2022, 2023, 2024]:
            begin = SPLITS['development']['start'] if year == 2022 else f'{year}-01-01'
            finish = f'{year+1}-01-01'
            yearly_gross = simulate(prices, targets, begin, finish, 0, 1)
            for cost in [0, 20]:
                result = yearly_gross if cost == 0 else apply_cost(yearly_gross, cost)
                annual_rows.append({**experiment, 'year': year, 'start': begin, 'end': finish,
                                    'partial_year': year == 2022, 'cost_bps': cost, **summarize(result, benchmark)})
        if number % 12 == 0 or number == len(grid):
            print(f'Exploratory test/yearly scale grid {number}/{len(grid)}', flush=True)
    metrics = pd.concat([pretest, pd.DataFrame(test_rows)], ignore_index=True)
    annual = pd.DataFrame(annual_rows)
    assert len(metrics) == 936 and len(annual) == 1248
    metrics.to_csv(HERE / 'metrics.csv', index=False, float_format='%.17g')
    annual.to_csv(HERE / 'annual_metrics.csv', index=False, float_format='%.17g')
    pd.concat(return_frames, ignore_index=True).to_parquet(HERE / 'candidate_returns.parquet', index=False)
    robustness_rows, inference_rows, breakeven_rows = [], [], []
    for number, selected in enumerate(chosen['gross_selected']):
        experiment = {key: selected[key] for key in ['experiment_id', 'family', 'lookback_h', 'rebalance_h']}
        sid, cadence = experiment['experiment_id'], experiment['rebalance_h']
        scenarios = [(0, 1, 'primary'), (0, 2, 'extra_hour_delay')]
        if cadence > 1:
            scenarios.append((cadence // 2, 1, 'half_cadence_phase_shift'))
        for phase, lag, label in scenarios:
            targets = generate_scaled_targets(prices, experiment['family'], experiment['lookback_h'], cadence, phase_hours=phase)
            for split_name in ['validation', 'test']:
                window = SPLITS[split_name]
                gross = simulate(prices, targets, window['start'], window['end'], 0, lag)
                for cost in [0, 20]:
                    result = gross if cost == 0 else apply_cost(gross, cost)
                    robustness_rows.append({**experiment, 'scenario': label, 'phase_hours': phase,
                                            'execution_lag': lag, 'split': split_name, 'cost_bps': cost,
                                            **summarize(result, benchmark)})
        gross = test_gross[sid]
        for cost in [0, 20]:
            result = gross if cost == 0 else apply_cost(gross, cost)
            for block in [7, 28]:
                inference_rows.append({**experiment, 'split': 'test', 'cost_bps': cost,
                                       **block_interval(daily_returns(result.frame.net_return), block, 20261006 + number * 100 + cost + block)})
        g, t = gross.frame.gross_return.to_numpy(), gross.frame.turnover.to_numpy()
        log_equity = lambda bps: float(np.log1p(g - t * bps * 1e-4).sum())
        threshold = None
        if log_equity(0) > 0:
            safe_upper = float(np.min((1 + g[t > 0]) / t[t > 0]) * 1e4 * .99)
            if log_equity(safe_upper) < 0:
                threshold = float(brentq(log_equity, 0, safe_upper, xtol=1e-10))
        breakeven_rows.append({**experiment, 'split': 'test', 'break_even_cost_bps': threshold,
                              'criterion': 'zero compounded total return'})
    pd.DataFrame(robustness_rows).to_csv(HERE / 'robustness.csv', index=False, float_format='%.17g')
    pd.DataFrame(inference_rows).to_csv(HERE / 'nominal_bootstrap_intervals.csv', index=False, float_format='%.17g')
    write_json(HERE / 'break_even.json', {'rows': breakeven_rows})
    counts = metrics.groupby(['split', 'family', 'cost_bps']).agg(
        n_configurations=('experiment_id', 'size'), positive_total_return=('total_return', lambda s: int((s > 0).sum())),
        positive_sharpe=('sharpe', lambda s: int((s > 0).sum()))).reset_index()
    counts.to_csv(HERE / 'profitability_counts.csv', index=False)
    after = protected_hashes()
    assert before == after
    outputs = ['metrics.csv', 'validation_metrics.csv', 'annual_metrics.csv', 'candidate_returns.parquet',
               'robustness.csv', 'nominal_bootstrap_intervals.csv', 'break_even.json', 'profitability_counts.csv', 'selection.json']
    manifest = {
        'started_at_utc': started, 'completed_at_utc': utc_now(), 'exploratory_test_started_at_utc': test_started,
        'grid': GRID, 'evaluation_splits': SPLITS, 'n_configurations': len(grid), 'metrics_rows': len(metrics),
        'annual_metrics_rows': len(annual), 'research_status': spec['research_status'],
        'original_artifacts_unchanged': True, 'original_artifact_sha256': before,
        'grid_spec_sha256': sha256_file(spec_path),
        'selection_evidence_sha256': chosen['selection_evidence_sha256'],
        'extension_source_sha256': {name: sha256_file(HERE / name) for name in ['reproduce.py', 'extended_backtest.py']},
        'output_sha256': {name: sha256_file(HERE / name) for name in outputs},
        'data_gate_status': audit.get('status', audit.get('gate_status')),
        'caveats': [
            'The broader time-scale grid was designed after inspecting the original 2025 results.',
            '2024 chooses candidates within this new scan; 2025 remains retrospective exploratory evidence, not an untouched holdout.',
            '156 related configurations create multiple-testing and selection optimism; bootstrap intervals are nominal and not selection-adjusted.',
            'The fixed eight-asset universe is a purposive survivor sample; shorts, fills and capacity remain idealized.',
            'One-way full-L1 target turnover includes entry and exit but excludes ordinary weight drift, funding and borrow costs.',
            'Rebalancing cadence is a schedule, not a minimum holding period; positions can persist across decisions.',
            'March7,2022 is a common aligned start after the longest lookback; 2022 annual rows are partial and labeled.',
            'The documented March2023 halt bridge retains positions without fabricated prices; intra-halt drawdown is unobserved.',
        ],
    }
    write_json(HERE / 'scan_manifest.json', manifest)
    print(counts.to_string(index=False), flush=True)
    print('SCAN COMPLETE', manifest['completed_at_utc'], flush=True)


if __name__ == '__main__':
    main()

"""Post-test cost sensitivity; original selections and artifacts stay unchanged.

Run with the original project's installed package and cached data. Costs apply
to full one-way L1 turnover, including entry and final liquidation. This is not
a new untouched test, nor a claim that any scenario cost is achievable live.
"""
from pathlib import Path
import json
import hashlib
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from crypto_stat_arb.backtest import generate_targets, simulate, observed_asset_returns
from crypto_stat_arb.data import load_panel
from crypto_stat_arb.metrics import summarize
from crypto_stat_arb.runner import load_config, sha256_file, write_json


def main():
    folder = Path(__file__).resolve().parent
    root = folder.parents[2]
    originals = [
        root / 'configs/research.toml', root / 'outputs/selection.json',
        root / 'outputs/final_metrics.csv', root / 'outputs/selected_returns.parquet',
        root / 'outputs/run_manifest.json', root / 'reports/project_report.pdf',
        root / 'notebooks/crypto_stat_arb_research.ipynb',
    ]
    before = {str(p.relative_to(root)): sha256_file(p) for p in originals}
    started = datetime.now(timezone.utc).isoformat()
    config = load_config(root / 'configs/research.toml')
    selection = json.loads((root / 'outputs/selection.json').read_text())
    prices, _, _ = load_panel(root)
    benchmark = observed_asset_returns(prices)['BTCUSDT']
    cached = pd.read_parquet(root / 'outputs/selected_returns.parquet')
    previous = pd.read_csv(root / 'outputs/final_metrics.csv')
    rows, breakeven, checks = [], [], []
    for selected in selection['selected']:
        sid = selected['strategy_id']
        targets = generate_targets(prices, selected['family'], selected['lookback_h'], selected['rebalance_h'])
        gross_test = None
        for split_name in ['validation', 'test']:
            split = config['splits'][split_name]
            saved = cached.loc[(cached.strategy_id == sid) & (cached.split == split_name)
                               & (cached.cost_bps == 0) & (cached.execution_lag == 1)].set_index('bar_end')
            assert not saved.index.has_duplicates
            assert len(saved) == (8784 if split_name == 'validation' else 8760)
            for cost in [0, 5, 10, 15, 20]:
                result = simulate(prices, targets, split['start'], split['end'], cost_bps=cost, execution_lag=1)
                frame = result.frame
                pd.testing.assert_index_equal(frame.index, saved.index)
                np.testing.assert_allclose(frame.gross_return, saved.gross_return, rtol=0, atol=1e-14)
                np.testing.assert_allclose(frame.turnover, saved.turnover, rtol=0, atol=1e-14)
                independent_net = saved.gross_return.to_numpy() - saved.turnover.to_numpy() * cost * 1e-4
                independent_equity = np.cumprod(1 + independent_net)
                np.testing.assert_allclose(frame.net_return, independent_net, rtol=0, atol=1e-14)
                np.testing.assert_allclose(frame.equity, independent_equity, rtol=1e-12, atol=1e-14)
                metrics = summarize(result, benchmark)
                if cost in [0, 20]:
                    old = previous.loc[(previous.strategy_id == sid) & (previous.split == split_name)
                                       & (previous.cost_bps == cost) & (previous.execution_lag == 1)].iloc[0]
                    for name in ['total_return', 'sharpe', 'max_drawdown', 'annual_volatility', 'total_turnover']:
                        np.testing.assert_allclose(metrics[name], old[name], rtol=1e-12, atol=1e-12)
                rows.append({'strategy_id': sid, 'family': selected['family'], 'lookback_h': selected['lookback_h'],
                             'rebalance_h': selected['rebalance_h'], 'split': split_name, 'cost_bps': cost,
                             'execution_lag': 1, **metrics})
                if split_name == 'test' and cost == 0:
                    gross_test = frame.copy()
                checks.append({'strategy_id': sid, 'split': split_name, 'cost_bps': cost,
                               'reconciled_saved_gross_and_turnover': True, 'independent_compounding_matches': True})
        assert gross_test is not None
        gross = gross_test.gross_return.to_numpy()
        turnover = gross_test.turnover.to_numpy()
        log_equity = lambda bps: float(np.log1p(gross - turnover * bps * 1e-4).sum())
        if log_equity(0) <= 0:
            threshold = None
            conclusion = 'Already negative at zero cost; no nonnegative break-even cost.'
        else:
            assert log_equity(20) < 0
            threshold = float(brentq(log_equity, 0, 20, xtol=1e-12))
            assert abs(log_equity(threshold)) < 1e-10
            conclusion = 'Compounded 2025 total return is zero at this hypothetical aggregate one-way cost.'
        breakeven.append({'strategy_id': sid, 'split': 'test', 'execution_lag': 1,
                         'break_even_cost_bps': threshold, 'conclusion': conclusion})
    frame = pd.DataFrame(rows)
    for _, group in frame.groupby(['strategy_id', 'split']):
        assert (group.sort_values('cost_bps').total_return.diff().dropna() < 0).all()
    frame.to_csv(folder / 'metrics.csv', index=False, float_format='%.17g')
    write_json(folder / 'break_even.json', {'criterion': 'zero compounded 2025 total return', 'rows': breakeven})
    after = {str(p.relative_to(root)): sha256_file(p) for p in originals}
    assert before == after
    receipt = {
        'started_at_utc': started, 'completed_at_utc': datetime.now(timezone.utc).isoformat(),
        'purpose': 'Post-test hypothetical cost sensitivity of the same frozen selections; no reselection.',
        'selection_timestamp_utc': selection['selection_timestamp_utc'],
        'input_artifact_sha256': before, 'original_artifacts_unchanged': True,
        'processed_data_sha256': sha256_file(root / 'data/processed/bars.parquet'),
        'reproduction_script_sha256': sha256_file(Path(__file__).resolve()),
        'output_sha256': {name: sha256_file(folder / name) for name in ['metrics.csv', 'break_even.json']},
        'checks': checks,
        'caveats': [
            'These sensitivities were requested after inspecting the original 2025 test results.',
            'Scenario cost is total one-way commission plus slippage per full L1 turnover, not a round-trip rate.',
            'Course target-weight turnover ignores ordinary weight drift.',
            'Shorts are theoretical; funding, borrow, capacity and margin costs remain excluded.',
            'No scenario cost is established as achievable with market or limit orders.',
            'The original report, notebook, selection, primary 20 bps analysis and delivered bundle are unchanged.',
        ],
    }
    write_json(folder / 'receipt.json', receipt)
    print(frame.loc[frame.split == 'test', ['family','cost_bps','total_return','sharpe','max_drawdown','annual_volatility']].to_string(index=False))
    print(json.dumps(breakeven, indent=2))


if __name__ == '__main__':
    main()

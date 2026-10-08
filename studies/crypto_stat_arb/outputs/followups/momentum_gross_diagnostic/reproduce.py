"""Read frozen outputs and decompose gross 2025 P&L without reselection."""
from pathlib import Path
from datetime import datetime, timezone
import json

import numpy as np
import pandas as pd

from crypto_stat_arb.backtest import observed_asset_returns
from crypto_stat_arb.data import load_panel
from crypto_stat_arb.runner import sha256_file, write_json


def main():
    folder = Path(__file__).resolve().parent
    root = folder.parents[2]
    inputs = ['outputs/selection.json', 'outputs/selected_returns.parquet',
              'outputs/selected_weights.parquet', 'data/processed/bars.parquet',
              'src/crypto_stat_arb/backtest.py']
    hashes = {name: sha256_file(root / name) for name in inputs}
    started = datetime.now(timezone.utc).isoformat()
    prices, _, _ = load_panel(root)
    returns = observed_asset_returns(prices)
    weights = pd.read_parquet(root / 'outputs/selected_weights.parquet')
    weights = weights.loc[(weights.strategy_id == 'momentum_h168_r24') & (weights.split == 'test')]
    weights = weights.pivot(index='bar_end', columns='symbol', values='weight').reindex(columns=prices.columns)
    saved = pd.read_parquet(root / 'outputs/selected_returns.parquet')
    saved = saved.loc[(saved.strategy_id == 'momentum_h168_r24') & (saved.split == 'test')
                      & (saved.cost_bps == 0) & (saved.execution_lag == 1)].set_index('bar_end')
    pd.testing.assert_index_equal(weights.index, saved.index)
    assert len(saved) == 8760
    np.testing.assert_allclose(weights.sum(axis=1), 0, atol=1e-14)
    np.testing.assert_allclose(weights.clip(lower=0).sum(axis=1), .5, atol=1e-14)
    np.testing.assert_allclose(weights.clip(upper=0).sum(axis=1), -.5, atol=1e-14)
    assets = returns.reindex(weights.index)
    long = (weights.clip(lower=0) * assets).sum(axis=1)
    short = (weights.clip(upper=0) * assets).sum(axis=1)
    np.testing.assert_allclose(long + short, saved.gross_return, atol=1e-14)
    prior_equity = saved.equity.shift(1, fill_value=1)
    long_pnl, short_pnl = float((prior_equity * long).sum()), float((prior_equity * short).sum())
    total = float(saved.equity.iloc[-1] - 1)
    np.testing.assert_allclose(long_pnl + short_pnl, total, atol=1e-13)
    contribution = pd.DataFrame([
        {'component': 'Long positions', 'initial_capital_pct': long_pnl * 100},
        {'component': 'Short positions', 'initial_capital_pct': short_pnl * 100},
        {'component': 'Portfolio total', 'initial_capital_pct': total * 100},
    ])
    endpoint_returns = prices.loc[pd.Timestamp('2026-01-01', tz='UTC')].div(
        prices.loc[pd.Timestamp('2025-01-01', tz='UTC')]) - 1
    asset_table = endpoint_returns.mul(100).rename('buy_hold_return_pct').rename_axis('symbol').reset_index()
    contribution.to_csv(folder / 'contributions.csv', index=False, float_format='%.17g')
    asset_table.to_csv(folder / 'asset_year_returns.csv', index=False, float_format='%.17g')
    assert all(sha256_file(root / name) == value for name, value in hashes.items())
    write_json(folder / 'receipt.json', {
        'started_at_utc': started, 'completed_at_utc': datetime.now(timezone.utc).isoformat(),
        'input_sha256': hashes, 'original_inputs_unchanged': True,
        'strategy_id': 'momentum_h168_r24', 'split': 'test', 'cost_bps': 0, 'execution_lag': 1,
        'long_gross_exposure': .5, 'short_gross_exposure': .5, 'net_exposure': 0,
        'hourly_rows': len(saved), 'all_eight_end_to_end_asset_returns_negative': bool(endpoint_returns.lt(0).all()),
        'long_plus_short_pnl_reconciles_gross_total': True,
        'caveats': ['Contributions use each interval beginning portfolio equity, so they add exactly to compounded total return.',
                    'These are P&L contributions as percentages of initial capital, not independent compounded long/short sleeve returns.',
                    'End-to-end price declines do not imply prices declined continuously throughout the year.',
                    'This is an accounting explanation, not proof of the economic cause of relative signal failure.',
                    'Dollar-neutral exposure does not imply a beta-neutral portfolio; course shorts remain theoretical.'],
    })
    print(contribution.to_string(index=False))
    print(asset_table.to_string(index=False))


if __name__ == '__main__':
    main()

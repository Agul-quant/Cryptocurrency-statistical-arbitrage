"""Build an executed, exploratory wider-timescale notebook from frozen scan outputs.

This command never downloads market data, re-runs the parameter sweep, chooses
new candidates, or modifies the original project artifacts.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import inspect
import json
import sys
import textwrap

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.ticker import PercentFormatter
import matplotlib.dates as mdates

HERE = Path(__file__).resolve().parent
HORIZONS = [1, 2, 4, 8, 12, 24, 48, 72, 168, 336, 672, 1440, 2160]
CADENCES = [1, 4, 12, 24, 72, 168]
FAMILIES = ['momentum', 'reversal']
COLORS = {'momentum': '#245C85', 'reversal': '#B66C24'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def label(row):
    return f"{row['family'].title()} {int(row['lookback_h'])}h/{int(row['rebalance_h'])}h"


def plot_heatmaps(metrics):
    data = metrics.loc[metrics['split'].eq('test') & metrics['cost_bps'].eq(0)]
    bound = float(data['sharpe'].abs().max())
    cmap = LinearSegmentedColormap.from_list('signal_strength', ['#B66C24', '#FAFAFA', '#245C85'])
    norm = TwoSlopeNorm(vmin=-bound, vcenter=0, vmax=bound)
    figures = {}
    for family in ['momentum', 'reversal']:
        rows = data.loc[data['family'].eq(family)]
        matrix = rows.pivot(index='lookback_h', columns='rebalance_h', values='sharpe').reindex(index=HORIZONS, columns=CADENCES)
        fig, ax = plt.subplots(figsize=(8.4, 6.4), layout='constrained')
        image = ax.imshow(matrix.to_numpy(), cmap=cmap, norm=norm, aspect='auto')
        ax.set_xticks(range(len(CADENCES)), [str(h) for h in CADENCES])
        ax.set_yticks(range(len(HORIZONS)), [str(h) for h in HORIZONS])
        ax.set(xlabel='Rebalance spacing (hours)', ylabel='Trailing price-return lookback (hours)',
               title=f'{family.title()}: 2025 zero-cost Sharpe (exploratory)')
        for i, horizon in enumerate(HORIZONS):
            for j, cadence in enumerate(CADENCES):
                value = matrix.loc[horizon, cadence]
                color = '#FFFFFF' if abs(value) > .55 * bound else '#1D2E3A'
                ax.text(j, i, f'{value:.2f}', ha='center', va='center', color=color, fontsize=9)
        bar = fig.colorbar(image, ax=ax, pad=.025)
        bar.set_label('Daily-return Sharpe (365 days, risk-free = 0)')
        figures[family] = fig
    return figures


def plot_stability(metrics):
    zero = metrics.loc[metrics['cost_bps'].eq(0)]
    pair = zero.pivot(index=['experiment_id', 'family'], columns='split', values='sharpe').reset_index()
    minimum = float(min(pair['validation'].min(), pair['test'].min()))
    maximum = float(max(pair['validation'].max(), pair['test'].max()))
    margin = max((maximum - minimum) * .08, .1)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), sharex=True, sharey=True, layout='constrained')
    for ax, family in zip(axes, ['momentum', 'reversal']):
        g = pair.loc[pair['family'].eq(family)]
        ax.scatter(g['validation'], g['test'], s=30, alpha=.75, color=COLORS[family], edgecolors='white', linewidth=.3)
        ax.axhline(0, color='#1D2E3A', lw=.8); ax.axvline(0, color='#1D2E3A', lw=.8)
        ax.plot([minimum-margin, maximum+margin], [minimum-margin, maximum+margin], ls='--', color='#77858F', lw=.8)
        ax.set(title=f'{family.title()} (78 configurations)', xlabel='2024 gross Sharpe',
               xlim=(minimum-margin,maximum+margin), ylim=(minimum-margin,maximum+margin))
        ax.grid(alpha=.4); ax.set_axisbelow(True)
    axes[0].set_ylabel('2025 gross Sharpe (exploratory)')
    fig.suptitle('Parameter-grid stability: 2024 versus already-seen 2025', fontsize=12)
    return fig


def plot_candidate_equity(candidate_returns, gross_selected):
    figures = {}
    maximum = 1.0
    for s in gross_selected:
        g = candidate_returns.loc[candidate_returns['experiment_id'].eq(s['experiment_id']) & candidate_returns['split'].eq('test')]
        for _, q in g.groupby('cost_bps'):
            maximum = max(maximum, float((1 + q.sort_values('bar_end')['net_return']).cumprod().max()))
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.1), sharey=True, layout='constrained')
    for ax, s in zip(axes, gross_selected):
        g = candidate_returns.loc[candidate_returns['experiment_id'].eq(s['experiment_id']) & candidate_returns['split'].eq('test')]
        for cost, q in g.groupby('cost_bps'):
            q = q.sort_values('bar_end')
            dates = pd.DatetimeIndex(q['bar_end']).insert(0, q['bar_end'].iloc[0] - pd.Timedelta(hours=1))
            equity = np.r_[1.0, (1 + q['net_return']).cumprod().to_numpy()]
            ax.plot(dates, equity, color=COLORS[s['family']], ls='-' if cost == 0 else '--',
                    lw=1.4, alpha=1 if cost == 0 else .65, label='Gross: 0 bps' if cost == 0 else 'Net: 20 bps')
        ax.axhline(1, color='#77858F', lw=.7)
        ax.set(title=label(s), xlabel='UTC date', ylim=(0,maximum*1.06))
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1,7]))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
        ax.legend(frameon=False, fontsize=9); ax.grid(alpha=.4); ax.set_axisbelow(True)
    axes[0].set_ylabel('Compounded equity (initial capital = 1)')
    fig.suptitle('2024 gross-selected candidates: exploratory 2025 cost comparison', fontsize=12)
    return fig


def plot_annual(annual_metrics, gross_selected):
    ids = [s['experiment_id'] for s in gross_selected]
    a = annual_metrics.loc[annual_metrics['experiment_id'].isin(ids) & annual_metrics['cost_bps'].eq(0)]
    years = sorted(a['year'].unique())
    fig, ax = plt.subplots(figsize=(9.5, 3.5), layout='constrained')
    width = .35
    xs = np.arange(len(years))
    for j, s in enumerate(gross_selected):
        g = a.loc[a['experiment_id'].eq(s['experiment_id'])].set_index('year').reindex(years)
        ax.bar(xs + (j-.5)*width, g['sharpe'], width, label=label(s), color=COLORS[s['family']])
    ax.axhline(0,color='#1D2E3A',lw=.8)
    ax.set_xticks(xs,[str(y) + ('*' if y == 2022 else '') for y in years])
    ax.set(title='Gross-selected candidates: yearly zero-cost Sharpe',
           ylabel='Daily-return Sharpe (365-day annualization)', xlabel='*2022 covers March 7-December 31 only')
    ax.grid(axis='y',alpha=.4);ax.set_axisbelow(True);ax.legend(frameon=False,fontsize=9)
    return fig


def build():
    import nbformat
    from nbclient import NotebookClient
    from nbconvert import HTMLExporter
    from jupyter_client.manager import KernelManager
    from jupyter_client.kernelspec import KernelSpec
    metrics = pd.read_csv(HERE/'metrics.csv')
    selection = json.loads((HERE/'selection.json').read_text())
    manifest = json.loads((HERE/'scan_manifest.json').read_text())
    selected = selection['gross_selected']
    md = nbformat.v4.new_markdown_cell
    code = nbformat.v4.new_code_cell
    cells = []
    summaries = []
    for s in selected:
        row = metrics.loc[metrics['experiment_id'].eq(s['experiment_id']) & metrics['split'].eq('test') & metrics['cost_bps'].eq(0)].iloc[0]
        net = metrics.loc[metrics['experiment_id'].eq(s['experiment_id']) & metrics['split'].eq('test') & metrics['cost_bps'].eq(20)].iloc[0]
        summaries.append(f"- {label(s)}: 2025 gross return {row['total_return']:.2%}, gross Sharpe {row['sharpe']:.2f}; 20 bps net return {net['total_return']:.2%}, net Sharpe {net['sharpe']:.2f}.")
    cells.append(md('# Wider time-scale study: momentum and reversal\n\n## tl;dr\n\n'
        'Zero-cost pattern discovery is primary; 20 bps economics are a secondary check. '
        'The wider scan tests **156 configurations**, not just the two original winning configurations.\n\n' + '\n'.join(summaries) +
        '\n\n**Exploratory, not a fresh held-out test:** 2025 was already inspected in the original project. '
        'Selecting candidates from 2024 only avoids selecting on these plotted 2025 results, '
        'but cannot make this follow-up an untouched out-of-sample experiment.'))
    cells.append(md('## Context & Methods\n\n'
        '- Both families use every lookback: **1, 2, 4, 8, 12, 24, 48, 72, 168, 336, 672, 1,440, 2,160 hours** (1 hour to 90 days).\n'
        '- Rebalance spacings: **1, 4, 12, 24, 72, 168 hours** (hourly to weekly), UTC-anchored to Monday January 3, 2022. Cadence is decision spacing, not a minimum holding period.\n'
        '- 13 lookbacks x 6 spacings x 2 families = 156 configurations. All share development beginning March 7, 2022, validation 2024, and exploratory evaluation 2025.\n'
        '- The same rank/demean/unit-gross dollar-neutral construction, 365-day daily metrics, BTC alpha/beta HAC(7), theoretical shorts, and documented 2023 halt protocol apply.\n'
        '- Longer horizons measure elapsed time, not number of surviving observations. Source missing prices are not filled.\n'
        '- The primary selection criterion is highest **2024 gross Sharpe**, separately for each family; a separately reported net-selected pair uses 2024 net Sharpe at 20 bps.\n'
        '- Zero execution cost is not achievable profit. Funding, borrow, margin, capacity, drift and guaranteed fills remain excluded.\n\n'
        'All original reports, notebook, selections, source definitions and deliverable ZIP are preserved. This companion writes only inside the isolated follow-up directory.'))
    cells.append(md('## Data\n\n### 1. Load the isolated evidence\n\n'
        'Local source files are `metrics.csv`, `annual_metrics.csv`, `selection.json`, `candidate_returns.parquet`, '
        '`robustness.csv`, and `scan_manifest.json`. No download or parameter search is executed by this notebook.'))
    cells.append(code("""from pathlib import Path
import json, hashlib, sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import PercentFormatter
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from IPython.display import display

choices = [Path.cwd(), Path.cwd()/'outputs/followups/time_scale_scan']
SCAN = next(p for p in choices if (p/'scan_manifest.json').exists())
PROJECT = SCAN.parents[2]
sys.path.insert(0,str(PROJECT/'src'))
sys.path.insert(0,str(SCAN))
get_ipython().run_line_magic('matplotlib','inline')
HORIZONS = [1,2,4,8,12,24,48,72,168,336,672,1440,2160]
CADENCES = [1,4,12,24,72,168]
COLORS = {'momentum':'#245C85','reversal':'#B66C24'}
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
metrics = pd.read_csv(SCAN/'metrics.csv')
annual = pd.read_csv(SCAN/'annual_metrics.csv')
selection = json.loads((SCAN/'selection.json').read_text())
manifest = json.loads((SCAN/'scan_manifest.json').read_text())
returns = pd.read_parquet(SCAN/'candidate_returns.parquet')
returns['bar_end'] = pd.to_datetime(returns['bar_end'],utc=True)
robustness = pd.read_csv(SCAN/'robustness.csv')
intervals = pd.read_csv(SCAN/'nominal_bootstrap_intervals.csv')
counts = pd.read_csv(SCAN/'profitability_counts.csv')
break_even = pd.DataFrame(json.loads((SCAN/'break_even.json').read_text())['rows'])
selection_digest = hashlib.sha256((SCAN/'selection.json').read_bytes()).hexdigest()
gross_selected = selection['gross_selected']
net_selected = selection['net_selected']
print('Python:',sys.executable)
print('Follow-up:',SCAN)
print('Status:',manifest['research_status'])
"""))
    cells.append(code(inspect.getsource(label)))
    cells.append(md('### 2. Check grid completeness and the saved selection evidence\n\n'
        'These are full-grid checks, not a selective preview. A decrease in return when trading costs are added '
        'is an accounting requirement, not evidence of statistical significance.'))
    cells.append(code("""assert manifest['original_artifacts_unchanged'] is True
for relative,digest in manifest['original_artifact_sha256'].items():
    assert hashlib.sha256((PROJECT/relative).read_bytes()).hexdigest() == digest,relative
for relative,digest in manifest['output_sha256'].items():
    assert hashlib.sha256((SCAN/relative).read_bytes()).hexdigest() == digest,relative
assert hashlib.sha256((SCAN/selection['evidence_file']).read_bytes()).hexdigest() == selection['selection_evidence_sha256']
assert pd.Timestamp(selection['frozen_at_utc']) < pd.Timestamp(manifest['exploratory_test_started_at_utc'])
assert len(metrics) == 936
assert len(annual) == 1248
keys = ['experiment_id','split','cost_bps']
assert not metrics.duplicated(keys).any()
assert set(metrics['family']) == {'momentum','reversal'}
assert set(metrics['lookback_h']) == set(HORIZONS)
assert set(metrics['rebalance_h']) == set(CADENCES)
assert set(metrics['cost_bps']) == {0,20}
assert set(metrics['split']) == {'development','validation','test'}
for family, group in metrics.groupby('family'):
    assert len(group[['lookback_h','rebalance_h']].drop_duplicates()) == 78
paired = metrics.pivot(index=['experiment_id','split'],columns='cost_bps',values='total_return')
assert (paired[20] <= paired[0] + 1e-12).all()
for criterion, picks, cost in [('gross',gross_selected,0),('net',net_selected,20)]:
    assert len(picks) == 2
    for s in picks:
        validation = metrics.loc[metrics['family'].eq(s['family']) & metrics['split'].eq('validation') & metrics['cost_bps'].eq(cost)]
        winner = validation.sort_values(['sharpe','mean_hourly_turnover','experiment_id'],ascending=[False,True,True]).iloc[0]
        assert winner['experiment_id'] == s['experiment_id']
print('Passed: 936 split/cost rows; 1,248 yearly rows; 78 configurations per family; frozen gross/net choices.')
display(pd.DataFrame(gross_selected)[['experiment_id','family','lookback_h','rebalance_h']])
"""))
    cells.append(md('### Reconcile the four frozen candidates from cached prices\n\n'
        'Rebuild extended-schedule weights, derive gross returns and L1 turnover from positions, '
        'recompute 2025 metrics at 0 and 20 bps, and compare every saved frame column. '
        'This is not a parameter sweep or a new selection.'))
    cells.append(code("""from crypto_stat_arb.data import load_panel
from crypto_stat_arb.backtest import simulate
from crypto_stat_arb.metrics import summarize
from extended_backtest import generate_scaled_targets
prices,_,audit=load_panel(PROJECT)
benchmark=prices['BTCUSDT'].pct_change(fill_method=None)
unique={s['experiment_id']:s for s in gross_selected+net_selected}
reconciliation=[]
for experiment_id,s in unique.items():
    targets=generate_scaled_targets(prices,s['family'],s['lookback_h'],s['rebalance_h'])
    for cost in [0,20]:
        result=simulate(prices,targets,'2025-01-01','2026-01-01',cost,1)
        f=result.frame
        asset_return=prices.pct_change(fill_method=None).reindex(f.index)
        manual_gross=(result.held_weights*asset_return).sum(axis=1)
        changes=result.held_weights.diff();changes.iloc[0]=result.held_weights.iloc[0]
        manual_turnover=changes.abs().sum(axis=1)
        manual_turnover.iloc[-1]+=result.held_weights.iloc[-1].abs().sum()
        np.testing.assert_allclose(f['net_return'],manual_gross-manual_turnover*cost*1e-4,atol=1e-13)
        saved=returns.loc[returns['experiment_id'].eq(experiment_id)&returns['split'].eq('test')&returns['cost_bps'].eq(cost)].set_index('bar_end').sort_index()
        assert f.index.equals(saved.index)
        for column in ['gross_return','net_return','turnover','cost','equity','drawdown']:
            np.testing.assert_allclose(f[column],saved[column],rtol=1e-10,atol=1e-13)
        computed=summarize(result,benchmark)
        row=metrics.loc[metrics['experiment_id'].eq(experiment_id)&metrics['split'].eq('test')&metrics['cost_bps'].eq(cost)].iloc[0]
        for column in ['total_return','cagr','annual_return','annual_volatility','sharpe','max_drawdown','alpha_annual','beta']:
            np.testing.assert_allclose(computed[column],row[column],rtol=1e-10,atol=1e-12)
        reconciliation.append({'candidate':label(s),'cost bps':cost,'hours verified':len(f),'reconciled':True})
assert hashlib.sha256((SCAN/'selection.json').read_bytes()).hexdigest()==selection_digest
display(pd.DataFrame(reconciliation))
"""))
    cells.append(md('## Results\n\n### 3. Map the entire 2025 zero-cost surface\n\n'
        'Every one of the 78 combinations appears for each family. Both heatmaps use the same symmetric '
        'color scale and exact cell annotations. The chart is **post-hoc exploratory**: a 2025 high-Sharpe '
        'cell is not a newly selected strategy or an unbiased performance estimate.'))
    cells.append(code(inspect.getsource(plot_heatmaps) + "\nheatmaps = plot_heatmaps(metrics)\nfor family, figure in heatmaps.items():\n    figure.savefig(SCAN/f'figures/{family}_zero_cost_sharpe.png',dpi=180,bbox_inches='tight')\n    display(figure)\n    plt.close(figure)"))
    cells.append(md('### 4. Compare validation with the already-seen evaluation year\n\n'
        'The dashed diagonal indicates unchanged gross Sharpe; zero lines distinguish sign persistence. '
        'Scatter points are configurations, not independent statistical samples.'))
    cells.append(code(inspect.getsource(plot_stability) + "\nstability_figure = plot_stability(metrics)\nstability_figure.savefig(SCAN/'figures/validation_test_stability.png',dpi=180,bbox_inches='tight')\ndisplay(stability_figure);plt.close(stability_figure)\nzero = metrics.loc[metrics['cost_bps'].eq(0)]\npersistence = zero.pivot(index=['experiment_id','family'],columns='split',values='sharpe').reset_index()\ndisplay(persistence.groupby('family').apply(lambda g:pd.Series({'positive_2024':int((g['validation']>0).sum()),'positive_2025':int((g['test']>0).sum()),'positive_both':int(((g['validation']>0)&(g['test']>0)).sum())}),include_groups=False))"))
    cells.append(md('### 5. Compare gross discovery with trading-cost economics\n\n'
        'Only the **2024 gross-selected** candidates are plotted. The separately net-selected candidates '
        'appear in a table below, without replacing the primary gross research question. Both families '
        'use the same equity axis, start capital, calendar year and cost convention.'))
    cells.append(code(inspect.getsource(plot_candidate_equity) + "\nequity_figure = plot_candidate_equity(returns,gross_selected)\nequity_figure.savefig(SCAN/'figures/gross_selected_cost_comparison.png',dpi=180,bbox_inches='tight')\ndisplay(equity_figure);plt.close(equity_figure)\nrows=[]\nfor criterion,picks in [('2024 gross selected',gross_selected),('2024 net selected',net_selected)]:\n    for s in picks:\n        for cost in [0,20]:\n            row=metrics.loc[metrics['experiment_id'].eq(s['experiment_id']) & metrics['split'].eq('test') & metrics['cost_bps'].eq(cost)].iloc[0]\n            rows.append({'selection':criterion,'candidate':label(s),'cost bps':cost,'2025 return':f\"{row['total_return']:.2%}\",'2025 Sharpe':round(row['sharpe'],3),'max drawdown':f\"{row['max_drawdown']:.2%}\"})\ndisplay(pd.DataFrame(rows))"))
    cells.append(md('### 6. Inspect year-by-year stability and phase/delay stresses\n\n'
        '2022 is a partial development year (March 7-December 31); it is labeled accordingly and is '
        'not directly equal in duration to the three subsequent full years. Yearly accounting resets '
        'cash and liquidates at each boundary. Phase/delay scenarios reuse the frozen candidates.'))
    cells.append(code(inspect.getsource(plot_annual) + """
annual_figure=plot_annual(annual,gross_selected)
annual_figure.savefig(SCAN/'figures/selected_yearly_sharpe.png',dpi=180,bbox_inches='tight')
display(annual_figure);plt.close(annual_figure)
stress=robustness.loc[robustness['split'].eq('test')].copy()
stress['candidate']=[label(r) for _,r in stress.iterrows()]
stress['2025 return']=stress['total_return'].map(lambda x:f'{x:.2%}')
display(stress[['candidate','scenario','phase_hours','execution_lag','cost_bps','2025 return','sharpe']].round(3))
"""))
    cells.append(md('### 7. Count broad yearly persistence without changing the selections\n\n'
        'The table below is **retrospectively selected after examining all four years**: it describes '
        'the full scan, not additional frozen winners. Each included configuration had positive '
        'gross compounded return in 2022 (partial), 2023, 2024 and 2025. Requiring positivity '
        'in all observed years does not correct survivor, multiple-testing or selection biases.'))
    cells.append(code("""annual_pair=annual.pivot(index=['experiment_id','family','lookback_h','rebalance_h','cost_bps'],columns='year',values='total_return').reset_index()
years=[2022,2023,2024,2025]
all_positive=annual_pair[years].gt(0).all(axis=1)
gross_persistent=annual_pair.loc[all_positive & annual_pair['cost_bps'].eq(0)].copy()
net_persistent=annual_pair.loc[all_positive & annual_pair['cost_bps'].eq(20)].copy()
print('Positive compounded returns in all four observed years:',len(gross_persistent),'at 0 bps;',len(net_persistent),'at 20 bps.')
view=gross_persistent[['family','lookback_h','rebalance_h']].copy()
for year in years:
    view[str(year)+('*' if year==2022 else '')]=gross_persistent[year].map(lambda x:f'{x:.2%}')
display(view.rename(columns={'lookback_h':'lookback hours','rebalance_h':'rebalance hours'}).reset_index(drop=True))
display(counts.loc[counts['split'].eq('test')][['family','cost_bps','n_configurations','positive_total_return','positive_sharpe']])
"""))
    cells.append(md('### 8. Nominal uncertainty and break-even execution costs\n\n'
        'Circular-block bootstrap intervals below use 5,000 resamples with 7- or 28-day blocks '
        'and saved seeds. They estimate the **annualized arithmetic mean of daily returns**, '
        'not CAGR or Sharpe. Intervals are nominal and **not adjusted for selection or 156 related '
        'comparisons**. The 0 bps selected-candidate intervals are plotted; the table includes '
        '20 bps. Break-even cost is the one-way cost where 2025 compounded total return is zero, '
        'not an estimated achievable fill cost.'))
    cells.append(code("""g=intervals.loc[intervals['cost_bps'].eq(0)].copy().sort_values(['family','block_days'])
fig,ax=plt.subplots(figsize=(9.5,3.4),layout='constrained')
y=np.arange(len(g))
means=g['arithmetic_annual_mean'].to_numpy()
errors=np.vstack([means-g['ci95_low'].to_numpy(),g['ci95_high'].to_numpy()-means])
ax.errorbar(means,y,xerr=errors,fmt='o',color='#245C85',ecolor='#77858F',capsize=4)
ax.set_yticks(y,[label(r)+f"; {int(r['block_days'])}-day blocks" for _,r in g.iterrows()])
ax.axvline(0,color='#1D2E3A',linewidth=.8)
ax.xaxis.set_major_formatter(PercentFormatter(1))
ax.set(title='Nominal 95% bootstrap intervals: zero-cost, not selection-adjusted',xlabel='2025 annual arithmetic mean daily-return estimate')
ax.grid(axis='x',alpha=.4);ax.set_axisbelow(True)
fig.savefig(SCAN/'figures/nominal_mean_return_intervals.png',dpi=180,bbox_inches='tight')
display(fig);plt.close(fig)
view=intervals[['family','cost_bps','block_days','arithmetic_annual_mean','ci95_low','ci95_high']].copy()
for c in ['arithmetic_annual_mean','ci95_low','ci95_high']:view[c]=view[c].map(lambda x:f'{x:.2%}')
display(view)
display(break_even[['family','lookback_h','rebalance_h','break_even_cost_bps','criterion']].round({'break_even_cost_bps':4}))
"""))

    cells.append(md('## Takeaways\n\n'
        'A wider grid can locate different gross patterns but increases multiple-comparison risk. '
        'Positive zero-cost results are not executable profit, and positive 2025 results in this '
        'already-seen period are hypotheses for a future truly unexamined period. Neither family '
        'is presumed successful. Theoretical shorts, funding/borrow omissions, the survivor universe, '
        'exchange-specific prices, USDT denomination and close-based execution remain material limits.\n\n'
        '### Sources and attribution\n\n'
        '- [Binance public market-data documentation](https://github.com/binance/binance-public-data); '
        'cached checksum-audited hourly spot archives inherited from the original project.\n'
        '- [Binance dataset terms](https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md): '
        'dataset-derived notebook analysis, charts and results are shared under CC BY-NC-SA 4.0 '
        'for non-commercial research, with Binance Vision attribution. No endorsement is implied.\n'
        '- The original class assignment defines the unconstrained framing and 20 bps cost sensitivity; '
        'this follow-up makes **zero cost primary** at the user\'s request.'))
    nb=nbformat.v4.new_notebook(cells=cells,metadata={'kernelspec':{'display_name':'Python 3 (myenv)','language':'python','name':'python3'},'language_info':{'name':'python'}})
    nbformat.validate(nb)
    manager=KernelManager(kernel_name='python3')
    manager._kernel_spec=KernelSpec(argv=[sys.executable,'-m','ipykernel_launcher','-f','{connection_file}'],display_name='Python 3 (myenv)',language='python')
    NotebookClient(nb,timeout=180,kernel_name='python3',km=manager,resources={'metadata':{'path':str(HERE)}},allow_errors=False).execute()
    path=HERE/'time_scale_research.ipynb'
    nbformat.write(nb,path)
    exporter=HTMLExporter();exporter.exclude_input_prompt=True;exporter.exclude_output_prompt=True
    html,_=exporter.from_notebook_node(nb)
    (HERE/'time_scale_research.html').write_text(html)
    print(path)


if __name__ == '__main__':
    build()

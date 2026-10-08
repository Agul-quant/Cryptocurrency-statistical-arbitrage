"""Evidence-backed, local research notebook and eight-page course PDF.

All charts use frozen runner outputs. Report generation never downloads data,
retunes a strategy, or mutates the selection manifest.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import numpy as np
import pandas as pd

COLORS = {'momentum': '#245C85', 'reversal': '#B66C24', 'combination': '#6D668E'}
BACKGROUND = '#FFFFFF'
INK = '#1D2E3A'
MUTED = '#52636F'
SOURCE_URL = 'https://github.com/binance/binance-public-data'
TERMS_URL = SOURCE_URL + '/blob/master/TERMS_AND_CONDITIONS.md'
HALT_URL = 'https://www.binance.com/en/blog/from-our-ceo/6789340645608890113'
RESUMPTION_URL = 'https://www.binance.com/en/support/announcement/detail/813a31506e9f478ea8c1058b425df87a'
BRIEF = '/Users/cosdis/Downloads/quant_course/ClassProject.docx'


def _json(path):
    with open(path) as f:
        return json.load(f)


def _metric(row, name, default=np.nan):
    aliases = {
        'total_return': ['total_return', 'net_total_return', 'cumulative_return'],
        'cagr': ['cagr', 'annualized_compounded_return'],
        'annual_return': ['annual_return', 'annualized_return', 'annual_arithmetic_return'],
        'volatility': ['volatility', 'annualized_volatility', 'annual_volatility'],
        'sharpe': ['sharpe', 'sharpe_ratio'],
        'max_drawdown': ['max_drawdown', 'maximum_drawdown'],
        'alpha': ['alpha', 'alpha_annual', 'alpha_annualized', 'annualized_alpha'],
        'beta': ['beta', 'btc_beta'],
        'turnover': ['turnover', 'mean_hourly_turnover', 'annual_turnover', 'annualized_turnover', 'mean_turnover', 'total_turnover'],
        'alpha_se': ['alpha_se', 'alpha_annualized_se', 'alpha_hac_se', 'alpha_se_annualized'],
    }
    for col in aliases.get(name, [name]):
        if col in row and pd.notna(row[col]):
            return float(row[col])
    return default


def _num(x, percent=False, digits=2):
    try:
        value = float(x)
        if not math.isfinite(value):
            return 'N/A'
        return f'{value:.{digits}%}' if percent else f'{value:.{digits}f}'
    except (ValueError, TypeError):
        return 'N/A'


def _family(row):
    family = str(row.get('family', row.get('strategy_id', ''))).lower()
    for k in COLORS:
        if family.startswith(k):
            return k
    if family.startswith('combo'):
        return 'combination'
    return family


def _label(identifier):
    match = re.fullmatch(r'(momentum|reversal)_h(\d+)_r(\d+)', str(identifier))
    if match:
        family, lookback, rebalance = match.groups()
        return f"{'Mom' if family == 'momentum' else 'Rev'} {int(lookback)}h/{int(rebalance)}h"
    if str(identifier).startswith(('combination', 'combo')):
        return '50/50 blend'
    return str(identifier).replace('_', ' ')


def _base(df, split='test'):
    out = df.loc[df['split'].eq(split)].copy()
    if 'cost_bps' in out:
        out = out.loc[out.cost_bps.eq(20)]
    if 'execution_lag' in out:
        out = out.loc[out.execution_lag.eq(out.execution_lag.min())]
    return out


def _load(root):
    paths = {name: root / 'outputs' / (name + '.csv') for name in
             ['experiments', 'final_metrics', 'annual_metrics', 'activity_diagnostics']}
    results = {name: pd.read_csv(path) for name, path in paths.items()}
    results['returns'] = pd.read_parquet(root / 'outputs' / 'selected_returns.parquet')
    results['returns']['bar_end'] = pd.to_datetime(results['returns']['bar_end'], utc=True)
    results['selection'] = _json(root / 'outputs' / 'selection.json')
    results['manifest'] = _json(root / 'outputs' / 'run_manifest.json')
    results['quality'] = _json(root / 'data' / 'processed' / 'data_quality.json')
    return results


def _style():
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
        'axes.titlesize': 12, 'axes.labelsize': 10, 'axes.titleweight': 'bold',
        'axes.spines.top': False, 'axes.spines.right': False,
        'axes.edgecolor': '#A8B2B9', 'text.color': INK, 'axes.labelcolor': INK,
        'xtick.color': MUTED, 'ytick.color': MUTED, 'figure.facecolor': BACKGROUND,
        'axes.facecolor': BACKGROUND, 'grid.color': '#E2E7EB', 'grid.linewidth': 0.6,
        'savefig.facecolor': BACKGROUND})


def _save(fig, path):
    fig.savefig(path, dpi=185, bbox_inches='tight')
    plt.close(fig)
    return str(path)


def make_figures(root: Path, results=None) -> dict:
    """Render selected tests, validation comparisons, and disclosed stress cases."""
    root = Path(root)
    d = _load(root) if results is None else results
    folder = root / 'reports' / 'figures'
    folder.mkdir(parents=True, exist_ok=True)
    _style()
    figures = {}
    e = d['experiments'].loc[d['experiments']['split'].eq('validation')].copy()
    if 'cost_bps' in e:
        e = e.loc[e.cost_bps.eq(20)]
    e['plot_sharpe'] = e.apply(lambda x: _metric(x, 'sharpe'), axis=1)
    e = e.sort_values('plot_sharpe', ascending=True)
    fig, ax = plt.subplots(figsize=(8.0, 5.3), layout='constrained')
    color = [COLORS.get(_family(row), '#6B7781') for _, row in e.iterrows()]
    ax.barh([_label(x) for x in e.strategy_id], e.plot_sharpe, color=color, height=.65)
    ax.axvline(0, color=INK, lw=.8)
    ax.set(xlabel='Daily-return Sharpe (365-day annualization)',
           title='2024 validation: all 18 predeclared configurations')
    ax.grid(axis='x'); ax.set_axisbelow(True)
    figures['validation'] = _save(fig, folder / 'validation_sharpe.png')

    ret = _base(d['returns'])
    fig, axes = plt.subplots(2, 1, figsize=(8.0, 5.0), sharex=True,
                             gridspec_kw={'height_ratios': [2, 1]}, layout='constrained')
    for identifier, g in ret.groupby('strategy_id', sort=True):
        g = g.sort_values('bar_end')
        family = _family({'strategy_id': identifier})
        color = COLORS.get(family, '#6B7781')
        # Include the initial unit capital explicitly, not just after first return.
        start = g.bar_end.iloc[0] - pd.Timedelta(hours=1)
        dates = pd.concat([pd.Series([start]), g.bar_end], ignore_index=True)
        eq = np.r_[1.0, (1 + g.net_return.to_numpy()).cumprod()]
        gross = np.r_[1.0, (1 + g.gross_return.to_numpy()).cumprod()]
        axes[0].plot(dates, eq, color=color, lw=1.5, label=_label(identifier) + ' net')
        axes[0].plot(dates, gross, color=color, lw=.9, ls='--', alpha=.7,
                     label=_label(identifier) + ' gross')
        draw = eq / np.maximum.accumulate(eq) - 1
        axes[1].plot(dates, draw, color=color, lw=1.2, label=_label(identifier))
    axes[0].axhline(1, color=INK, lw=.7)
    axes[0].set(ylabel='Compounded equity (start = 1)', title='2025 untouched test: gross versus 20 bps net')
    axes[1].set(ylabel='Net drawdown', xlabel='UTC date')
    axes[1].yaxis.set_major_formatter(PercentFormatter(1))
    axes[1].xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    for ax in axes: ax.grid(); ax.set_axisbelow(True)
    axes[0].legend(fontsize=8, ncol=2, loc='best', frameon=False)
    figures['equity'] = _save(fig, folder / 'test_equity_drawdown.png')

    m = d['final_metrics'].loc[d['final_metrics']['split'].eq('test')].copy()
    minlag = m.execution_lag.min()
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.5), layout='constrained')
    for identifier, g in m.groupby('strategy_id', sort=True):
        col = COLORS.get(_family({'strategy_id': identifier}), '#6B7781')
        cost = g.loc[g.execution_lag.eq(minlag)].sort_values('cost_bps')
        axes[0].plot(cost.cost_bps, cost.apply(lambda x: _metric(x, 'total_return'), axis=1),
                     marker='o', color=col, lw=1.4, label=_label(identifier))
        lag = g.loc[g.cost_bps.eq(20)].sort_values('execution_lag')
        axes[1].plot(lag.execution_lag, lag.apply(lambda x: _metric(x, 'sharpe'), axis=1),
                     marker='o', color=col, lw=1.4, label=_label(identifier))
    axes[0].set(title='Cost stress', xlabel='One-way execution cost (bps)', ylabel='2025 total compounded return')
    axes[0].set_xticks([0, 20, 40]); axes[0].yaxis.set_major_formatter(PercentFormatter(1))
    axes[1].set(title='Timing stress at 20 bps', xlabel='Signal-to-return lag (hours)', ylabel='2025 daily-return Sharpe')
    axes[1].set_xticks(sorted(m.execution_lag.unique()))
    for ax in axes: ax.axhline(0, color=INK, lw=.7); ax.grid(); ax.set_axisbelow(True)
    axes[0].legend(fontsize=7.5, frameon=False, loc='best')
    figures['robustness'] = _save(fig, folder / 'cost_timing_stress.png')

    a = d['activity_diagnostics'].copy()
    if 'split' in a: a = a.loc[a.split.eq('test')]
    if 'cost_bps' in a: a = a.loc[a.cost_bps.eq(20)]
    if 'execution_lag' in a: a = a.loc[a.execution_lag.eq(a.execution_lag.min())]
    # The table is preserved even if a revised runner uses a differently named proxy.
    regime_col = next((x for x in ['activity_regime', 'regime', 'activity'] if x in a), None)
    mean_col = next((x for x in ['mean_net_return', 'mean_hourly_net_return', 'net_mean_hourly_return', 'mean_return'] if x in a), None)
    if 'n_hours' in a: a = a.loc[a.n_hours > 0]
    if regime_col and mean_col and not a.empty:
        identifiers = list(a.strategy_id.unique())
        fig, ax = plt.subplots(figsize=(8, 3.6), layout='constrained')
        regimes = list(a[regime_col].unique())
        xs = np.arange(len(identifiers))
        width = .72 / max(len(regimes), 1)
        for j, regime in enumerate(regimes):
            vals = [float(a.loc[(a.strategy_id == i) & (a[regime_col] == regime), mean_col].iloc[0]) * 1e4
                    if ((a.strategy_id == i) & (a[regime_col] == regime)).any() else np.nan for i in identifiers]
            ax.bar(xs + (j - (len(regimes)-1)/2)*width, vals, width=width,
                   label=str(regime).replace('_', ' ').title(),
                   color=['#245C85', '#B5C8D6'][j % 2], edgecolor='#245C85',
                   hatch='' if j == 0 else '//', linewidth=.7)
        ax.set_xticks(xs, [_label(x) for x in identifiers])
        ax.set(ylabel='Mean hourly net return (bps)', title='2025 activity-conditioned return diagnostic')
        ax.axhline(0, color=INK, lw=.8); ax.legend(frameon=False); ax.grid(axis='y'); ax.set_axisbelow(True)
        figures['activity'] = _save(fig, folder / 'activity_diagnostic.png')
    return figures


def _summary(d):
    base = _base(d['final_metrics'])
    lines = []
    for _, row in base.iterrows():
        name = _label(row.strategy_id)
        lines.append(f"{name}: {_num(_metric(row, 'total_return'), True)} net test return, "
                     f"Sharpe {_num(_metric(row, 'sharpe'))}, "
                     f"maximum drawdown {_num(_metric(row, 'max_drawdown'), True)}.")
    profitable = base.apply(lambda r: _metric(r, 'total_return') > 0, axis=1).sum()
    if profitable == 0:
        verdict = 'None of the frozen selections was profitable after the prescribed 20 bps cost in the 2025 test.'
    elif profitable == len(base):
        verdict = 'All frozen selections had positive 2025 net returns at 20 bps; this is historical evidence, not a live-trading guarantee.'
    else:
        verdict = f'{profitable} of {len(base)} frozen selections had a positive 2025 net return at 20 bps.'
    return lines, verdict


def _quality_text(q):
    """Compact evidence view; actual issues stay in the machine-readable manifest."""
    out = []
    for key in ['status', 'rows', 'archive_count', 'missing_count', 'duplicate_count', 'invalid_ohlc_count', 'invalid_volume_count']:
        value = q.get(key)
        if value is not None and isinstance(value, (str, int, float, bool)):
            out.append((key.replace('_', ' ').title(), str(value)))
    return out


def _render_pdf(root, d, figures):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepTogether
    path = root / 'reports' / 'project_report.pdf'
    path.parent.mkdir(parents=True, exist_ok=True)
    W, H = A4
    usable = W - 90
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='TitleCustom', fontName='Helvetica-Bold', fontSize=25,
        leading=29, textColor=colors.HexColor(INK), spaceAfter=13))
    styles.add(ParagraphStyle(name='SectionCustom', fontName='Helvetica-Bold', fontSize=16,
        leading=20, textColor=colors.HexColor(INK), spaceAfter=13))
    styles.add(ParagraphStyle(name='SubCustom', fontName='Helvetica-Bold', fontSize=10.5,
        leading=14, textColor=colors.HexColor(INK), spaceBefore=9, spaceAfter=5))
    styles.add(ParagraphStyle(name='BodyCustom', fontName='Helvetica', fontSize=9.6,
        leading=14, textColor=colors.HexColor(INK), spaceAfter=8))
    styles.add(ParagraphStyle(name='SmallCustom', fontName='Helvetica', fontSize=8,
        leading=11, textColor=colors.HexColor(MUTED), spaceAfter=6))
    styles.add(ParagraphStyle(name='TableCustom', fontName='Helvetica', fontSize=8,
        leading=10.5, textColor=colors.HexColor(INK)))
    story = []
    def p(text, style='BodyCustom'):
        return Paragraph(text, styles[style])
    def add(text, style='BodyCustom'):
        story.append(p(text, style))
    def title(number, text):
        add(f'{number:02d} / {text}', 'SectionCustom')
    def table(rows, widths=None, fs=8):
        converted = [[p(escape(str(x)), 'TableCustom') for x in row] for row in rows]
        t = Table(converted, colWidths=widths, repeatRows=1, hAlign='LEFT')
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#E9EFF3')),
            ('LINEBELOW', (0,0), (-1,0), .7, colors.HexColor('#B7C6D0')),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING', (0,0), (-1,-1), 7), ('RIGHTPADDING', (0,0), (-1,-1), 7),
            ('TOPPADDING', (0,0), (-1,-1), 5), ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F6F8FA')]),
        ]))
        story.append(t); story.append(Spacer(1, 9))
    def img(key, height=None):
        if key not in figures: return
        from PIL import Image as PILImage
        with PILImage.open(figures[key]) as im: w, h = im.size
        scaled_h = usable * h / w
        if height and scaled_h > height:
            width = usable * height / scaled_h; scaled_h = height
        else: width = usable
        story.append(Image(figures[key], width=width, height=scaled_h, hAlign='LEFT'))
        story.append(Spacer(1, 7))
    def page():
        while story and isinstance(story[-1], Spacer):
            story.pop()
        story.append(PageBreak())

    lines, verdict = _summary(d)
    base = _base(d['final_metrics'])
    # 1: compact research summary, not an oversized decorative cover.
    add('CRYPTOCURRENCY\nSTATISTICAL ARBITRAGE'.replace('\n', '<br/>'), 'TitleCustom')
    add('Momentum and reversal | Hourly, dollar-neutral research | 2022-2025', 'SubCustom')
    add('Course project report', 'SmallCustom')
    add('Research question', 'SubCustom')
    add('Can cross-sectional price patterns in eight cryptocurrencies predict subsequent returns strongly enough to survive 20 basis points of one-way trading costs? The project compares two predeclared strategy families and tests a volume-activity diagnostic.')
    add('Principal finding', 'SubCustom')
    add(escape(verdict))
    for line in lines: add(escape(line))
    table([['Evidence', 'Design'],
           ['Universe', 'BTC, ETH, LTC, ADA, LINK, DOGE, DOT, SOL; Binance USDT spot'],
           ['Development / validation / test', '2022-2023 / 2024 / 2025; December 2021 warm-up'],
           ['Experiments', '18 fixed combinations: 9 momentum and 9 reversal'],
           ['Position model', 'Theoretical 50% long / 50% short; unit gross exposure'],
           ['Execution', 'Close-based idealization; 0, 20, 40 bps and one-extra-hour delay'],
          ], [usable*.37, usable*.63])
    add('Interpretation boundary', 'SubCustom')
    add('This is an unconstrained educational backtest, not an implementable spot shorting system. Borrowing, funding, leverage constraints, execution capacity, and weight drift are excluded. The fixed survivor universe and multiple comparisons limit generalization. One documented 2023 exchange halt is handled as an observed four-hour holding interval, without fabricated prices.')
    add('Source of the assignment: ClassProject.docx, The Wall Street Quants course. Data attribution: Binance public market data. No claim of profitability was assumed in constructing this report.', 'SmallCustom')
    page()

    # 2: point-in-time partitions and actual data status.
    title(2, 'Data and experimental protocol')
    add('Input and provenance', 'SubCustom')
    add('Hourly spot OHLCV comes from Binance public monthly archives. Original archives and SHA-256 checksums are cached; normalized Parquet inputs retain completed UTC-hour endpoints. The loader accounts for the 2025 spot timestamp-unit change. All eight instruments use the same USDT quote currency.')
    table([['Split', 'Period', 'Permitted use'],
          ['Warm-up', 'December 2021', 'Trailing indicators only'],
          ['Development', '2022-2023', 'Implementation and diagnostic design'],
          ['Validation', '2024', 'Select one configuration per family'],
          ['Test', '2025', 'Frozen-selection evaluation; no retuning']],
          [usable*.20, usable*.25, usable*.55])
    add('Predeclared grid', 'SubCustom')
    table([['Family', 'Signal lookback', 'Rebalance spacing'],
          ['Momentum', '24, 72, 168 hours', '1, 4, 24 hours'],
          ['Reversal', '1, 4, 12 hours', '1, 4, 24 hours']], [usable*.25, usable*.35, usable*.40])
    add('Quality gate', 'SubCustom')
    add('Checks cover duplicates, missing hours, OHLC consistency, volumes, checksums, and cross-instrument alignment. Status is pass with documented exceptions, not a clean complete-hourly pass. All missing prices remain missing; the full audit is saved with the dataset.')
    quality_rows = _quality_text(d['quality'])
    if quality_rows: table([['Observed quality field', 'Recorded value']] + quality_rows, [usable*.44, usable*.56])
    else: add('Detailed quality results are recorded in data/processed/data_quality.json.', 'SmallCustom')
    add('Predeclared exception: March 24, 2023 spot halt', 'SubCustom')
    add(f'Binance reports a halt at 11:27 UTC and resumption at 14:00. The missing 14:00 endpoint affects all eight assets and is not repaired by official daily archives. We bridge observed closes 11:00 to 15:00 as one four-hour interval, hold the existing position, and book the complete price-ratio return once at 15:00. No executions, costs, valuations, price filling, early cash-out, or dropped day occur at 12:00-14:00. <link href="{HALT_URL}" color="#245C85">Official halt account</link>.', 'SmallCustom')
    add('Sixteen close-time metadata anomalies are documented: one SOL warm-up record is corrected from a checksum-verified daily archive without changing OHLCV; fifteen shortened close timestamps are allowlisted warnings. No observed prices are changed. Unknown exceptions still stop research.', 'SmallCustom')
    add('Selection rule', 'SubCustom')
    add('Maximize 2024 net Sharpe per family; tie-break by lower turnover, then identifier. A 50/50 position blend requires both families to pass positive net validation. Blend costs come from combined positions.')
    page()

    # 3: backtest/accounting details with equations in ASCII for portability.
    title(3, 'Signals, portfolio, and accounting')
    add('Signal construction', 'SubCustom')
    add('For coin i at completed hour t, trailing return is close(i,t) / close(i,t-L) - 1. Momentum uses this return; reversal uses its negative. Cross-sectional average ranks are demeaned, then normalized by the sum of absolute demeaned ranks. Ties receive average ranks; an all-tied cross-section is flat.')
    table([['Operation', 'Definition'],
           ['Cross-sectional score', 'z(i,t) = rank(signal(i,t)) - mean(rank(signal(t)))'],
           ['Target weights', 'w(i,t) = z(i,t) / sum_i abs(z(i,t))'],
           ['Gross next-hour return', 'r_gross(t+1) = sum_i w(i,t) * r(i,t+1)'],
           ['Traded notional', 'turnover(t) = sum_i abs(w_new(i,t) - w_old(i,t))'],
           ['Cost and net return', 'cost(t) = turnover(t) * bps / 10,000; r_net = r_gross - cost'],
           ['Compounded equity', 'equity(t) = product over s<=t of [1 + r_net(s)]'],
           ['Drawdown', 'equity(t) / max(1, earlier equity values) - 1']],
           [usable*.30, usable*.70])
    add('Time alignment and costs', 'SubCustom')
    add('Targets are set only on UTC-aligned rebalance hours and held between decisions, except no execution is allowed during the documented halt. Completed-bar signals earn subsequent, not contemporaneous, returns. Each split starts from cash, charges initial entry, and includes final liquidation. Halt lookbacks require exact elapsed-hour endpoints: unavailable signals defer the decision while retaining exposure. A long-to-short change pays the full absolute weight change. The extra-delay test moves signals back one additional hour.')
    add('This close-based execution assumption is deliberately idealized: the observed close is not a guaranteed executable price. Twenty bps is the course-prescribed all-in market-order cost, not an empirical estimate from an order book. Seven-bps limit-order commissions do not justify assuming fills without spread, adverse selection, or opportunity costs.')
    add('Performance definitions', 'SubCustom')
    add('Observed-interval net returns compound into UTC daily returns with exactly 24 elapsed hours of coverage; the 2023 bridge preserves the reopening return. Arithmetic annual return = daily mean x 365; annual volatility = daily sample standard deviation x sqrt(365); Sharpe uses a zero risk-free rate. CAGR uses compounded equity and elapsed years; maximum drawdown uses observed-endpoint equity including initial capital. It is hourly outside the halt; intrahalt losses cannot be reconstructed.')
    add('Daily OLS against BTC/USDT returns includes an intercept. Reported alpha is annualized by 365 and beta is dimensionless. Alpha uncertainty uses HAC standard errors with seven daily lags; this handles a specified short autocorrelation window but does not correct configuration-search bias. USDT is the numeraire, not guaranteed identical to USD.')
    add('Course-style approximation: target changes determine turnover. We do not track weight drift, cash financing, margin, mark-to-market collateral, or capacity.', 'SmallCustom')
    page()

    # 4: all tested configurations preserved.
    title(4, 'Validation and frozen selections')
    img('validation', height=365)
    add('The comparison uses the same 2024 period and prescribed execution costs for all 18 configurations. Color distinguishes the two families; the zero line separates positive and negative Sharpe. Labels show family and lookback/rebalance hours. No test-period metric is used to choose winners.', 'SmallCustom')
    val = _base(d['final_metrics'], 'validation')
    rows = [['Frozen strategy', 'Net return', 'Sharpe', 'Max drawdown']]
    for _, r in val.iterrows():
        rows.append([_label(r.strategy_id), _num(_metric(r,'total_return'),True),
                     _num(_metric(r,'sharpe')), _num(_metric(r,'max_drawdown'),True)])
    if len(rows)>1: table(rows, [usable*.43, usable*.19, usable*.15, usable*.23])
    add('Why validation is not proof', 'SubCustom')
    add('Selecting the best of nine candidates within a family can capitalize on noise. All configurations are retained in the experiment table, and evaluation advances chronologically into 2025. The held-out year reduces selection leakage, but one market regime and a survivor-selected sample cannot establish a persistent trading edge.')
    add('Selection provenance is saved separately in outputs/selection.json. The runner writes that frozen decision before creating test metrics. Execution-cost and delay sensitivity cases reuse those decisions; they do not trigger reselection.', 'SmallCustom')
    page()

    # 5: core result and exact required performance metrics.
    title(5, 'Untouched 2025 test results')
    img('equity', height=310)
    rows = [['Metric'] + [_label(r.strategy_id) for _, r in base.iterrows()]]
    for name, display, pct in [('total_return','Total return',True), ('cagr','CAGR',True),
                              ('annual_return','Arithmetic annual return',True), ('volatility','Annual volatility',True),
                              ('sharpe','Sharpe (zero risk-free)',False), ('max_drawdown','Max hourly drawdown',True),
                              ('alpha','Annual BTC-relative alpha',True), ('beta','BTC beta',False)]:
        rows.append([display] + [_num(_metric(r,name),pct) for _,r in base.iterrows()])
    rows.append(['Alpha 95% HAC interval'] + [f"{_num(r.get('alpha_ci_low'), True)} to {_num(r.get('alpha_ci_high'), True)}" for _, r in base.iterrows()])
    widths = [usable*.39] + [usable*.61 / max(len(base),1)] * len(base)
    table(rows, widths)
    add(escape(verdict), 'SmallCustom')
    add('Solid curves are 20 bps net equity; dashed curves are gross before transaction costs. Net drawdowns below use the same start-at-one capital base. The table is net at the minimum declared lag; alpha and its 95% HAC interval are expressed in annual return units; positive maximum drawdown is loss magnitude. N/A means unavailable, never zero.', 'SmallCustom')
    page()

    # 6: robustness can challenge result, not rescue parameters.
    title(6, 'Execution sensitivity and robustness')
    img('robustness', height=215)
    rows=[['Strategy', 'Cost bps', 'Lag h', 'Net return', 'Sharpe']]
    tm=d['final_metrics'].loc[d['final_metrics']['split'].eq('test')].sort_values(['strategy_id','execution_lag','cost_bps'])
    for _, r in tm.iterrows():
        rows.append([_label(r.strategy_id), str(int(r.cost_bps)), str(int(r.execution_lag)),
                     _num(_metric(r,'total_return'),True), _num(_metric(r,'sharpe'))])
    table(rows,[usable*.39,usable*.14,usable*.12,usable*.19,usable*.16])
    bridge=[['20 bps baseline', 'Gross return', 'Net return', 'Mean hourly turnover']]
    for _, r in base.iterrows():
        bridge.append([_label(r.strategy_id), _num(r.get('gross_total_return'),True),
                       _num(_metric(r,'total_return'),True), _num(r.get('mean_hourly_turnover'),False,3)])
    table(bridge,[usable*.40,usable*.19,usable*.19,usable*.22])
    add('Turnover is traded notional per unit of target capital, not half-turnover. Mean hourly turnover includes entry and liquidation; gross-net equity differences are compounded cost drag, not summed hourly cost rates.', 'SmallCustom')
    add('Reading the stress cases', 'SubCustom')
    add('Zero cost measures gross signal behavior, not achievable profit. Higher costs test implementation sensitivity; an extra hour tests close-timing dependence. These are stresses, not confidence intervals; no 2025 reselection occurs.')
    add('Even a positive scenario is insufficient for deployment. A subsequent implementation study would need borrowable instruments, funding and financing, measured spreads, order-book capacity, realistic execution, and an additional untouched period.', 'SmallCustom')
    page()

    # 7: predeclared activity study, not causal claim.
    title(7, 'Volume activity and time stability')
    add('Activity as a descriptive proxy', 'SubCustom')
    add('For each coin, current volume is divided by its preceding 168-hour mean, excluding the current bar from that denominator. The marketwide activity score averages these relative volumes. The median estimated only on development data divides high and low activity. Missing preceding-volume coverage is an explicit unknown regime, not fabricated low activity. The activity label follows the strategy rebalance decision and execution lag, excluding later activity information; its use is descriptive, not an additional trading gate.')
    img('activity', height=175)
    a=d['activity_diagnostics'].copy()
    if 'split' in a: a=a.loc[a.split.eq('test')]
    if 'cost_bps' in a: a=a.loc[a.cost_bps.eq(20)]
    if 'execution_lag' in a: a=a.loc[a.execution_lag.eq(a.execution_lag.min())]
    regime = next((x for x in ['activity_regime','regime','activity'] if x in a),None)
    mean = next((x for x in ['mean_net_return','mean_hourly_net_return','net_mean_hourly_return','mean_return'] if x in a),None)
    count=next((x for x in ['n_hours','count','observations','n_obs'] if x in a),None)
    if regime and mean:
        if count: a = a.loc[a[count] > 0]
        rows=[['Strategy', 'Regime', 'Hours', 'Mean net (bps/hour)']]
        for _,r in a.iterrows():
            rows.append([_label(r.strategy_id),str(r[regime]),str(int(r[count])) if count else 'N/A',_num(float(r[mean])*1e4,False,3)])
        table(rows,[usable*.40,usable*.20,usable*.15,usable*.25])
    add('Higher trading volume may reflect information, liquidity demand, volatility, or mechanical trading. This split cannot identify informed versus uninformed traders or establish a causal mechanism. Means across discontinuous subsets are not annualized Sharpes; counts matter and serial dependence remains. Zero-hour unknown regimes are retained in the CSV, not displayed above.')
    add('Year-by-year stability', 'SubCustom')
    annual=d['annual_metrics'].copy()
    if 'cost_bps' in annual: annual=annual.loc[annual.cost_bps.eq(20)]
    if 'execution_lag' in annual: annual=annual.loc[annual.execution_lag.eq(annual.execution_lag.min())]
    if len(annual) and 'year' in annual:
        annual=annual.sort_values(['strategy_id','year'])
        rows=[['Strategy', 'Year', 'Net return', 'Sharpe']]
        for _,r in annual.iterrows():
            rows.append([_label(r.strategy_id),str(int(r.year)),_num(_metric(r,'total_return'),True),_num(_metric(r,'sharpe'))])
        if len(rows)<=10:
            table(rows,[usable*.42,usable*.14,usable*.24,usable*.20])
            add('Annual results reset cash and liquidate each year. Earlier-year results for validation-selected configurations are retrospective; they are not independent yearly selections.', 'SmallCustom')
        else: add('Complete annual returns and Sharpe are retained in outputs/annual_metrics.csv and the notebook. Development-period metrics are retrospective descriptions of the validation-selected configurations, not independently selected yearly results.', 'SmallCustom')
    page()

    # 8: explicit conclusions, limitations, and usable source attribution.
    title(8, 'Conclusions, limitations, and reproduction')
    add('Answer to the course research question', 'SubCustom')
    add(escape(verdict))
    add('Momentum and reversal were both implemented and compared under a common unconstrained portfolio rule. The decisive question is not whether some gross curve rises but whether the frozen signal remains economically meaningful after turnover, costs, and timing sensitivity. Results above answer that question only for this dataset and model.')
    add('Material limitations', 'SubCustom')
    for text in [
        '<b>Theoretical short side.</b> Spot price series supply returns, not borrowing availability. Funding, margin, financing, collateral, and liquidation risk are excluded.',
        '<b>Survivor selection.</b> These eight present-day recognizable coins omit failed, delisted, and newly listed alternatives; this is not a point-in-time crypto-wide universe.',
        '<b>Execution.</b> Fixed costs and next-return close alignment do not model spread variation, order-book impact, adverse selection, failed orders, or price latency.',
        '<b>Statistical uncertainty.</b> Eighteen comparisons, one validation year, and one test year leave substantial false-discovery and regime risks. HAC alpha errors are not search-adjusted and cannot substitute for future validation.',
        '<b>Data and numeraire.</b> Unknown outages or missing bars stop research; exchange-specific prices and USDT denomination limit portability. One four-hour 2023 holding interval is observed only at its endpoints; volume regimes become unknown when preceding volume coverage is missing.',
        '<b>Approximate accounting.</b> Target-change turnover ignores portfolio weight drift. Daily annualization uses 365 days rather than equity-market calendars.',
    ]: add(text)
    add('Reproduction', 'SubCustom')
    add('The Python package, TOML configuration, checksum-backed cache, processed Parquet data, frozen selection manifest, and executed notebook are delivered together. The notebook loads local locked inputs, demonstrates the rank-neutral construction, independently rebuilds selected 2025 performance through the package, and reconciles saved returns and metrics. It does not download or retune strategies.')
    add('Sources and attribution', 'SubCustom')
    add('1. <b>Course assignment:</b> The Wall Street Quants, <i>ClassProject.docx</i>; supplied locally. The report uses its unconstrained backtest framing and prescribed 20 bps market-order cost.', 'SmallCustom')
    add(f'2. <b>Binance public market data:</b> archive schema, timestamp conventions, and checksum documentation. <link href="{SOURCE_URL}" color="#245C85">github.com/binance/binance-public-data</link>.', 'SmallCustom')
    add(f'3. <b>Dataset terms:</b> data-derived report, charts, and results are CC BY-NC-SA 4.0; non-commercial educational/research use with attribution. <link href="{TERMS_URL}" color="#245C85">Binance data terms</link>. No exchange endorsement is implied.', 'SmallCustom')

    add(f'4. <b>Observed-halt protocol:</b> <link href="{HALT_URL}" color="#245C85">Binance March 24, 2023 halt explanation</link> and <link href="{RESUMPTION_URL}" color="#245C85">official resumption announcement</link>.', 'SmallCustom')

    def chrome(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor('#DCE4E9')); canvas.setLineWidth(.5)
        canvas.line(45, H-32, W-45, H-32)
        canvas.setFont('Helvetica', 7.5); canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawString(45, H-24, 'CRYPTO STATISTICAL ARBITRAGE / COURSE RESEARCH')
        canvas.drawString(45, 26, 'Binance Vision data-derived analysis | CC BY-NC-SA 4.0 | Research only')
        canvas.drawRightString(W-45,26,str(doc.page))
        canvas.restoreState()
    doc=SimpleDocTemplate(str(path), pagesize=A4, rightMargin=45,leftMargin=45,
                          topMargin=49,bottomMargin=43,title='Crypto Statistical Arbitrage: Momentum and Reversal',
                          author='Course project research', pageCompression=1)
    doc.build(story,onFirstPage=chrome,onLaterPages=chrome)
    from pypdf import PdfReader
    count=len(PdfReader(path).pages)
    if count!=8:
        raise RuntimeError(f'Report overflowed fixed eight-page design: {count} pages; repair layout before delivery.')
    return path


def create_report(root: Path) -> dict:
    """Build the report, evidence figures, and reproducible notebook from outputs."""
    root=Path(root).resolve()
    d=_load(root)
    figures=make_figures(root,d)
    pdf=_render_pdf(root,d,figures)
    notebook=_make_notebook(root,d,figures)
    return {'pdf':str(pdf),'notebook':str(notebook),'figures':figures}


def _make_notebook(root, d, figures):
    """Create and execute a portable teaching companion using frozen local data."""
    import nbformat
    from nbclient import NotebookClient
    from nbconvert import HTMLExporter
    from jupyter_client.manager import KernelManager
    from jupyter_client.kernelspec import KernelSpec
    import sys

    lines, verdict = _summary(d)
    md = nbformat.v4.new_markdown_cell
    code = nbformat.v4.new_code_cell
    cells = []
    cells.append(md("# Crypto statistical arbitrage: momentum and reversal\n\n"
        "An executed research companion to the supplied Wall Street Quants class project. "
        "The notebook uses cached, checksum-audited Binance hourly spot inputs; it never downloads "
        "or reselects strategies. Shorts and close execution are theoretical.\n\n"
        "## tl;dr\n\n" + verdict + "\n\n" + "\n".join("- " + line for line in lines)))
    cells.append(md("## Context & Methods\n\n"
        "**Question:** do price continuation or reversal patterns survive the course's "
        "20 bps one-way trading cost? We compare an 18-configuration predeclared grid. "
        "Development is 2022-2023, selection uses 2024 net Sharpe, and 2025 is the frozen test. "
        "December 2021 supplies warm-up.\n\n"
        "**Documented data exception, fixed before experiments:** Binance spot halted on March 24, "
        "2023 at 11:27 UTC and resumed at 14:00. We bridge the observed 11:00 and 15:00 closes "
        "as one four-hour holding interval: existing exposure remains invested; no fills, costs, "
        "or valuations at 12:00-14:00; no price imputation or dropped reopening return. "
        "Exact elapsed-hour signal endpoints are required; missing denominators defer trading. "
        "Daily returns preserve 24 elapsed hours; drawdown is observed-endpoint during this interval. "
        "Sixteen close-time metadata anomalies are audited, including one daily-archive metadata "
        "repair with identical OHLCV and fifteen allowlisted shortened timestamps. 2025 is complete.\n\n"
        "### Key Assumptions\n\n"
        "- Eight fixed survivors: BTC, ETH, LTC, ADA, LINK, DOGE, DOT, SOL in USDT.\n"
        "- Trailing price-ratio returns; momentum follows winners, reversal follows losers.\n"
        "- Demeaned ranks / absolute-rank sum: dollar-neutral individual families have unit gross, zero net exposure, with average ranks for ties. Blending positions may reduce gross exposure.\n"
        "- Rebalances every 1, 4, or 24 UTC hours; targets held between decisions.\n"
        "- A completed signal earns the next observed interval return (normally one hour, lag 1); lag 2 is an extra-delay stress.\n"
        "- Full L1 weight-change turnover, including entry and liquidation; no drift, funding, "
        "borrow, margin, capacity, or guaranteed limit fills.\n"
        "- Daily compounding uses UTC interval-days (a midnight endpoint belongs to the prior day), "
        "365-day annualization and zero risk-free rate; BTC alpha/beta uses daily OLS + HAC(7)."))
    cells.append(md("### 1. Set up the local project\n\n"
        "Run with `~/.venvs/myenv/bin/python` or a kernel using that environment. "
        "Root detection works from the project root or its notebooks directory."))
    cells.append(code("""from pathlib import Path
import sys, json, hashlib, re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
from IPython.display import display

candidates = [Path.cwd(), Path.cwd().parent]
ROOT = next(p for p in candidates if (p / 'outputs/selection.json').exists())
sys.path.insert(0, str(ROOT / 'src'))
from crypto_stat_arb.data import load_panel
from crypto_stat_arb.backtest import generate_targets, simulate
from crypto_stat_arb.metrics import summarize, daily_returns

get_ipython().run_line_magic('matplotlib', 'inline')
plt.rcParams.update({'figure.figsize': (10, 4), 'font.size': 11,
    'axes.spines.top': False, 'axes.spines.right': False,
    'axes.grid': True, 'grid.color': '#E2E7EB', 'grid.linewidth': 0.6})
PALETTE = {'momentum': '#245C85', 'reversal': '#B66C24', 'combination': '#6D668E'}
def color_for(identifier):
    return next((v for k, v in PALETTE.items() if identifier.startswith(k)), '#6B7781')
def short_label(identifier):
    match = re.fullmatch(r'(momentum|reversal)_h(\\d+)_r(\\d+)', identifier)
    if match:
        family, lookback, rebalance = match.groups()
        return f"{'Mom' if family == 'momentum' else 'Rev'} {int(lookback)}h/{int(rebalance)}h"
    return '50/50 blend' if identifier.startswith('combination') else identifier
print('Project:', ROOT)
print('Python:', sys.executable)
"""))
    cells.append(md("## Data\n\n### 2. Load and validate locked inputs\n\n"
        "`load_panel` verifies the saved Parquet checksum and recomputes the coverage audit. "
        "Unknown missing prices are errors. The single documented 2023 halt is retained as "
        "a four-hour observed holding interval; missing prices are never filled. Quote volume "
        "is used only for the activity diagnostic."))
    cells.append(code("""prices, quote_volume, audit = load_panel(ROOT)
manifest = json.loads((ROOT / 'outputs/run_manifest.json').read_text())
selection_path = ROOT / 'outputs/selection.json'
selection_digest = hashlib.sha256(selection_path.read_bytes()).hexdigest()
selection = json.loads(selection_path.read_text())
assert audit['status'] in ['pass', 'pass_with_documented_exceptions']
assert selection['test_evaluated_before_selection'] is False
assert selection_digest == manifest['selection_sha256']
assert pd.Timestamp(manifest['selection_frozen_at_utc']) < pd.Timestamp(manifest['test_evaluation_started_at_utc'])
print('Price grid shape (documented missing values retained):', prices.shape)
print('UTC coverage:', prices.index.min(), 'to', prices.index.max())
display(pd.DataFrame([{'field': k, 'value': str(audit[k])} for k in
    ['status', 'rows', 'missing_count', 'duplicate_count', 'implicit_fill', 'cross_venue_substitution'] if k in audit]))
display(prices.iloc[[0, -1]])
"""))
    cells.append(md("### 3. Inspect the frozen choices before reproducing the test\n\n"
        "These entries were chosen using 2024 only. Even if a 2025 result is unfavorable, "
        "we keep the same identifiers. The optional blend is present only if both "
        "families passed the positive-net-validation rule."))
    cells.append(code("""selected = selection['selected']
display(pd.DataFrame(selected).set_index('strategy_id')[[
    'family', 'lookback_h', 'rebalance_h', 'validation_net_sharpe',
    'validation_mean_hourly_turnover']].rename(columns={
    'lookback_h': 'lookback hours', 'rebalance_h': 'rebalance hours',
    'validation_net_sharpe': '2024 net Sharpe', 'validation_mean_hourly_turnover': '2024 turnover/hour'}).round(6))
print('Combination eligible:', selection['combination_eligible'])
print('Development-only activity median:', selection['activity_threshold'])
print('Configuration hash:', selection['config_sha256'])
experiments = pd.read_csv(ROOT / 'outputs/experiments.csv')
final_metrics = pd.read_csv(ROOT / 'outputs/final_metrics.csv')
returns = pd.read_parquet(ROOT / 'outputs/selected_returns.parquet')
returns['bar_end'] = pd.to_datetime(returns['bar_end'], utc=True)
base_mask = (final_metrics['cost_bps'].eq(20) & final_metrics['execution_lag'].eq(1))
base_metrics = final_metrics.loc[base_mask].copy()
test_metrics = base_metrics.loc[base_metrics['split'].eq('test')].set_index('strategy_id')
"""))
    cells.append(md("### 4. Demonstrate the portfolio calculation by hand\n\n"
        "At one scheduled test timestamp, recompute trailing returns, ranks and weights "
        "directly. Positive weights sum to 0.5, negative weights to -0.5; this is not "
        "a dollar-neutral guarantee under weight drift. The target uses no future price."))
    cells.append(code("""example = selected[0]
L = example['lookback_h']
R = example['rebalance_h']
t = next(t for t in prices.index if t >= pd.Timestamp('2025-01-02', tz='UTC') and t.hour % R == 0)
raw_signal = prices.loc[t] / prices.shift(L).loc[t] - 1
signal = raw_signal if example['family'] == 'momentum' else -raw_signal
rank = signal.rank(method='average')
centered = rank - rank.mean()
weights = centered / centered.abs().sum() if centered.abs().sum() else centered * 0
example_targets = generate_targets(prices, example['family'], L, R)
np.testing.assert_allclose(weights, example_targets.loc[t], atol=1e-14)
assert abs(weights.sum()) < 1e-14
assert np.isclose(weights.abs().sum(), 1)
display(pd.DataFrame({'trailing_return': raw_signal, 'signal': signal, 'rank': rank, 'weight': weights}).round(5))
print('Scheduled UTC decision:', t)
print('Long / short / gross:', weights.clip(lower=0).sum(), weights.clip(upper=0).sum(), weights.abs().sum())
"""))
    cells.append(md("## Results\n\n### 5. Show all validation candidates\n\n"
        "The grid is limited before inspecting 2025. Ranking below is validation evidence, "
        "not an unbiased estimate of future performance."))
    cells.append(code("""validation = experiments.loc[experiments['split'].eq('validation')].sort_values('sharpe')
fig, ax = plt.subplots(figsize=(10, 6))
ax.barh([short_label(s) for s in validation['strategy_id']], validation['sharpe'],
    color=[color_for(s) for s in validation['strategy_id']])
ax.axvline(0, color='#1D2E3A', linewidth=.8)
ax.set(title='2024 validation net Sharpe: all 18 configurations at 20 bps',
       xlabel='Daily-return Sharpe (365-day annualization)')
ax.grid(axis='y', visible=False)
fig.tight_layout(); plt.show()
display(validation[['strategy_id', 'total_return', 'sharpe', 'mean_hourly_turnover']].sort_values('sharpe', ascending=False).round(5))
"""))
    cells.append(md("### 6. Reproduce the untouched test, then reconcile the saved evidence\n\n"
        "Generate the same frozen targets from cached inputs and simulate 2025 independently "
        "of the saved runner-return table. Also reconstruct gross returns and entry/change/exit "
        "costs directly from held positions. Finally reproduce daily metrics and verify every "
        "saved test return, equity, drawdown, and turnover. No candidate is reselected."))
    cells.append(code("""targets_by_id = {
    s['strategy_id']: generate_targets(prices, s['family'], s['lookback_h'], s['rebalance_h'])
    for s in selected
}
if selection['combination_eligible']:
    targets_by_id['combination_50_50'] = sum(
        selection['combination_weights'][sid] * targets_by_id[sid]
        for sid in selection['combination_weights'])
benchmark = prices['BTCUSDT'].pct_change(fill_method=None)
reproduced = {}
checks = []
for sid, targets in targets_by_id.items():
    result = simulate(prices, targets, '2025-01-01', '2026-01-01', 20, 1)
    frame = result.frame
    manual_gross = (result.held_weights * prices.pct_change(fill_method=None).reindex(frame.index)).sum(axis=1)
    changes = result.held_weights.diff()
    changes.iloc[0] = result.held_weights.iloc[0]
    manual_turnover = changes.abs().sum(axis=1)
    manual_turnover.iloc[-1] += result.held_weights.iloc[-1].abs().sum()
    manual_net = manual_gross - manual_turnover * .002
    np.testing.assert_allclose(manual_net, frame['net_return'], atol=1e-14)
    saved = returns.loc[returns['strategy_id'].eq(sid) & returns['split'].eq('test') &
        returns['cost_bps'].eq(20) & returns['execution_lag'].eq(1)].set_index('bar_end').sort_index()
    assert frame.index.equals(saved.index)
    for column in ['gross_return', 'net_return', 'turnover', 'cost', 'equity', 'drawdown']:
        np.testing.assert_allclose(frame[column], saved[column], rtol=1e-11, atol=1e-13)
    stats = summarize(result, benchmark)
    for column in ['total_return', 'cagr', 'annual_return', 'annual_volatility', 'sharpe',
                   'max_drawdown', 'alpha_annual', 'beta']:
        np.testing.assert_allclose(stats[column], test_metrics.loc[sid, column], rtol=1e-10, atol=1e-12)
    # A second independent daily compounding check uses interval-day membership.
    day = (frame.index - pd.Timedelta(nanoseconds=1)).floor('D')
    manual_daily = (1 + manual_net).groupby(day).prod() - 1
    np.testing.assert_allclose(manual_daily, daily_returns(frame['net_return']), atol=1e-14)
    assert len(frame) == 365 * 24
    assert len(manual_daily) == 365
    checks.append({'strategy_id': sid, 'hours_verified': len(frame), 'days_verified': len(manual_daily),
                   'terminal_equity': frame['equity'].iloc[-1], 'reconciled': True})
    reproduced[sid] = result
assert hashlib.sha256(selection_path.read_bytes()).hexdigest() == selection_digest
display(pd.DataFrame(checks))
"""))
    cells.append(md("### 7. Compare gross and net equity, including initial capital\n\n"
        "Dashed lines remove trading costs only; they do not assert executable gross profits. "
        "Drawdown uses hourly compounded equity and includes the initial unit capital. "
        "Metric-table return and volatility entries are decimal fractions (0.10 means 10%); "
        "maximum drawdown is a positive loss magnitude and alpha intervals are annualized."))
    cells.append(code("""fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True, gridspec_kw={'height_ratios': [2, 1]})
for sid, result in reproduced.items():
    f = result.frame
    dates = f.index.insert(0, f.index[0] - pd.Timedelta(hours=1))
    net = np.r_[1, (1 + f['net_return']).cumprod().values]
    gross = np.r_[1, (1 + f['gross_return']).cumprod().values]
    axes[0].plot(dates, net, color=color_for(sid), label=short_label(sid) + ' net')
    axes[0].plot(dates, gross, color=color_for(sid), linestyle='--', linewidth=.9,
                 label=short_label(sid) + ' gross')
    axes[1].plot(dates, net / np.maximum.accumulate(net) - 1, color=color_for(sid))
axes[0].axhline(1, color='#1D2E3A', linewidth=.8)
axes[0].set(title='2025 frozen test: gross and 20 bps net', ylabel='Compounded equity (start = 1)')
axes[0].legend(fontsize=9, ncol=2, frameon=False)
axes[1].set(ylabel='Hourly net drawdown', xlabel='UTC date')
axes[1].yaxis.set_major_formatter(PercentFormatter(1))
fig.tight_layout(); plt.show()
display(test_metrics[['total_return', 'cagr', 'annual_return', 'annual_volatility', 'sharpe',
    'max_drawdown', 'alpha_annual', 'beta', 'alpha_ci_low', 'alpha_ci_high']].round(6).T)
"""))
    cells.append(md("### 8. Cost and extra-delay stresses\n\n"
        "The same frozen configurations are evaluated under 0, 20, and 40 bps at lag 1, "
        "and 20 bps at lag 2. These scenarios are not confidence bounds. A result that "
        "deteriorates with costs or delay argues against robustness; we do not retune to rescue it."))
    cells.append(code("""stresses = final_metrics.loc[final_metrics['split'].eq('test')].sort_values(['strategy_id', 'execution_lag', 'cost_bps'])
fig, axes = plt.subplots(1, 2, figsize=(10, 4))
for sid, group in stresses.groupby('strategy_id'):
    costs = group.loc[group['execution_lag'].eq(1)].sort_values('cost_bps')
    delays = group.loc[group['cost_bps'].eq(20)].sort_values('execution_lag')
    axes[0].plot(costs['cost_bps'], costs['total_return'], marker='o', color=color_for(sid), label=short_label(sid))
    axes[1].plot(delays['execution_lag'], delays['sharpe'], marker='o', color=color_for(sid))
axes[0].set(title='Cost stress', xlabel='One-way cost (bps)', ylabel='2025 total compounded return', xticks=[0, 20, 40])
axes[0].yaxis.set_major_formatter(PercentFormatter(1))
axes[0].legend(frameon=False, fontsize=9)
axes[1].set(title='Extra-delay stress at 20 bps', xlabel='Signal-to-return lag (hours)', ylabel='2025 daily-return Sharpe', xticks=[1, 2])
for ax in axes: ax.axhline(0, color='#1D2E3A', linewidth=.8)
fig.tight_layout(); plt.show()
display(stresses[['strategy_id', 'cost_bps', 'execution_lag', 'total_return', 'sharpe',
    'max_drawdown', 'total_turnover']].round(5))
"""))
    cells.append(md("### 9. Volume activity and year-by-year stability\n\n"
        "Volume relative to its strictly preceding 168-hour mean is averaged across assets. "
        "The development-only median divides regimes. The label follows each strategy's "
        "rebalance decision and execution lag, preventing future activity from defining past "
        "positions. Missing preceding-volume coverage is an explicit unknown regime. Elapsed-hour "
        "counts and mean observed-interval returns are reported, not artificial annual "
        "Sharpes for discontinuous subsets. Volume does not identify trader information.\n\n"
        "Annual tables reset cash and liquidate at each year boundary. Thus two single-year "
        "equities do not compound exactly to the development split, which has one entry "
        "and one exit. Earlier-year rows for the validation-selected strategies are retrospective."))
    cells.append(code("""activity = pd.read_csv(ROOT / 'outputs/activity_diagnostics.csv')
a = activity.loc[activity['split'].eq('test')].copy()
a['mean_net_bps_per_hour'] = 1e4 * a['mean_hourly_net_return']
display(a[['strategy_id', 'activity_regime', 'n_hours', 'exposure_share',
    'mean_net_bps_per_hour', 'mean_hourly_turnover', 'mean_activity_ratio']].round(6))
activity_pivot = a.pivot(index='strategy_id', columns='activity_regime', values='mean_net_bps_per_hour').dropna(axis=1, how='all')
fig, ax = plt.subplots(figsize=(9, 4))
activity_pivot.index = [short_label(s) for s in activity_pivot.index]
activity_pivot.plot.bar(ax=ax, color=['#245C85', '#B5C8D6'], edgecolor='#245C85', rot=0)
ax.axhline(0, color='#1D2E3A', linewidth=.8)
ax.set(title='2025 net mean returns conditioned on activity', ylabel='Mean net return (bps/hour)', xlabel='')
ax.grid(axis='x', visible=False)
fig.tight_layout(); plt.show()
annual = pd.read_csv(ROOT / 'outputs/annual_metrics.csv')
display(annual[['strategy_id', 'year', 'total_return', 'annual_volatility', 'sharpe', 'max_drawdown']].round(6))
"""))
    cells.append(md("## Takeaways\n\n" + verdict + "\n\n"
        "- The comparisons separate gross predictability from net economic value. "
        "No observed outcome is treated as a guaranteed future profit.\n"
        "- A fixed survivor universe, USDT numeraire, exchange-specific prices and an "
        "unconstrained short side limit external validity.\n"
        "- Close fills, constant costs and target-change turnover are idealizations. "
        "Real deployment requires financing, borrow/funding, capacity and live execution study.\n"
        "- One untouched year does not eliminate selection bias or regime risk. "
        "HAC(7) alpha intervals are not multiple-testing-adjusted.\n"
        "- Volume activity is descriptive; information/liquidity explanations remain hypotheses.\n\n"
        "### Sources and attribution\n\n"
        f"- **Halt evidence:** [Binance official halt explanation]({HALT_URL}) and "
        f"[resumption notice]({RESUMPTION_URL}); exceptional handling affects 2023, not 2025.\n"
        "- **Assignment:** supplied `ClassProject.docx`, The Wall Street Quants course "
        "(20 bps market-order convention; returns, volatility, Sharpe, drawdown, alpha/beta).\n"
        f"- **Data:** [Binance public-data archive documentation]({SOURCE_URL}), original monthly "
        "hourly spot OHLCV archives; SHA-256 receipt in `data/raw/manifest.json`.\n"
        f"- **Terms:** [Binance dataset terms]({TERMS_URL}), non-commercial educational/research "
        "use with attribution and applicable CC BY-NC-SA 4.0 conditions. No Binance endorsement.\n\n"
        "Dataset-derived notebook analysis, charts, and results are shared under CC BY-NC-SA 4.0. \n\n"
        "The package source, research configuration and saved manifests are part of the "
        "handoff. This notebook completed local top-to-bottom execution and full-series "
        "reconciliation of the primary 2025 test outputs."))
    notebook = nbformat.v4.new_notebook(cells=cells,
        metadata={'kernelspec': {'display_name': 'Python 3 (myenv)', 'language': 'python', 'name': 'python3'},
                  'language_info': {'name': 'python', 'version': sys.version.split()[0]}})
    nbformat.validate(notebook)
    path = root / 'notebooks/crypto_stat_arb_research.ipynb'
    path.parent.mkdir(parents=True, exist_ok=True)
    # Avoid depending on the user's default Jupyter interpreter: explicit virtualenv.
    manager = KernelManager(kernel_name='python3')
    manager._kernel_spec = KernelSpec(argv=[sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}'],
        display_name='Python 3 (myenv)', language='python')
    client = NotebookClient(notebook, timeout=180, kernel_name='python3', km=manager,
        resources={'metadata': {'path': str(root)}}, allow_errors=False)
    client.execute()
    nbformat.validate(notebook)
    nbformat.write(notebook, path)
    exporter = HTMLExporter()
    exporter.exclude_input_prompt = True
    exporter.exclude_output_prompt = True
    html, _ = exporter.from_notebook_node(notebook)
    (root / 'notebooks/crypto_stat_arb_research.html').write_text(html)
    return path

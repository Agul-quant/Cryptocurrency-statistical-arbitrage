"""Five-minute pilot artifacts from completed, hash-verified cached research.

This presentation module cannot download prices or select strategies. Every year
in this follow-up is exploratory/retrospective, including January-September 2026.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import PercentFormatter
import numpy as np
import pandas as pd

INK='#243441'; MUTED='#5A6A76'; BLUE='#245C85'; GOLD='#B7772B'; GREY='#738490'
SOURCE='https://github.com/binance/binance-public-data'
TERMS=SOURCE+'/blob/master/TERMS_AND_CONDITIONS.md'
HALT='https://www.binance.com/en/blog/from-our-ceo/6789340645608890113'
SYMBOLS=['BTCUSDT','ETHUSDT','LTCUSDT','ADAUSDT','LINKUSDT','DOGEUSDT','DOTUSDT','SOLUSDT']
SPLITS=['development','validation','retrospective','retrospective_2026']
SPLIT_LABELS={'development':'Development 2022-23','validation':'Selection 2024','retrospective':'Retrospective 2025','retrospective_2026':'Retrospective Jan-Sep 2026'}
START=pd.Timestamp('2026-01-01',tz='UTC'); END=pd.Timestamp('2026-10-01',tz='UTC')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _json(path): return json.loads(Path(path).read_text())


def fmt(value,percent=False,digits=2):
    try:
        value=float(value)
        if not math.isfinite(value): return 'N/A'
        return f'{value:.{digits}%}' if percent else f'{value:.{digits}f}'
    except (TypeError,ValueError): return 'N/A'


def _field(row,*names,default=np.nan):
    return next((row[x] for x in names if x in row and pd.notna(row[x])),default)


def label(identifier):
    text=str(identifier)
    fam='Reversal' if 'reversal' in text.lower() else 'Momentum'
    horizon=re.search(r'(?:lookback|look|lb|l|h|m)[_-]?(\d+)',text,re.I)
    cadence=re.search(r'(?:rebalance|reb|r)[_-]?(\d+)',text,re.I)
    return f'{fam} L{int(horizon.group(1)) if horizon else "?"}m / R{int(cadence.group(1)) if cadence else "?"}m'


def color(identifier): return GOLD if 'reversal' in str(identifier).lower() else BLUE


def primary(df): return df.loc[df.cost_bps.eq(20)&df.execution_lag.eq(1)].copy()


def selected_specs(selection):
    for key in ['selected','champions','selected_strategies']:
        if key in selection:
            v=selection[key]
            if isinstance(v,dict): v=list(v.values())
            return [dict(x) if isinstance(x,dict) else {'strategy_id':x} for x in v]
    raise ValueError('No explicit selected strategy list in completed receipt')


def load_outputs(root:Path):
    root=Path(root); manifest=_json(root/'outputs/run_manifest.json')
    if manifest.get('status')!='complete': raise ValueError('A complete audited run is required; partial research is not a result.')
    digests=manifest.get('research_output_sha256',manifest.get('analysis_output_sha256',{}))
    if not digests: raise ValueError('No research-output hash map in run manifest')
    required={'outputs/experiments.csv','outputs/selection.json','outputs/protocol.json','outputs/selected_returns.parquet','outputs/selected_weights.parquet'}
    if not required.issubset(digests):raise ValueError('Research receipt does not pin all required reporting inputs')
    for path,digest in digests.items():
        if sha256(root/path)!=digest: raise ValueError(f'Completed research differs from receipt: {path}')
    for path,digest in manifest.get('analysis_source_sha256',manifest.get('analysis_hashes',{})).items():
        if sha256(root/path)!=digest: raise ValueError(f'Analysis code differs from receipt: {path}')
    for name in ['protocol','selection']:
        if sha256(root/f'outputs/{name}.json')!=manifest.get(name+'_sha256'):raise ValueError(f'{name.title()} differs from completed receipt')
    if not manifest.get('analysis_source_sha256'):raise ValueError('No immutable analysis-source hash map')
    selection=_json(root/'outputs/selection.json'); protocol=_json(root/'outputs/protocol.json')
    if protocol.get('all_periods_exploratory_retrospective') is not True:raise ValueError('No explicit all-period retrospective classification')
    experiments=pd.read_csv(root/'outputs/experiments.csv')
    if len(experiments)!=504 or experiments.strategy_id.nunique()!=18: raise ValueError('Expected all 18 configurations, four periods, seven scenarios')
    if set(experiments.split)!=set(SPLITS):raise ValueError('Unexpected or missing evaluation partition')
    if experiments.duplicated(['strategy_id','split','cost_bps','execution_lag']).any():raise ValueError('Duplicate configuration-period-scenario metric rows')
    expected={(float(c),1) for c in [0,5,10,15,20,40]}|{(20.,2)}
    for _,case in experiments.groupby(['strategy_id','split']):
        if set(zip(case.cost_bps,case.execution_lag))!=expected:raise ValueError('Missing or unexpected cost/delay scenario')
    specs=selected_specs(selection)
    if len(specs)!=2:raise ValueError('Expected one historical control per family, not post-2026 reselection')
    returns=pd.read_parquet(root/'outputs/selected_returns.parquet');returns['bar_end']=pd.to_datetime(returns.bar_end,utc=True)
    weights=pd.read_parquet(root/'outputs/selected_weights.parquet');weights['bar_end']=pd.to_datetime(weights.bar_end,utc=True)
    if weights.duplicated(['bar_end','strategy_id','split','execution_lag']).any():raise ValueError('Weights must be unique per lag, not duplicated by cost')
    audit=manifest.get('data_quality',manifest.get('data_audit',{}))
    for path in ['data/processed/data_quality.json','outputs/data_quality.json']:
        if not audit and (root/path).exists(): audit=_json(root/path)
    reconciliation=manifest.get('hourly_reconciliation',{})
    for path in ['outputs/data_hourly_reconciliation.json','outputs/hourly_reconciliation.json','data/processed/hourly_reconciliation.json']:
        if not reconciliation and (root/path).exists():reconciliation=_json(root/path)
    return {'root':root,'manifest':manifest,'protocol':protocol,'selection':selection,'specs':specs,'experiments':experiments,'returns':returns,'weights':weights,'audit':audit,'reconciliation':reconciliation}


def _style():
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.titlesize':12,'axes.titleweight':'bold','text.color':INK,'axes.labelcolor':INK,'xtick.color':MUTED,'ytick.color':MUTED,'axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':'#A7B3BA','grid.color':'#E3E8EB','grid.linewidth':.6,'axes.facecolor':'white','figure.facecolor':'white','savefig.facecolor':'white'})


def plot_selection(experiments,selection):
    """All 18 declared cases, both gross and cost-aware 2024 performance."""
    _style();data=primary(experiments);data=data.loc[data.split.eq('validation')]
    chosen={x['strategy_id'] for x in selected_specs(selection)}
    fig,axes=plt.subplots(1,2,figsize=(10,6.2),layout='constrained',sharey=True)
    ids=list(data.sort_values(['family','lookback_minutes','rebalance_minutes']).strategy_id)
    ordered=data.set_index('strategy_id').reindex(ids)
    y=np.arange(len(ids))
    for ax,col,title in zip(axes,['gross_sharpe','sharpe'],['Before costs','At 20 bps']):
        ax.barh(y,ordered[col],color=[color(x) for x in ids])
        ax.set_yticks(y,[label(x)+(' *' if x in chosen else '') for x in ids]);ax.invert_yaxis()
        ax.axvline(0,color=INK,lw=.8);ax.grid(axis='x');ax.set_axisbelow(True)
        ax.set(title=title,xlabel='Daily-return annualized Sharpe')
    fig.suptitle('2024 selection: all 18 cases (independent x scales)',fontsize=13,fontweight='bold')
    return fig


def plot_periods(experiments):
    _style();data=primary(experiments);ids=list(data.loc[data.split.eq('validation')].sort_values(['family','lookback_minutes','rebalance_minutes']).strategy_id)
    matrix=data.pivot(index='strategy_id',columns='split',values='terminal_log_equity').reindex(index=ids,columns=SPLITS)/np.log(10)
    v=matrix.to_numpy();loss=-v;lim=float(np.nanmax(loss))
    fig,ax=plt.subplots(figsize=(10,6.4),layout='constrained')
    im=ax.imshow(loss,cmap='Blues',vmin=0,vmax=lim,aspect='auto')
    ax.set_xticks(range(4),['2022-23','2024','2025','Jan-Sep 2026']);ax.set_yticks(range(len(ids)),[label(x) for x in ids])
    for i in range(len(ids)):
        for j in range(4): ax.text(j,i,fmt(v[i,j],digits=1),ha='center',va='center',color='white' if loss[i,j]>.58*lim else INK,fontsize=9)
    ax.set(title='All 18 cases: terminal log10 retained capital at 20 bps',xlabel='Retrospective partitions (independent unit-capital resets)')
    fig.colorbar(im,ax=ax,label='Capital loss: -log10 terminal equity',shrink=.75)
    return fig


def plot_equity(returns):
    _style();data=returns.loc[returns.split.eq('retrospective_2026')&returns.execution_lag.eq(1)&returns.cost_bps.isin([0,20])]
    ids=list(data.strategy_id.drop_duplicates());fig,axes=plt.subplots(1,len(ids),figsize=(10,4.1),layout='constrained',sharey=True,squeeze=False)
    for ax,identifier in zip(axes.flat,ids):
        for cost,ls in [(0,'--'),(20,'-')]:
            g=data.loc[data.strategy_id.eq(identifier)&data.cost_bps.eq(cost)].sort_values('bar_end')
            if len(g):
                times=[START]+g.bar_end.tolist()
                if 'log_equity' not in g:raise ValueError('Explicit log wealth is required to preserve numerical underflow')
                log_equity=np.r_[0.,g.log_equity.to_numpy()]/np.log(10)
                ax.plot(times,log_equity,ls,color=color(identifier),label='Gross / 0 bps' if cost==0 else 'Net / 20 bps')
        ax.axhline(0,color=INK,lw=.7);ax.grid();ax.set(title=label(identifier),ylabel='log10 equity (Jan 1 = 0; -1 = 90% loss)')
        ax.set_xticks([START,pd.Timestamp('2026-04-01',tz='UTC'),pd.Timestamp('2026-07-01',tz='UTC'),END]);ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'));ax.legend(frameon=False,fontsize=9)
    return fig


def plot_costs(experiments,selection):
    _style();ids=[x['strategy_id'] for x in selected_specs(selection)]
    data=experiments.loc[experiments.split.eq('retrospective_2026')&experiments.execution_lag.eq(1)&experiments.strategy_id.isin(ids)]
    fig,axes=plt.subplots(1,2,figsize=(10,3.7),layout='constrained')
    for identifier in ids:
        g=data.loc[data.strategy_id.eq(identifier)].sort_values('cost_bps')
        for ax,col in zip(axes,['total_return','annual_return']):
            ax.plot(g.cost_bps,g[col],marker='o',color=color(identifier),ls='--' if 'reversal' in identifier else '-',label=label(identifier))
    for ax,title in zip(axes,['Actual nine-month net return','Annualized mean daily net return']):
        ax.axhline(0,color=INK,lw=.7);ax.grid();ax.set(title=title,xlabel='All-in one-way cost (bps)');ax.yaxis.set_major_formatter(PercentFormatter(1));ax.set_xticks([0,5,10,15,20,40]);ax.legend(frameon=False,fontsize=8)
    return fig


def plot_turnover(experiments):
    _style();g=primary(experiments);g=g.loc[g.split.eq('retrospective_2026')].sort_values(['family','lookback_minutes','rebalance_minutes'])
    ids=list(g.strategy_id);turn=g.total_turnover.to_numpy()/273
    fig,ax=plt.subplots(figsize=(10,5.6),layout='constrained');ax.barh(np.arange(len(g)),turn,color=[color(x) for x in ids]);ax.set_yticks(range(len(g)),[label(x) for x in ids]);ax.invert_yaxis();ax.grid(axis='x');ax.set_axisbelow(True)
    ax.set(title='Jan-Sep 2026 full-L1 turnover: all 18 configurations',xlabel='Capital-weight units traded per calendar day (entry and liquidation included)')
    return fig


def make_figures(root,d):
    folder=Path(root)/'reports/figures';folder.mkdir(parents=True,exist_ok=True)
    calls={'selection':plot_selection(d['experiments'],d['selection']),'periods':plot_periods(d['experiments']),'equity':plot_equity(d['returns']),'costs':plot_costs(d['experiments'],d['selection']),'turnover':plot_turnover(d['experiments'])}
    paths={}
    for key,fig in calls.items():
        path=folder/f'{key}.png';fig.savefig(path,dpi=180,bbox_inches='tight');plt.close(fig);paths[key]=str(path)
    return paths


def historical_break_even(d):
    """Post-hoc zero-compounded-return diagnostic, never a selection rule."""
    from scipy.optimize import brentq
    g=d['returns'].loc[d['returns'].split.eq('retrospective_2026')&d['returns'].execution_lag.eq(1)&d['returns'].cost_bps.eq(0)]
    out={}
    for identifier,case in g.groupby('strategy_id'):
        gross=case.gross_return.to_numpy();turn=case.turnover.to_numpy()
        def terminal_log(cost_bps):
            net=gross-cost_bps*1e-4*turn
            if (net<=-1).any():raise ValueError('Invalid insolvent interval for break-even search')
            return float(np.log1p(net).sum())
        zero=terminal_log(0)
        if zero<0:out[identifier]={'cost_bps':None,'reason':'Already negative before costs; no nonnegative zero-profit cost.'}
        else:
            bound=5.
            if terminal_log(bound)>0:raise ValueError('Declared 5-bps stress does not bracket post-hoc break-even')
            result=float(brentq(terminal_log,0,bound,xtol=1e-13));out[identifier]={'cost_bps':result,'residual_terminal_log_equity':terminal_log(result),'classification':'Post-hoc historical diagnostic; no reselection or future promise.'}
    return out


def conclusions(d):
    g=primary(d['experiments']);period=g.loc[g.split.eq('retrospective_2026')]
    ids=[x['strategy_id'] for x in d['specs']];selected=period.loc[period.strategy_id.isin(ids)]
    lines=[f'At 20 bps, {int(period.total_return.gt(0).sum())} of 18 configurations had positive January-September 2026 net returns. Across all four partitions, {int(g.total_return.lt(0).sum())} of 72 primary case-period results were negative. Every case is retained; this is descriptive, not a corrected discovery test.']
    for _,r in selected.iterrows():
        stress=d['experiments'].loc[d['experiments'].strategy_id.eq(r.strategy_id)&d['experiments'].split.eq('retrospective_2026')&d['experiments'].execution_lag.eq(1)&d['experiments'].cost_bps.eq(5)].iloc[0]
        retained=float(np.exp(r.terminal_log_equity))
        lines.append(label(r.strategy_id)+': gross '+fmt(r.gross_total_return,True)+'; net at 5 bps '+fmt(stress.total_return,True)+'; at 20 bps retained only '+f'{retained:.3g}'+' of initial capital (net return rounds to -100%). The selected 2024 control was already negative after costs.')
    lines.append('Five-minute sampling is a new measurement granularity, not new untouched market history. Every period in this follow-up, including 2026, is exploratory/retrospective. Shorter horizons do not lower costs, and OHLCV closes do not demonstrate executable microstructure profits.')
    return lines


def create_pdf(root,d,figures):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image,PageBreak
    from PIL import Image as PILImage
    root=Path(root);path=root/'reports/intraday_5m_report.pdf';path.parent.mkdir(exist_ok=True)
    width,height=A4;usable=width-90;story=[]
    styles={
      'Title':ParagraphStyle('Title',fontName='Helvetica-Bold',fontSize=24,leading=28,textColor=colors.HexColor(INK),spaceAfter=16),
      'Head':ParagraphStyle('Head',fontName='Helvetica-Bold',fontSize=16,leading=20,textColor=colors.HexColor(INK),spaceAfter=12),
      'Sub':ParagraphStyle('Sub',fontName='Helvetica-Bold',fontSize=11.5,leading=15,textColor=colors.HexColor(INK),spaceBefore=9,spaceAfter=7),
      'Body':ParagraphStyle('Body',fontName='Helvetica',fontSize=10,leading=14.2,textColor=colors.HexColor(INK),spaceAfter=9),
      'Small':ParagraphStyle('Small',fontName='Helvetica',fontSize=8.5,leading=11.8,textColor=colors.HexColor(MUTED),spaceAfter=8),
      'Cell':ParagraphStyle('Cell',fontName='Helvetica',fontSize=8,leading=10,textColor=colors.HexColor(INK))}
    def add(text,style='Body'):story.append(Paragraph(text,styles[style]))
    def page(n,title):
        if story:story.append(PageBreak())
        add(f'{n:02d} / {title}','Head')
    def table(rows,widths):
        t=Table([[Paragraph(escape(str(c)),styles['Cell']) for c in row] for row in rows],colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E8EEF2')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),('LINEBELOW',(0,0),(-1,0),.5,colors.HexColor('#A7B3BA')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F5F7F8')])]))
        story.extend([t,Spacer(1,10)])
    def image(key,maxheight=420):
        im=PILImage.open(figures[key]);w,h=im.size;scale=min(usable/w,maxheight/h);story.extend([Image(figures[key],width=w*scale,height=h*scale),Spacer(1,9)])
    add('Short-horizon crypto signals\nneed a cost-aware test','Title')
    add('Five-minute OHLCV pilot | Separate supplementary project through September 30, 2026','Small')
    add('Executive summary','Sub')
    for line in conclusions(d):add(escape(line))
    table([['Pilot dimension','Declared scope'],['Market','Eight fixed Binance spot USDT pairs; theoretical long/short'],['Grid','Momentum/reversal x 5/15/30-minute lookback x 5/15/60-minute rebalance = 18'],['Primary','20 bps full-L1 cost, one five-minute-bar execution lag'],['Stress','0/5/10/15/40 bps; extra five-minute execution delay at 20 bps'],['Evidence','All four periods are exploratory/retrospective; no fresh holdout']],[usable*.25,usable*.75])
    add('This is an educational close-price simulation, not risk-free arbitrage or a deployment recommendation. The original project and its expanded hourly extension remain unchanged.','Small')

    page(2,'Actual five-minute data and granular halt audit')
    table([['Partition','Dates','Purpose'],['Warm-up','December 2021','Signals only'],['Development','2022-2023','Implementation and historical comparison'],['Selection','2024','One control per family by net daily Sharpe'],['Retrospective','2025','Already examined at coarser granularity'],['Retrospective 2026','Jan 1-Sep 30','273 days; 78,624 regular five-minute intervals']],[usable*.23,usable*.27,usable*.5])
    add('Source and timestamp conventions','Sub');add('The study uses actual Binance 5m archives, not prices interpolated from hourly bars. Each completed bar is indexed by open time plus five minutes; Binance spot timestamp units change from milliseconds to microseconds in January 2025. Archive checksums, metadata anomalies, repairs, duplicates and unexplained gaps are audited before research.')
    audit=d['audit']
    add('Data-audit status: '+escape(str(audit.get('status','see accompanying audit')))+'. This is not an exception-free clean pass. Observed asset-bar rows: '+fmt(audit.get('rows'),digits=0)+'; expected: '+fmt(audit.get('expected_rows'),digits=0)+'; missing asset-bars: '+fmt(audit.get('missing_count'),digits=0)+'. The 464 verified monthly archives cover 178.7 MB compressed. Sixteen close-time metadata anomalies comprise one SOL metadata-field-only repair and 15 warnings; no OHLCV price/volume is repaired. Exact counts and digests are retained.','Small')
    add('March 24, 2023: one observed 160-minute bridge','Sub');add('The granular suspension treatment is 11:25 to 14:05 UTC, not the hourly study\'s coarser 11:00 to 15:00 window. Raw partial and zero-trade records are retained as source evidence, but no interior price valuation or execution is simulated. Existing holdings earn the single true close-to-close return over 160 elapsed minutes. Sixteen missing five-minute endpoints per asset (12:45-14:00 UTC) are documented; missing prices are never filled. No intrahalt mark-to-market drawdown can be reconstructed.')
    add('Hourly reconciliation is a data check, not a portfolio claim','Sub');add('Among 338,864 finite hourly price comparisons, three close discrepancies and 134 quote-volume discrepancies are retained, all in December 2021 warm-up; none occur among 332,920 finite evaluated-window close comparisons in January 2022-September 2026. Verified five-minute daily closes match the hourly source at the three discrepant endpoints but differ from the monthly five-minute archives. No source values are replaced, and no evaluated return or at-most-30-minute signal uses those early-December endpoints. The data check does not imply equal portfolio returns across trading frequencies. Volume tolerance and every exception remain in the receipts.','Small')

    page(3,'Declared grid, historical selection, and accounting')
    add('Cross-sectional signals','Sub');add('At scheduled UTC decisions, rank each coin\'s elapsed-time trailing return, demean the ranks and normalize full L1 exposure to one. Momentum holds high-rank coins long and low-rank coins short; reversal flips the signs. Ties use averaged ranks; constant signals remain cash. Targets are dollar-neutral, but market beta need not be zero. Scheduled 5/15/60-minute rebalances do not trade every five-minute observation unless the cadence is five minutes.')
    add('Selection is a control, not independent confirmation','Sub');add('One configuration per family is selected by highest defined 2024 net daily-return Sharpe at 20 bps. Ties prefer lower turnover, then fixed experiment ID. Negative winners remain research controls. The complete 18-case, four-period, seven-scenario table prevents hiding unsuccessful cases. The protocol was declared before strategy calculations; source-data inspection was already underway. This is not a data-naive preregistration and does not erase prior knowledge of the same calendar history.')
    selected=primary(d['experiments']);selected=selected.loc[selected.split.eq('validation')&selected.strategy_id.isin([x['strategy_id'] for x in d['specs']])]
    table([['2024 selected control','Net return','Net Sharpe','Full-L1 turnover']]+[[label(r.strategy_id),fmt(r.total_return,True),fmt(r.sharpe),fmt(r.total_turnover)] for _,r in selected.iterrows()],[usable*.4,usable*.2,usable*.18,usable*.22])
    add('Execution and cash resets','Sub');add('Targets use completed observed endpoints only. Lag one earns the following five-minute interval; lag two adds another five minutes. The suspension prevents interior execution. Each evaluation starts from cash, preserves warm-up signals, and charges both initial entry and final liquidation. No forced cash-out is invented before the 2023 halt.')
    add('Net return = held-weight simple asset return - (bps / 10,000) x full-L1 executed weight change. Ordinary position-weight drift is omitted, as in the course model. Equity compounds all interval returns; near-total loss can round to -100% while mathematical equity is still positive. Daily returns compound five-minute and bridge returns using their actual UTC intervals.')
    add('Annualization uses 365 calendar days, zero risk-free rate, daily sample volatility and mean-daily-return Sharpe. Nine-month total return differs from CAGR and annualized mean return. BTC alpha/beta use daily OLS with an intercept and HAC(7) uncertainty; these are descriptive, not proof of arbitrage.','Small')

    page(4,'Gross signals versus 2024 cost-aware selection')
    image('selection',460)
    add('Each of the 18 cases is shown before and after 20 bps costs, using daily compounded returns rather than pretending five-minute samples are independent daily observations. An asterisk marks the two historically selected controls. The two panels use independent horizontal scales to expose detail; read the numeric axes rather than comparing bar lengths across panels. Their values show whether gross performance survives the declared friction.')
    add('A positive gross Sharpe does not establish executable profit. These prices contain last-trade OHLCV data, not contemporaneous bid/ask spread, queue priority, borrow availability, or market impact. The course\'s assumed seven-bps commission alone exceeds the total five-bps sensitivity scenario.','Small')

    page(5,'All 18 cases across every evaluation period')
    image('periods',445)
    add('Every cell is terminal log10 retained capital at 20 bps, with an independent unit-capital reset: -1 means 0.1 remains, -10 means 10^-10 remains. This exposes distinctions hidden when total returns all round to -100%. Development covers two years; 2024 and 2025 cover one each; 2026 covers nine months. These durations are intentionally unequal, so use the daily annualized metrics in experiments.csv for risk-normalized comparison.')
    add('No cell is an untouched test. Trying a finer frequency after viewing earlier outcomes is a new exploratory specification. Best-looking later-period cases are not promoted to new selections. Rounded -100% cells may have distinct tiny positive equities and turnover; the exact CSV metrics and terminal log-capital matrix retain that distinction.','Small')

    page(6,'Two selected controls: retrospective 2026 paths')
    image('equity',270)
    g=primary(d['experiments']);g=g.loc[g.split.eq('retrospective_2026')&g.strategy_id.isin([x['strategy_id'] for x in d['specs']])]
    table([['Control','Gross return','Net return','Gross SR','Net SR','Max DD']]+[[label(r.strategy_id),fmt(r.gross_total_return,True),fmt(r.total_return,True),fmt(r.gross_sharpe),fmt(r.sharpe),fmt(r.max_drawdown,True)] for _,r in g.iterrows()],[usable*.33,usable*.14,usable*.14,usable*.13,usable*.13,usable*.13])
    table([['Control','Annual vol','CAGR','Mean daily x365','BTC beta']]+[[label(r.strategy_id),fmt(_field(r,'annual_volatility','volatility'),True),fmt(r.cagr,True),fmt(r.annual_return,True),fmt(_field(r,'beta','btc_beta'))] for _,r in g.iterrows()],[usable*.36,usable*.16,usable*.16,usable*.16,usable*.16])
    add('The graph uses stored log wealth divided by ln(10): zero on the axis is unit capital, -1 is equity 0.1, and -2 is equity 0.01. Finite log wealth remains valid when displayed floating-point equity underflows to zero; that numerical limit is not bankruptcy. Interval returns at or below -100% are rejected, never clipped. Gross and net lines use identical signals, so their separation is modeled cost, not a different strategy.')
    add('At 20 bps, the two selected paths retain '+', '.join(label(r.strategy_id)+': '+f'{np.exp(r.terminal_log_equity):.3g}' for _,r in g.iterrows())+' of initial capital. Their equity-underflow counts are zero: rounding their returns to -100% is not the same as floating-point underflow. Some faster 40-bps development scenarios do underflow displayed equity; their finite log wealth is retained.','Small')
    add('OLS alpha/beta and their uncertainty are retained in the notebook and full configuration table. Estimated dollar neutrality does not imply beta neutrality; theoretical spot shorts remain unconstrained by financing or margin.','Small')

    page(7,'Cost sensitivity and an additional five-minute delay')
    image('costs',260)
    ids=[x['strategy_id'] for x in d['specs']];lag=d['experiments'].loc[d['experiments'].split.eq('retrospective_2026')&d['experiments'].strategy_id.isin(ids)&d['experiments'].cost_bps.eq(20)]
    table([['Control','Execution lag','Net return','Net Sharpe','Turnover']]+[[label(r.strategy_id),str(r.execution_lag*5)+' minutes',fmt(r.total_return,True),fmt(r.sharpe),fmt(r.total_turnover)] for _,r in lag.sort_values(['strategy_id','execution_lag']).iterrows()],[usable*.36,usable*.16,usable*.16,usable*.15,usable*.17])
    add('The left panel shows actual nine-month compounded return; the right shows the annualized arithmetic mean of compounded daily returns. The latter preserves distinctions when many total returns round near -100%. Cost scenarios are stress assumptions, not confidence intervals or observed exchange spreads.')
    add('Post-hoc historical break-even','Sub');add('For the selected reversal control, solving sum(log(1 + gross_return - cost_rate x turnover)) = 0 on the saved 2026 path gives approximately 0.34 bps total one-way cost. Momentum is already negative before costs and has no nonnegative break-even. This is a post-hoc derivative diagnostic, not a selection rule, confidence interval, or promise for future prices. The reversal threshold is far below the assumed seven-bps commission alone.','Small')
    add('Five minutes is a signal and execution resolution, not a reason to reduce 20 bps. Full-L1 turnover can repeatedly consume capital. Close-based one-bar execution and the additional-bar delay do not model intrabar order placement or guaranteed fills.','Small')

    page(8,'Turnover is part of the strategy, not an afterthought')
    image('turnover',395)
    add('This is sum of absolute executed weight changes divided by 273 calendar days. Initial entry and final liquidation are included. It is not trade count, and it is not portfolio gross exposure. Reversal and momentum can have similar turnover because changing the signs does not remove frequent rank rotation.')
    add('The two selected controls average 31.20 full-L1 weight units/day in this window. Multiplying by 20 bps gives about 6.24% of capital as summed daily interval cost rates; it is not 6.24% of initial capital paid in actual cash each day.','Small')
    add('Primary daily BTC attribution and exposure','Sub')
    table([['Control','Annual alpha','HAC(7) 95% alpha CI','Mean gross','Mean net']]+[[label(r.strategy_id),fmt(r.alpha_annual,True),fmt(r.alpha_ci_low,True)+' to '+fmt(r.alpha_ci_high,True),fmt(r.mean_gross_exposure),fmt(r.mean_net_exposure)] for _,r in g.iterrows()],[usable*.33,usable*.16,usable*.25,usable*.13,usable*.13])
    add('At a fixed cost rate, interval cost is exactly rate times full-L1 turnover. Summed interval costs are capital-return fractions; they do not add linearly to compounded total-return differences. The notebook independently reconciles holdings, net/gross P&amp;L, turnover, entry/liquidation, elapsed minutes and daily compounding from cached prices.')

    page(9,'Limitations, attribution, and reproduction')
    add('What this pilot cannot establish','Sub');add('A fixed eight-coin survivor universe may exclude failures and delistings. Spot short positions are theoretical: borrow, funding, financing, collateral, margin calls, position limits and capacity are absent. OHLCV is not an order book. A close fill is idealized; endpoint data cannot recover intrabar path, spread, queue position, partial fill, adverse selection, or intrahalt drawdown. USDT is treated as the numeraire. No live orders or scheduled monitoring are created.')
    add('Selection and uncertainty','Sub');add('Eighteen configurations, repeated years and multiple costs are a research family, not eighteen independent discoveries. The chosen controls use 2024, but the complete pilot is retrospective because these calendar years were already examined at coarser granularity. Daily HAC intervals describe regression uncertainty under the stated convention, not all model-selection or microstructure risks. Future work must use further unexamined/prospective data and tradable price/borrow evidence before deployment claims.')
    add('Reproduce from inspectable artifacts','Sub');add('The standalone project includes declared protocol, every configuration-level result, selected returns and weights, normalized cached data, source/checksum receipts, preservation evidence, tests, this report, and an executed explained notebook. Reporting verifies completed research hashes and cannot select or download. Regenerate with <font name="Courier">python -m crypto_intraday_5m report</font>; run tests with <font name="Courier">python -m pytest -q</font>. Use the specified myenv Python environment.','Small')
    add('Sources','Sub')
    for title,url in [('Binance public archive documentation',SOURCE),('Binance dataset terms',TERMS),('Official 2023 incident account',HALT)]:add(f'<link href="{url}" color="{BLUE}">{title}</link>','Small')
    add('Assignment source: /Users/cosdis/Downloads/quant_course/ClassProject.docx. This supplementary pilot is separate from the original project and the expanded hourly research. Both projects and their ZIPs are checksum-preserved; no publication is performed.','Small')
    add('Binance data and dataset-derived charts/results are attributed to Binance under its stated CC BY-NC-SA 4.0 non-commercial educational/personal non-production terms. This is a historical educational experiment, not financial advice.','Small')
    def footer(canvas,doc):
        canvas.setStrokeColor(colors.HexColor('#BCC6CC'));canvas.line(45,43,width-45,43);canvas.setFillColor(colors.HexColor(MUTED));canvas.setFont('Helvetica',8);canvas.drawString(45,31,'FIVE-MINUTE CRYPTO PILOT | Exploratory / retrospective research');canvas.drawRightString(width-45,31,str(doc.page))
    SimpleDocTemplate(str(path),pagesize=A4,leftMargin=45,rightMargin=45,topMargin=45,bottomMargin=58,title='Five-minute crypto strategy pilot',author='Educational research').build(story,onFirstPage=footer,onLaterPages=footer)
    return path


def reconcile_selected(root,d):
    """Independent accounting using cached raw endpoint prices, not simulator API."""
    from .data import load_panel
    close,quote,audit=load_panel(Path(root))
    observed=close.copy()
    for bridge in close.attrs.get('halt_bridges',[]):
        begin=pd.Timestamp(bridge['start']);end=pd.Timestamp(bridge['end'])
        observed=observed.loc[~((observed.index>begin)&(observed.index<end))]
    if observed.isna().any().any():raise AssertionError('Unexplained missing price outside the declared halt bridge')
    asset_returns=observed.pct_change(fill_method=None)
    data=primary(d['returns']);checks=[]
    for (identifier,split),g in data.groupby(['strategy_id','split'],sort=True):
        g=g.sort_values('bar_end');weights=d['weights'].loc[d['weights'].strategy_id.eq(identifier)&d['weights'].split.eq(split)&d['weights'].execution_lag.eq(1)].set_index('bar_end')[SYMBOLS].reindex(g.bar_end)
        if weights.isna().any().any():raise AssertionError('Missing held weights')
        actual=asset_returns.reindex(g.bar_end)[SYMBOLS]
        if actual.isna().any().any():raise AssertionError('Unexplained missing valuation return')
        gross=np.sum(weights.to_numpy()*actual.to_numpy(),axis=1)
        delta=weights.diff();delta.iloc[0]=weights.iloc[0]
        turnover=delta.abs().sum(axis=1).to_numpy();turnover[-1]+=weights.iloc[-1].abs().sum()
        np.testing.assert_allclose(g.gross_return,gross,atol=1e-12,rtol=1e-10)
        np.testing.assert_allclose(g.turnover,turnover,atol=1e-12,rtol=1e-10)
        np.testing.assert_allclose(g.cost,g.turnover*.002,atol=1e-12,rtol=1e-10)
        np.testing.assert_allclose(g.net_return,g.gross_return-g.cost,atol=1e-12,rtol=1e-10)
        net=g.net_return.to_numpy();equity=np.exp(np.cumsum(np.log1p(net)))
        np.testing.assert_allclose(g.equity,equity,atol=1e-12,rtol=1e-9)
        if (net<=-1).any():raise AssertionError('True insolvent interval cannot be silently clipped')
        log_equity=np.cumsum(np.log1p(net));np.testing.assert_allclose(g.log_equity,log_equity,atol=1e-9,rtol=1e-10)
        peaks=np.maximum.accumulate(np.r_[0.,log_equity])[1:]
        drawdown=np.expm1(log_equity-peaks)
        if 'drawdown' in g:np.testing.assert_allclose(g.drawdown,drawdown,atol=1e-12,rtol=1e-9)
        interval_days=(pd.DatetimeIndex(g.bar_end)-pd.Timedelta(nanoseconds=1)).floor('D')
        duration=pd.Series(g.interval_minutes.to_numpy(),index=interval_days)
        if not duration.groupby(level=0).sum().eq(1440).all():raise AssertionError('UTC days must cover 1440 elapsed minutes, including the bridge')
        daily=pd.Series(1+net,index=interval_days).groupby(level=0).prod()-1
        row=primary(d['experiments']);row=row.loc[row.strategy_id.eq(identifier)&row.split.eq(split)].iloc[0]
        volatility=daily.std(ddof=1)*np.sqrt(365);sharpe=daily.mean()/daily.std(ddof=1)*np.sqrt(365) if daily.std(ddof=1)>1e-15 else np.nan
        np.testing.assert_allclose(_field(row,'annual_volatility','volatility'),volatility,atol=1e-10,rtol=1e-9)
        np.testing.assert_allclose(row.sharpe,sharpe,atol=1e-9,rtol=1e-9,equal_nan=True)
        if 'total_return' in row:np.testing.assert_allclose(row.total_return,np.expm1(log_equity[-1]),atol=1e-11,rtol=1e-9)
        if 'annual_return' in row:np.testing.assert_allclose(row.annual_return,daily.mean()*365,atol=1e-10,rtol=1e-9)
        if 'max_drawdown' in row:np.testing.assert_allclose(row.max_drawdown,max(0.,-drawdown.min()),atol=1e-11,rtol=1e-9)
        btc_daily=pd.Series(1+actual['BTCUSDT'].to_numpy(),index=interval_days).groupby(level=0).prod()-1
        if len(daily)>=3 and btc_daily.std(ddof=1)>1e-15:
            X=np.column_stack([np.ones(len(btc_daily)),btc_daily.to_numpy()])
            alpha,beta=np.linalg.lstsq(X,daily.to_numpy(),rcond=None)[0]
            if 'beta' in row:np.testing.assert_allclose(row.beta,beta,atol=1e-9,rtol=1e-8)
            if 'alpha_annual' in row:np.testing.assert_allclose(row.alpha_annual,alpha*365,atol=1e-9,rtol=1e-8)
        if split=='retrospective_2026':
            assert len(g)==78624 and len(daily)==273 and g.bar_end.iloc[-1]==END
            assert math.isclose(float(g.interval_minutes.sum()),393120)
        checks.append({'strategy_id':identifier,'split':split,'observations':len(g),'daily_observations':len(daily),'total_return':equity[-1]-1,'full_l1_turnover':float(turnover.sum()),'status':'reconciled'})
    return pd.DataFrame(checks)


def create_notebook(root,d):
    import nbformat
    from nbclient import NotebookClient
    from nbconvert import HTMLExporter
    from jupyter_client import KernelManager
    from jupyter_client.kernelspec import KernelSpec
    root=Path(root);folder=root/'notebooks';folder.mkdir(exist_ok=True)
    path=folder/'intraday_5m_research.ipynb';html=folder/'intraday_5m_research.html';nb=nbformat.v4.new_notebook();cells=[]
    def md(s):cells.append(nbformat.v4.new_markdown_cell(s))
    def code(s):cells.append(nbformat.v4.new_code_cell(s))
    md('# Five-minute crypto strategy pilot\n\n## tl;dr\n\n'+'\n\n'.join('- '+x for x in conclusions(d)))
    md('## Context & Methods\n\nActual 5m bars, 18 declared momentum/reversal configurations, 5/15/30-minute trailing signals, 5/15/60-minute calendar schedules. One historically selected control per family uses 2024 net daily Sharpe at 20 bps, turnover then ID for ties. **Every period is exploratory/retrospective, including 2026**; changing granularity does not recreate an untouched holdout.\n\n### Key Assumptions\n\nTheoretical spot shorts; gross-one rank/demean/full-L1 targets; averaged ties and cash for constant signals. Cost is all-in one-way bps times full-L1 changes, including entry/liquidation. Completed endpoint signals with one-bar lag; lag two adds five minutes. No funding/borrow, drift turnover, capacity, or guaranteed close fills. Daily compounded returns use 365-day annualization; minute samples are not independent daily returns.')
    md('### 1. Load completed hash-verified research\n\nNo cell downloads prices or changes selections. Inputs are the completed experiment/protocol receipts and cached audited sources.')
    code("from pathlib import Path\nimport sys,json\nimport numpy as np\nimport pandas as pd\nimport matplotlib.pyplot as plt\nfrom IPython.display import display\nROOT=Path.cwd()\nif not (ROOT/'outputs/run_manifest.json').exists(): ROOT=ROOT.parent\nsys.path.insert(0,str(ROOT/'src'))\nfrom crypto_intraday_5m.reporting import (load_outputs,primary,label,reconcile_selected,plot_selection,plot_periods,plot_equity,plot_costs,plot_turnover,historical_break_even)\nd=load_outputs(ROOT)\nprint('Classification: entire pilot exploratory/retrospective; no fresh holdout.')\nprint('Grid:',d['experiments'].strategy_id.nunique(),'configurations;',len(d['experiments']),'configuration-period-scenario rows.')\nspec_table=pd.DataFrame(d['specs'])\ndisplay(spec_table[['strategy_id','lookback_minutes','rebalance_minutes','role','validation_sharpe']].round(5))")
    md('## Data\n\n### 2. Inspect the actual five-minute audit\n\nEndpoint = bar-open plus five minutes. Source timestamp units switch in January 2025. The March 24, 2023 bridge is 11:25 to 14:05 UTC (160 minutes), with no interior valuation/execution or filled missing prices. Raw partial/zero-trade bars remain source evidence. The hourly comparison retains three monthly-close and 134 volume discrepancies, all in December 2021 warm-up, and none in evaluated January 2022-September 2026. Verified daily five-minute closes match hourly at the three discrepant endpoints; no source values are replaced. No evaluated return or max-30-minute lookback uses those early-December endpoints. Price/volume reconciliation is a data check, not a portfolio-equivalence claim.')
    code("audit=d['audit']\ndisplay(pd.DataFrame([{'item':k,'value':audit.get(k)} for k in ['status','rows','expected_rows','panel_rows','missing_count','duplicate_count','normalized_parquet_sha256']]))\nprint('Hourly data reconciliation (scalar receipt fields; complete receipt retained):')\ndisplay(pd.DataFrame([{'item':k,'value':str(v)} for k,v in d['reconciliation'].items() if not isinstance(v,(dict,list))]))")
    md('### 3. Independently reconcile selected holdings and accounting\n\nThis calculation does not call the simulator: it uses cached observed close-to-close returns, removes only the declared halt interior, recomputes held-weight P&L, full-L1 turnover, cash entry/final liquidation, cost, compounded equity, daily volatility and Sharpe. The 2026 window must contain 78,624 five-minute returns spanning 393,120 minutes and 273 complete days.')
    code("reconciled=reconcile_selected(ROOT,d)\ndisplay(reconciled.round(8))\nassert len(reconciled)==8\nprint('All selected model/period primary reconciliations passed.')")
    md('## Results\n\n### 4. All declared 2024 configurations: gross versus cost-aware\n\nAsterisks mark the historically selected controls. Gross and net performance use the same signals; no 2025/2026 observation determines selection.')
    code("fig=plot_selection(d['experiments'],d['selection'])\nplt.show()\ng=primary(d['experiments']);validation=g.loc[g.split.eq('validation')]\ndisplay(validation[['strategy_id','gross_total_return','total_return','gross_sharpe','sharpe','total_turnover']].round(5))")
    md('### 5. Every case across all retrospective partitions\n\nAll 18 cases are retained, not just the selected two. The matrix shows terminal log10 capital, preserving severe-loss distinctions hidden by -100% rounding: -10 means only 10^-10 of initial capital remains. Periods have unequal durations: two years, one year, one year, nine months. Rounded -100% paths may remain mathematically positive but economically wiped out; inspect the exact CSV and log equity rather than treating them as identical or missing.')
    code("fig=plot_periods(d['experiments'])\nplt.show()")
    md('### 6. Selected 2026 paths on a logarithmic scale\n\nThe graph uses stored log wealth divided by ln(10), preserving finite wealth even if displayed floating-point equity underflows to zero. Underflow is not bankruptcy; invalid interval returns at or below -100% are rejected, not clipped. These are January-September retrospective paths, not a fresh holdout.')
    code("fig=plot_equity(d['returns'])\nplt.show()\nids=[x['strategy_id'] for x in d['specs']]\nselected=g.loc[g.split.eq('retrospective_2026')&g.strategy_id.isin(ids)]\ndisplay(selected[['strategy_id','gross_total_return','total_return','annual_volatility','sharpe','max_drawdown']].round(6))")
    md('### 7. Annualization, exposure and BTC regression\n\nCAGR and arithmetic annualized return are transformations of nine-month evidence, not twelve-month observations. BTC alpha/beta come from daily OLS with intercept and HAC(7) 95% intervals. Missing/undefined quantities remain missing, never zero.')
    code("annual_columns=[c for c in ['strategy_id','cagr','annual_return','alpha_annual','alpha_ci_low','alpha_ci_high','beta'] if c in selected]\nexposure_columns=[c for c in ['strategy_id','mean_gross_exposure','mean_net_exposure','fraction_flat','n_days','n_minutes','terminal_log_equity','equity_underflow_count'] if c in selected]\ndisplay(selected[annual_columns].round(6))\ndisplay(selected[exposure_columns].round(6))")
    md('### 8. Cost and one additional five-minute execution bar\n\nPrimary cost remains 20 bps even at a shorter time scale. Scenarios are assumptions, not uncertainty intervals. The five-bps total scenario is below the course\'s assumed seven-bps commission alone.')
    code("fig=plot_costs(d['experiments'],d['selection'])\nplt.show()\nlag=d['experiments'].loc[d['experiments'].split.eq('retrospective_2026')&d['experiments'].strategy_id.isin(ids)&d['experiments'].cost_bps.eq(20)]\ndisplay(lag[['strategy_id','execution_lag','total_return','sharpe','total_turnover']].sort_values(['strategy_id','execution_lag']).round(6))")
    md('### 9. Post-hoc historical zero-profit cost\n\nThis derivative calculation does not select or tune a strategy. It solves the compounded saved-path return equation for an all-in one-way cost threshold. It is historical, not a confidence interval or a future tradability promise. A threshold below the course commission alone cannot justify lowering primary costs.')
    code("derived=historical_break_even(d)\ndisplay(pd.DataFrame([{'strategy_id':k,'break_even_cost_bps':v['cost_bps']} for k,v in derived.items()]))\nassert abs(derived['reversal_m015_r060']['cost_bps']-0.33949153642324725)<1e-10\nassert derived['momentum_m015_r060']['cost_bps'] is None\nprint('Reversal break-even about 0.34 bps; momentum has no nonnegative threshold.')")
    md('### 10. Full-L1 turnover for all cases\n\nTurnover/day is total full-L1 change divided by 273 days, not trade count or gross exposure. Sum of interval costs reconciles to rate times turnover, but compounded gross/net total-return differences are not an additive cost waterfall.')
    code("fig=plot_turnover(d['experiments'])\nplt.show()\nall_2026=g.loc[g.split.eq('retrospective_2026')].copy()\nall_2026['turnover_per_day']=all_2026.total_turnover/273\ndisplay(all_2026[['strategy_id','gross_total_return','total_return','sharpe','turnover_per_day']].round(5))")
    md('## Takeaways\n\n'+'\n\n'.join('- '+x for x in conclusions(d))+'\n\nThe fixed survivor universe, theoretical shorts, absent financing/margin/capacity, idealized closes and omitted weight drift limit tradability. OHLCV is not bid/ask or order-book evidence. No live orders, publication, or scheduled monitoring.\n\n## Sources and reproduction\n\n- [Binance archives]('+SOURCE+')\n- [Binance dataset terms]('+TERMS+')\n- [Official 2023 incident]('+HALT+')\n- Course source: `/Users/cosdis/Downloads/quant_course/ClassProject.docx`\n\nBinance data and derived figures/results are attributed to Binance under the stated CC BY-NC-SA 4.0 non-commercial educational/personal non-production terms. Original and extended hourly projects/ZIPs remain unchanged.\n\nRegenerate cached artifacts: `python -m crypto_intraday_5m report`. Tests: `python -m pytest -q`. Use `/Users/cosdis/.venvs/myenv/bin/python`.')
    nb.cells=cells;nb.metadata={'kernelspec':{'display_name':'Python 3 (myenv)','language':'python','name':'python3'},'language_info':{'name':'python','version':sys.version.split()[0]}}
    nbformat.validate(nb);manager=KernelManager(kernel_name='python3');manager._kernel_spec=KernelSpec(argv=[sys.executable,'-m','ipykernel_launcher','-f','{connection_file}'],display_name='Python 3 (myenv)',language='python')
    executed=NotebookClient(nb,timeout=600,kernel_name='python3',km=manager,resources={'metadata':{'path':str(root)}},allow_errors=False).execute();nbformat.write(executed,path)
    body,_=HTMLExporter().from_notebook_node(executed);html.write_text(body);return path,html


def create_report(root:Path):
    root=Path(root);d=load_outputs(root);figures=make_figures(root,d);pdf=create_pdf(root,d,figures);notebook,html=create_notebook(root,d)
    paths={'pdf':str(pdf),'notebook':str(notebook),'html':str(html),**{'figure_'+k:v for k,v in figures.items()}}
    receipt={'artifact_paths':{k:str(Path(v).relative_to(root)) for k,v in paths.items()},'sha256':{k:sha256(v) for k,v in paths.items()},'reporting_source_sha256':sha256(__file__),'classification':'Entire pilot exploratory/retrospective; 2026 is not a new holdout.','execution':'Notebook executed top to bottom, selected primary holdings/accounting/daily metrics independently reconciled.','visual_inspection':'Pending complete final PDF-page, figure-output and HTML inspection.'}
    (root/'reports/artifact_verification.json').write_text(json.dumps(receipt,indent=2)+'\n');return receipt

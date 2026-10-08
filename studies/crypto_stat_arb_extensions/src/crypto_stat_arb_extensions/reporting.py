"""Portable report artifacts from frozen extension outputs, never live prices.

The plotting/notebook/report layer is deliberately outside the strategy freeze:
it cannot alter selection and never downloads data or runs the research runner.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import PercentFormatter
import numpy as np
import pandas as pd

INK = '#243441'
MUTED = '#5A6A76'
BLUE = '#245C85'
ORANGE = '#B7772B'
OLIVE = '#737642'
PINK = '#A56387'
GREY = '#738490'
SOURCE_URL = 'https://github.com/binance/binance-public-data'
TERMS_URL = SOURCE_URL + '/blob/master/TERMS_AND_CONDITIONS.md'
HALT_URL = 'https://www.binance.com/en/blog/from-our-ceo/6789340645608890113'
START = pd.Timestamp('2026-01-01', tz='UTC')
END = pd.Timestamp('2026-10-01', tz='UTC')
_REFERENCE_LABELS = {}
SYMBOLS = ['BTCUSDT','ETHUSDT','LTCUSDT','ADAUSDT','LINKUSDT','DOGEUSDT','DOTUSDT','SOLUSDT']


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _json(path):
    return json.loads(Path(path).read_text())


def fmt(value, percent=False, digits=2):
    try:
        value = float(value)
        if not math.isfinite(value):
            return 'N/A'
        return f'{value:.{digits}%}' if percent else f'{value:.{digits}f}'
    except (TypeError, ValueError):
        return 'N/A'


def _col(df, *names):
    return next((n for n in names if n in df.columns), None)


def metric(row, name):
    aliases = {'total_return':['total_return','net_total_return'],
        'annual_return':['annual_return','annual_arithmetic_return'],
        'volatility':['volatility','annual_volatility'],
        'alpha':['alpha','alpha_annual'], 'beta':['beta','btc_beta'],
        'turnover':['total_turnover','turnover'],
        'gross_exposure':['mean_gross_exposure','gross_exposure_mean'],
        'net_exposure':['mean_net_exposure','net_exposure_mean'],
        'cash':['mean_cash_allocation','cash_participation','mean_cash_participation'],
        'alpha_low':['alpha_ci_low','alpha_ci_lower'],
        'alpha_high':['alpha_ci_high','alpha_ci_upper']}
    return next((row[c] for c in aliases.get(name,[name]) if c in row and pd.notna(row[c])), np.nan)


def label(identifier):
    """Bounded labels; the identifier table retains full canonical names."""
    s = str(identifier)
    if s in _REFERENCE_LABELS: return _REFERENCE_LABELS[s]
    if 'factor' in s or 'residual' in s:
        return 'BTC-factor reversal'
    days = re.search(r'(?:h|L|lookback[_-]?)(\d+)', s, re.I)
    if days:
        hours=int(days.group(1))
        days = f'{hours/24:g}d' if hours>=24 else f'{hours}h'
    else:
        days = ''
    freq = 'weekly' if any(t in s.lower() for t in ['r168','weekly','_w','r_168']) else 'daily'
    if 'cash' in s.lower():
        out = f'Trend long/cash {days} {freq}'
    elif any(t in s.lower() for t in ['long_short','longshort','trend_ls','ts_ls']):
        out = f'Trend long/short {days} {freq}'
    elif 'momentum' in s.lower() or 'cs_mom' in s.lower():
        out = f'CS momentum {days} {freq}'
    elif 'reversal' in s.lower():
        out = f'CS reversal {days} {freq}'
    else:
        out = s.replace('_',' ')
    if any(t in s.lower() for t in ['b025','b0.25','buffer_on','buffered']) and not any(t in s.lower() for t in ['unbuffered','b0250']):
        out += ' + buffer'
    return out.strip()


def family(identifier):
    s=str(identifier).lower()
    if 'factor' in s or 'residual' in s: return 'factor'
    if 'cash' in s: return 'cash'
    if any(t in s for t in ['long_short','longshort','trend_ls','ts_ls']): return 'longshort'
    if 'reversal' in s: return 'reversal'
    return 'momentum'


def color(identifier):
    return {'cash':ORANGE,'longshort':OLIVE,'factor':PINK,'reversal':GREY,'momentum':BLUE}[family(identifier)]


def primary(df):
    out=df.copy()
    if 'cost_bps' in out: out=out.loc[out.cost_bps.eq(20)]
    if 'execution_lag' in out: out=out.loc[out.execution_lag.eq(1)]
    return out


def _style():
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,
        'axes.titlesize':12,'axes.titleweight':'bold','axes.labelsize':10,
        'axes.spines.top':False,'axes.spines.right':False,'text.color':INK,
        'axes.labelcolor':INK,'xtick.color':MUTED,'ytick.color':MUTED,
        'axes.edgecolor':'#A7B3BA','axes.facecolor':'white','figure.facecolor':'white',
        'grid.color':'#E3E8EB','grid.linewidth':.6,'savefig.facecolor':'white'})


def _save(fig,path):
    fig.savefig(path,dpi=185,bbox_inches='tight'); plt.close(fig)
    return str(path)


def verify_frozen_inputs(root:Path) -> dict:
    """Fail closed before opening any output carrying holdout prices/returns."""
    root=Path(root)
    receipt=_json(root/'outputs/freeze_receipt.json')
    selection=root/'outputs/selection.json'
    expected=receipt.get('selection_sha256')
    if expected and sha256(selection)!=expected:
        raise ValueError('Selection differs from its pre-holdout frozen receipt')
    from .core import verify_freeze
    verify_freeze(root)
    for path, digest in receipt.get('analysis_hashes',receipt.get('analysis_source_sha256',{})).items():
        p=Path(path)
        p=p if p.is_absolute() else root/p
        if sha256(p)!=digest:
            raise ValueError(f'Analysis source differs from its frozen receipt: {path}')
    stamp=receipt.get('frozen_at_utc',receipt.get('frozen_at'))
    if stamp is None: raise ValueError('Freeze receipt has no UTC timestamp')
    freeze=pd.Timestamp(stamp)
    access_file=root/'outputs/holdout_access_receipt.json'
    if access_file.exists():
        access=_json(access_file)
    else:
        manifest=_json(root/'outputs/run_manifest.json')
        access=manifest.get('holdout_access',manifest.get('holdout_access_receipt',{}))
    access_stamp=access.get('first_access_utc',access.get('first_access_at_utc'))
    if access_stamp is None: raise ValueError('No independently recorded first holdout access timestamp')
    if freeze>=pd.Timestamp(access_stamp):
        raise ValueError('Freeze did not precede holdout access')
    return {'freeze_at_utc':str(freeze),'first_holdout_access_utc':str(pd.Timestamp(access_stamp)),
        'selection_sha256':sha256(selection),'freeze_receipt_sha256':sha256(root/'outputs/freeze_receipt.json')}


def load_outputs(root:Path) -> dict:
    root=Path(root)
    chronology=verify_frozen_inputs(root)
    d={'root':root,'chronology':chronology,'selection':_json(root/'outputs/selection.json'),
       'manifest':_json(root/'outputs/run_manifest.json')}
    if d['manifest'].get('status')!='complete':
        raise ValueError('Artifacts require a complete holdout; do not invent or shorten evaluation')
    for relative,digest in d['manifest'].get('analysis_output_sha256',{}).items():
        if sha256(root/relative)!=digest:
            raise ValueError(f'Locked research output differs from its run receipt: {relative}')
    for spec in d['selection'].get('evaluated_strategies',[]):
        if spec.get('role') in ['original_reference','time_scale_reference']:
            horizon=spec['lookback_h']; horizon=f'{horizon/24:g}d' if horizon>=24 else f'{horizon}h'
            cadence='weekly' if spec['rebalance_h']==168 else 'daily' if spec['rebalance_h']==24 else str(spec['rebalance_h'])+'h'
            prefix='Original' if spec['role']=='original_reference' else 'Scale'
            _REFERENCE_LABELS[spec['strategy_id']]=f'{prefix} {spec["family"]} {horizon}/{cadence}'
    for name in ['historical_metrics','holdout_metrics','ic_daily','ic_summary',
                 'regime_observations','regime_summary','factor_models','factor_events','annual_metrics']:
        path=root/'outputs'/f'{name}.csv'
        try: d[name]=pd.read_csv(path)
        except pd.errors.EmptyDataError: d[name]=pd.DataFrame()
        if 'annual_volatility' in d[name] and 'volatility' not in d[name]:
            d[name]['volatility']=d[name]['annual_volatility']
        if 'alpha_annual' in d[name] and 'alpha' not in d[name]:
            d[name]['alpha']=d[name]['alpha_annual']
        if 'regime_feature' in d[name] and 'feature' not in d[name]:
            d[name]['feature']=d[name]['regime_feature']
    d['returns']=pd.read_parquet(root/'outputs/selected_returns.parquet')
    d['returns']['bar_end']=pd.to_datetime(d['returns']['bar_end'],utc=True)
    weights=root/'outputs/selected_weights.parquet'
    d['weights']=pd.read_parquet(weights) if weights.exists() else None
    if d['weights'] is not None:
        d['weights']['bar_end']=pd.to_datetime(d['weights']['bar_end'],utc=True)
    return d


def plot_ic(summary:pd.DataFrame, splits=None):
    """Observed mean IC with multiplicity marker; intervals remain in CSV/NB."""
    _style()
    splitcol=_col(summary,'split','period')
    splits=list(summary[splitcol].drop_duplicates()) if splits is None else list(splits)
    summary=summary.rename(columns={'forward_horizon_h':'forward_h'})
    mean=_col(summary,'mean_ic','ic_mean','mean')
    pcol=_col(summary,'p_holm','p_value_holm','holm_p','adjusted_p')
    rows=math.ceil(len(splits)/2)
    fig,axes=plt.subplots(rows,2,figsize=(10,rows*3.8),layout='constrained',squeeze=False)
    bound=max(.05,float(summary[mean].abs().max()))
    for ax,split in zip(axes.flat,splits):
        g=summary.loc[summary[splitcol].eq(split)]
        mat=g.pivot(index='lookback_h',columns='forward_h',values=mean).sort_index()
        im=ax.imshow(mat.to_numpy(),cmap='RdBu',vmin=-bound,vmax=bound,aspect='auto')
        ax.set_xticks(range(len(mat.columns)),[f'{int(x)}h' for x in mat.columns])
        ax.set_yticks(range(len(mat.index)),[f'{int(x)}h' for x in mat.index])
        ax.set(title={'development':'Development 2022-2023','validation':'Selection 2024','retrospective':'Retrospective 2025','holdout':'Holdout Jan-Sep 2026'}.get(str(split),str(split).replace('_',' ').title()),xlabel='Forward return horizon',ylabel='Trailing lookback')
        for i,L in enumerate(mat.index):
            for j,F in enumerate(mat.columns):
                v=mat.loc[L,F]; r=g.loc[g.lookback_h.eq(L)&g.forward_h.eq(F)].iloc[0]
                star='*' if pcol and pd.notna(r[pcol]) and r[pcol]<.05 else ''
                ax.text(j,i,f'{v:+.2f}{star}' if pd.notna(v) else 'N/A',ha='center',va='center',
                        fontsize=9,color='white' if pd.notna(v) and abs(v)>bound*.55 else INK)
    for ax in list(axes.flat)[len(splits):]: ax.remove()
    fig.colorbar(im,ax=list(axes.flat)[:len(splits)],label='Mean cross-sectional Spearman IC',shrink=.85)
    return fig


def plot_screening(historical:pd.DataFrame):
    _style(); val=primary(historical)
    val=val.loc[val.split.eq('validation')].sort_values(['sharpe','strategy_id'],na_position='first')
    fig,ax=plt.subplots(figsize=(9,6.2),layout='constrained')
    finite=val.sharpe.notna()
    names=[label(x) for x in val.strategy_id]
    ax.barh(np.arange(len(val))[finite],val.loc[finite,'sharpe'],height=.68,
            color=[color(x) for x in val.loc[finite,'strategy_id']])
    for j,(_,r) in enumerate(val.iterrows()):
        if pd.isna(r.sharpe): ax.text(.04,j,'N/A (flat / undefined)',va='center',fontsize=8)
    ax.set_yticks(np.arange(len(val)),names)
    ax.axvline(0,color=INK,lw=.8);ax.grid(axis='x');ax.set_axisbelow(True)
    ax.set(title='2024 selection: all 17 predeclared extension models',
           xlabel='Daily-return Sharpe at 20 bps, one-hour execution lag')
    return fig


def _holdout_returns(d):
    out=primary(d['returns'])
    return out.loc[out.bar_end.gt(START)&out.bar_end.le(END)]


def _group_ids(ids):
    groups=[[],[],[],[]]
    for s in ids:
        f=family(s)
        j={'momentum':0,'cash':1,'longshort':1,'reversal':2,'factor':3}[f]
        groups[j].append(s)
    return groups


def plot_equity(returns:pd.DataFrame):
    _style()
    ret=primary(returns); ret=ret.loc[ret.bar_end.gt(START)&ret.bar_end.le(END)]
    ids=list(ret.strategy_id.drop_duplicates())
    fig,axes=plt.subplots(2,2,figsize=(10,7.0),layout='constrained',sharex=True,sharey=True)
    for ax,group,title in zip(axes.flat,_group_ids(ids),['Cross-sectional momentum','Time-series trend following','Cross-sectional reversal','BTC-factor residual reversal']):
        for j,s in enumerate(group):
            g=ret.loc[ret.strategy_id.eq(s)].sort_values('bar_end')
            eq=np.r_[1,(1+g.net_return).cumprod().to_numpy()]
            dates=pd.DatetimeIndex([START]).append(pd.DatetimeIndex(g.bar_end))
            ax.plot(dates,eq,color=color(s),ls=['-','--',':','-.'][j%4],lw=1.6,label=label(s))
        ax.axhline(1,color=INK,lw=.7);ax.grid();ax.set_axisbelow(True)
        ax.set(title=title,ylabel='Net equity (January 1 = 1)')
        if group: ax.legend(frameon=False,fontsize=8,loc='best')
        else: ax.text(.5,.5,'No model in this group',transform=ax.transAxes,ha='center')
        ax.set_xticks([START,pd.Timestamp('2026-04-01',tz='UTC'),pd.Timestamp('2026-07-01',tz='UTC'),END])
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
    return fig


def plot_costs(metrics:pd.DataFrame):
    _style(); m=metrics.loc[metrics.execution_lag.eq(1)]
    ids=list(m.strategy_id.drop_duplicates())
    fig,axes=plt.subplots(2,2,figsize=(10,6),layout='constrained',sharex=True,sharey=True)
    for ax,group,title in zip(axes.flat,_group_ids(ids),['Cross-sectional momentum','Trend following','Cross-sectional reversal','BTC-factor reversal']):
        for j,s in enumerate(group):
            g=m.loc[m.strategy_id.eq(s)].sort_values('cost_bps')
            ax.plot(g.cost_bps,g.total_return,color=color(s),ls=['-','--',':','-.'][j%4],marker='o',markersize=4,label=label(s))
        ax.axhline(0,color=INK,lw=.7);ax.set(title=title,xlabel='All-in one-way cost (bps)',ylabel='Nine-month total return')
        ax.set_xticks([0,5,10,15,20,40]);ax.yaxis.set_major_formatter(PercentFormatter(1));ax.grid();ax.set_axisbelow(True)
        if group:ax.legend(frameon=False,fontsize=8)
    return fig


def plot_stability(annual:pd.DataFrame):
    _style();g=primary(annual)
    mat=g.pivot(index='strategy_id',columns='year',values='total_return')
    fig,ax=plt.subplots(figsize=(10,4.6),layout='constrained')
    bound=max(.05,float(np.nanmax(np.abs(mat.to_numpy()))))
    im=ax.imshow(mat.to_numpy(),cmap='RdBu',vmin=-bound,vmax=bound,aspect='auto')
    ax.set_xticks(range(len(mat.columns)),[str(x) for x in mat.columns])
    ax.set_yticks(range(len(mat.index)),[label(s) for s in mat.index])
    for i in range(len(mat)):
        for j in range(len(mat.columns)):
            v=mat.iloc[i,j]
            ax.text(j,i,fmt(v,True,1),ha='center',va='center',fontsize=10,
                    color='white' if abs(v)>bound*.55 else INK)
    ax.set(title='Frozen models: retrospective yearly net returns at 20 bps',xlabel='Calendar year (independent cash resets)')
    fig.colorbar(im,ax=ax,label='Total yearly net return',format=PercentFormatter(1),shrink=.9)
    return fig


def plot_factor(models:pd.DataFrame,events:pd.DataFrame):
    _style(); datecol=_col(models,'refit_date','refit_time','month','decision_time','refit_at')
    g=models.copy();g['year']=pd.to_datetime(g[datecol],utc=True).dt.year
    g=g.loc[g.year.ge(2022)&pd.to_datetime(g[datecol],utc=True).lt(END)]
    eligible=_col(g,'eligible','is_eligible')
    if g[eligible].dtype==object:g[eligible]=g[eligible].astype(str).str.lower().isin(['true','1'])
    counts=g.groupby('year')[eligible].agg(['sum','count'])
    fig=plt.figure(figsize=(9,3.9),layout='constrained')
    grid=fig.add_gridspec(2,2,height_ratios=[1,.14])
    axes=np.array([fig.add_subplot(grid[0,0]),fig.add_subplot(grid[0,1])])
    legend_ax=fig.add_subplot(grid[1,:]);legend_ax.axis('off')
    axes[0].bar([str(x) for x in counts.index],counts['sum'],color=PINK,label='Eligible coin-months')
    axes[0].bar([str(x) for x in counts.index],counts['count']-counts['sum'],bottom=counts['sum'],color='#E5D3DF',edgecolor=PINK,hatch='//',label='Ineligible coin-months')
    axes[0].set(title='Stationarity and half-life eligibility',xlabel='Calendar year (2026: Jan-Sep)',ylabel='Coin-months')
    legend_ax.legend(*axes[0].get_legend_handles_labels(),loc='center',ncol=2,frameon=False,fontsize=9)
    e=events.copy();eventcol=_col(e,'event','event_type','action');timecol=_col(e,'decision_time','timestamp','bar_end','time','date')
    if not e.empty and eventcol and timecol:
        e=e.loc[pd.to_datetime(e[timecol],utc=True).lt(END)].copy()
        e['year']=pd.to_datetime(e[timecol],utc=True).dt.year
        enters=e.loc[e[eventcol].astype(str).str.lower().eq('entry')].groupby('year').size().reindex(counts.index,fill_value=0)
        axes[1].bar([str(x) for x in enters.index],enters,color=PINK)
    else:
        axes[1].text(.5,.5,'No entry events',ha='center',transform=axes[1].transAxes)
    axes[1].set(title='Actual spread entries',xlabel='Calendar year (2026: Jan-Sep)',ylabel='Entry events')
    for ax in axes:ax.grid(axis='y');ax.set_axisbelow(True)
    return fig


def plot_regimes(summary:pd.DataFrame):
    _style();g=summary.copy()
    splitcol=_col(g,'split','period');g=g.loc[g[splitcol].eq('holdout')]
    regimecol=_col(g,'feature','regime_feature')
    g=g.drop_duplicates(['strategy_id',regimecol])
    diff=_col(g,'high_minus_low_net_return','difference_high_minus_low','high_minus_low','mean_difference','contrast','difference')
    lo=_col(g,'ci_low','difference_ci_low','contrast_ci_low');hi=_col(g,'ci_high','difference_ci_high','contrast_ci_high')
    regs=list(g[regimecol].drop_duplicates())
    fig,axes=plt.subplots(1,len(regs),figsize=(10.0,5.4),layout='constrained',squeeze=False,sharey=True,sharex=True)
    ids=list(g.strategy_id.drop_duplicates())
    for ax,reg in zip(axes.flat,regs):
        sub=g.loc[g[regimecol].eq(reg)].set_index('strategy_id').reindex(ids)
        y=np.arange(len(ids));v=sub[diff].to_numpy()*1e4
        ax.scatter(v,y,color=BLUE,s=28,zorder=3)
        if lo and hi:
            for j,(_,r) in enumerate(sub.iterrows()):
                if pd.notna(r[lo]) and pd.notna(r[hi]): ax.hlines(j,r[lo]*1e4,r[hi]*1e4,color=BLUE,lw=1.4)
        ax.axvline(0,color=INK,lw=.7);ax.grid(axis='x');ax.set_axisbelow(True)
        ax.set(title={'relative_quote_volume':'Relative volume','btc_volatility_30d':'BTC volatility','return_dispersion_24h':'Return dispersion'}.get(reg,str(reg).replace('_',' ').title()),xlabel='High - low mean daily\nnet return (bps)')
        ax.set_yticks(y,[label(s) for s in ids]);ax.invert_yaxis()
    return fig


def make_figures(root:Path,results=None) -> dict:
    root=Path(root);d=load_outputs(root) if results is None else results
    folder=root/'reports/figures';folder.mkdir(parents=True,exist_ok=True)
    figures={}
    charts=[('ic',plot_ic(d['ic_summary'])),('screening',plot_screening(d['historical_metrics'])),
            ('equity',plot_equity(d['returns'])),('costs',plot_costs(d['holdout_metrics'])),
            ('factor',plot_factor(d['factor_models'],d['factor_events'])),
            ('stability',plot_stability(d['annual_metrics'])),
            ('regimes',plot_regimes(d['regime_summary']))]
    for name,fig in charts:figures[name]=_save(fig,folder/f'{name}.png')
    return figures


def findings(d):
    p=primary(d['holdout_metrics']).sort_values(['total_return','strategy_id'],ascending=[False,True])
    positive=int((p.total_return>0).sum());defined=int(p.sharpe.notna().sum())
    best=p.iloc[0];worst=p.iloc[-1]
    champion_ids=[x['strategy_id'] for x in d['selection']['champions']]
    champions=p.loc[p.strategy_id.isin(champion_ids)]
    lines=[f'{positive} of {len(p)} frozen evaluations had positive 20 bps net returns during January-September 2026. The three 2024-selected extension champions all had negative net returns: '+', '.join(label(r.strategy_id)+' '+fmt(r.total_return,True) for _,r in champions.iterrows())+'.',
      f'{label(best.strategy_id)} had the highest observed net return, {fmt(best.total_return,True)}, with Sharpe {fmt(best.sharpe)}. This is a preserved reference-model result, not a post-holdout selection.']
    factor=p.loc[p.strategy_id.eq('factor_residual_fixed')]
    if len(factor):
        events=d['factor_events'];entries=events.loc[events.event.eq('entry')&pd.to_datetime(events.decision_time,utc=True).ge(START)&pd.to_datetime(events.decision_time,utc=True).lt(END)]
        lines.append(f'Fixed BTC-factor reversal returned {fmt(factor.iloc[0].total_return,True)} net from only {len(entries)} spread entries. Sparse activity does not establish a persistent profitable edge.')
    summary=d['ic_summary'];pcol=_col(summary,'p_holm','p_value_holm','holm_p','adjusted_p')
    if pcol:
        hs=summary.loc[summary.split.eq('holdout')]; n=int((hs[pcol]<.05).sum())
        lines.append(f'{n} of 24 holdout signal comparisons passed the within-period Holm 5% threshold. Correlations are diagnostic, not independent strategy profits.')
    return lines


def create_pdf(root:Path,d,figures) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle,getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image,PageBreak
    from PIL import Image as PILImage
    root=Path(root);path=root/'reports/expanded_research_report.pdf';W,H=A4;usable=W-90
    st=getSampleStyleSheet()
    for name,size,leading,weight in [('Cover',25,29,'Helvetica-Bold'),('Section',16,20,'Helvetica-Bold'),('Sub',10.5,14,'Helvetica-Bold'),('Body',9.4,13.5,'Helvetica'),('Small',8,11,'Helvetica'),('Cell',7.8,10.4,'Helvetica')]:
        st.add(ParagraphStyle(name='Ext'+name,fontName=weight,fontSize=size,leading=leading,textColor=colors.HexColor(MUTED if name=='Small' else INK),spaceAfter=8 if name!='Cell' else 0))
    story=[]
    def para(s,sty='Body'):return Paragraph(s,st['Ext'+sty])
    def add(s,sty='Body'):story.append(para(s,sty))
    def page(n,title):
        if story:story.append(PageBreak())
        add(f'{n:02d} / {title}','Section')
    def table(rows,widths=None):
        t=Table([[para(escape(str(x)),'Cell') for x in r] for r in rows],colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E9EFF3')),('LINEBELOW',(0,0),(-1,0),.7,colors.HexColor('#B7C6D0')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F6F8FA')])]))
        story.append(t);story.append(Spacer(1,9))
    def img(name,cap):
        with PILImage.open(figures[name]) as im:w,h=im.size
        height=min(cap,usable*h/w);width=height*w/h
        story.append(Image(figures[name],width=width,height=height,hAlign='LEFT'));story.append(Spacer(1,8))
    add('EXPANDED CRYPTO<br/>STRATEGY RESEARCH','Cover')
    add('Signals, lower-turnover momentum, trend following, and BTC-factor reversal','Sub')
    add('Supplement to the original course project | Historical research through September 30, 2026','Small')
    add('Executive summary','Sub')
    for line in findings(d):add(escape(line))
    table([['Research extension','What it examines'],['Signal diagnostics','24 lookback/forward-horizon combinations; daily cross-sectional ranks'],['Lower-turnover momentum','14/28-day lookbacks; daily/weekly schedules; whole-target no-trade buffer'],['Time-series trend following','Own-coin trends; separately evaluated long/cash and long/short'],['BTC-factor reversal','Monthly past-data fit; stationarity/half-life gates; aggregate BTC hedge'],['Regimes','Volume, volatility, dispersion; descriptive following-day contrasts only']],[usable*.32,usable*.68])
    add('Interpretation','Sub');add('The three tuned champions were selected using 2024 only. Four historical reference selections and one fixed residual model complete the eight-model comparison. The nine-month 2026 period was new to this analysis and was accessed only after the freeze. It is a historical holdout, not prospective live evidence. Earlier periods and the inspected 2025 year are explicitly exploratory or retrospective.')
    add('Educational unconstrained backtests, not a recommendation to trade. A fixed survivor universe, idealized execution, and excluded short financing limit generalization. Original artifacts remain unchanged.','Small')

    page(2,'Data, chronology, and accounting')
    table([['Partition','Dates','Use'],['Warm-up','Oct-Dec 2021','Trailing signals and residual formation only'],['Development','2022-2023','Design, implementation, regime medians'],['Selection','2024','Highest net Sharpe at 20 bps within each tuned family'],['Retrospective','2025','Robustness; already inspected, not untouched'],['Historical holdout','Jan 1-Sep 30, 2026','273 days / 6,552 elapsed hours; no reselection']],[usable*.22,usable*.26,usable*.52])
    add('Point-in-time safeguards','Sub');add('Freeze receipt pins candidate IDs, analysis code, model rules, development-only thresholds, and selections. Higher 2024 net daily Sharpe wins; ties use lower full-L1 turnover, then canonical identifier. Defined negative winners remain research controls. Monthly residual refits are predeclared past-data operations, not tuning on holdout outcomes.')
    table([['Audit event','UTC timestamp'],['Selection / analysis freeze',d['chronology']['freeze_at_utc']],['First recorded holdout access',d['chronology']['first_holdout_access_utc']]],[usable*.39,usable*.61])
    add('Return and cost definitions','Sub');add('The existing tested simulator is reused without changing its public API. Signals on completed UTC endpoints earn subsequent intervals with lag one hour; lag two is a stress. Net return equals weighted asset return minus cost, where cost = (bps / 10,000) x sum of absolute executed weight changes. Initial cash entry and terminal liquidation are charged. BTC hedges are aggregated before turnover, so offsetting virtual hedge legs are not double-charged.')
    add('Daily compounded returns use 365-day annualization and zero risk-free rate. Total return is the actual nine-month compounded return; CAGR is an annualized transformation, not a twelve-month observation. Daily OLS against BTC includes an intercept; alpha and its HAC(7) 95% interval are annualized, beta is dimensionless. Maximum drawdown uses observed-endpoint equity including initial unit capital.')
    add('Data quality','Sub')
    audit=d['manifest']['holdout_data_quality']
    add(f'Full cache: {audit["archive_count"]} checksum-verified monthly archives, {audit["rows"]:,} observed of {audit["expected_rows"]:,} expected asset-hour rows; {audit["duplicate_count"]} duplicates. All {audit["missing_count"]} missing asset-hours belong to the documented 2023 halt; the 2026 holdout has no missing hours. Status: pass with documented exceptions, not an exception-free clean pass.','Small')
    add('Hourly Binance public spot archives are checksum-verified, cached, and normalized. The original documented March 24, 2023 suspension is preserved: hold invested positions across the 11:00-15:00 UTC observed interval; no fabricated interim prices, executions, or preemptive cash-out. Unknown gaps, missing archives, or failed checksums stop evaluation. Dataset receipts contain metadata repairs and all documented exceptions. No intrahalt drawdown can be reconstructed.','Small')
    add('Course approximation: target-change turnover omits ordinary weight drift. Spot short positions are theoretical; borrowing, funding, financing, collateral/margin, capacity, and reliable close fills are not modeled. USDT is the quote numeraire.','Small')

    page(3,'Do ranks predict later relative returns?')
    img('ic',420)
    add('Daily signals at 00:00 UTC compare cross-sectional past-return ranks with later return ranks across the same eight coins. Positive mean Spearman IC supports momentum; negative supports reversal. Constant or missing cross-sections, suspended endpoints, and forward labels crossing a partition boundary are excluded. The complete daily and summary records remain inspectable.')
    add('Uncertainty and multiplicity','Sub');add('Mean-IC 95% intervals use 4,000 seeded, 28-day block-bootstrap replicates. Resampling retains within-block serial structure; intervals and p-values are nominal under this declared block scheme, not guaranteed for all dependence. A star marks a Holm-adjusted p-value below 5% across the 24 comparisons within that period. The color scale is shared across panels. Unstarred cells are not established effects; statistically detectable IC is not an execution-cost-adjusted trading profit.')
    significant=d['ic_summary'].loc[d['ic_summary'].split.eq('holdout')&d['ic_summary'].p_holm.lt(.05)]
    if len(significant):
        detail='; '.join(str(int(r.lookback_h))+'h lookback / '+str(int(r.forward_horizon_h))+'h forward: mean IC '+fmt(r.mean_ic,False,4)+', Holm p '+fmt(r.p_holm,False,4) for _,r in significant.iterrows())
        add('The holdout passing comparison is '+escape(detail)+'. The adjusted p-value is borderline at 5% and has finite 4,000-replicate Monte Carlo precision. This nominal-bootstrap result is not a cost-aware trading strategy.','Small')
    add('All confidence intervals, counts, raw and corrected p-values are retained in outputs/ic_summary.csv and displayed in the notebook. This diagnostic does not select a new 2026 trading horizon.','Small')

    page(4,'Historical screening and frozen champions')
    img('screening',385)
    add('Grid and behavior','Sub');add('Eight cross-sectional configurations combine 14/28-day lookbacks, daily/Monday-weekly schedules, and buffer off/on. The buffer skips the entire decision only when proposed full-L1 target change is below 0.25; otherwise it executes the complete target. Eight time-series configurations use the same lookbacks/schedules for long/cash and long/short. Each coin receives 1/8 when active; inactive allocations are not redistributed.')
    add('The fixed residual model is not selected from a hyperparameter grid. Four unbuffered cross-sectional configurations were already examined in the 156-configuration time-scale scan: matching them here is a control comparison, not a new discovery. Historical and failed candidates remain in the CSV.','Small')
    val=primary(d['historical_metrics']);val=val.loc[val.split.eq('validation')]
    # Keep exact selection IDs visible even when summaries use short labels.
    champions=d['selection'].get('champions',{})
    ids=[]
    if isinstance(champions,dict):
        for x in champions.values():ids.append(x.get('strategy_id',x.get('id')) if isinstance(x,dict) else x)
    elif isinstance(champions,list):ids=[x.get('strategy_id') if isinstance(x,dict) else x for x in champions]
    rows=[['2024-selected champion','Net total return','Sharpe','Turnover']]
    for s in ids:
        r=val.loc[val.strategy_id.eq(s)]
        if len(r):r=r.iloc[0];rows.append([label(s),fmt(r.total_return,True),fmt(r.sharpe),fmt(metric(r,'turnover'),False,1)])
    if len(rows)>1:table(rows,[usable*.45,usable*.20,usable*.15,usable*.20])

    page(5,'Earlier years are retrospective evidence')
    img('stability',280)
    add('Identical choices, matched accounting','Sub');add('Each row is a frozen champion, fixed residual model, or original/time-scale reference selection. Annual calculations start from cash and liquidate at each year end, charging both transitions. These calculations use the same selected strategy across years, not a newly chosen winner for each year.')
    add('2022-2023 is development evidence; 2024 determines the three tuned champions; 2025 is retrospective robustness because the earlier project and time-scale scan already exposed that year. In particular, favorable 2025 returns here cannot be called untouched validation or used to justify reselection after the fact.')
    add('What this view can establish','Sub');add('Year-by-year differences expose path sensitivity and how one selected formulation behaved in different observed markets. They do not establish a market-regime mechanism, prospective profitability, or a representative point-in-time investment universe. The full annual-metric CSV includes all required metrics and independent cash-reset flags.','Small')

    page(6,'Nine-month historical holdout results')
    img('equity',340)
    p=primary(d['holdout_metrics']).sort_values('strategy_id')
    rows=[['Frozen model','Gross return','Net return','Volatility','Sharpe','Max DD']]
    for _,r in p.iterrows():rows.append([label(r.strategy_id),fmt(r.get('gross_total_return'),True),fmt(r.total_return,True),fmt(r.volatility,True),fmt(r.sharpe),fmt(r.max_drawdown,True)])
    table(rows,[usable*.33,usable*.14,usable*.14,usable*.14,usable*.11,usable*.14])
    add('January 1-September 30, 2026, primary 20 bps / lag one hour. Total returns are compounded over 273 days; volatility and Sharpe use daily returns and 365-day annualization. Drawdown is the maximum observed-endpoint loss magnitude. Curves share the same equity axis and begin at one. Line style distinguishes controls within the same family. N/A is undefined, never zero.','Small')
    add('These eight paths are evaluations of previously frozen choices, not an invitation to select whichever worked best in 2026. A favorable historical outcome still needs prospective confirmation and realistic short/execution feasibility.','Small')

    page(7,'Costs, execution timing, and exposure')
    img('costs',310)
    add('Cost scenarios reuse identical signals and positions. Zero bps isolates gross behavior; 5 bps is below the course-assumed 7 bps commission alone. Cost/timing scenarios are model stresses, not confidence intervals. No 2026 selection or parameter rescue is performed.','Small')
    lag=d['holdout_metrics'].loc[d['holdout_metrics'].cost_bps.eq(20)].copy()
    rows=[['Frozen model','Net lag 1','Net lag 2','Mean gross','Mean net','BTC beta']]
    for _,r in p.iterrows():
        rr=lag.loc[lag.strategy_id.eq(r.strategy_id)&lag.execution_lag.eq(2)]
        rows.append([label(r.strategy_id),fmt(r.total_return,True),fmt(rr.iloc[0].total_return if len(rr) else np.nan,True),fmt(metric(r,'gross_exposure')),fmt(metric(r,'net_exposure')),fmt(metric(r,'beta'))])
    table(rows,[usable*.33,usable*.14,usable*.14,usable*.13,usable*.13,usable*.13])
    cash_row=p.loc[p.strategy_id.astype(str).str.contains('long_cash')]
    if len(cash_row):
        add('Selected long/cash mean uninvested allocation: '+fmt(cash_row.iloc[0].get('mean_unused_gross_budget'),True)+'. This cash share is not redistributed to other coins.','Small')
    add('Long/cash retains inactive cash and may have variable directional exposure. Long/short trend following is not necessarily dollar-neutral. Factor reversal allocates each spread including its hedge, but aggregated exposure can be below one; estimated factor hedging does not guarantee realized neutrality. The notebook records cash participation, CAGR, annual arithmetic return, turnover, and alpha with HAC intervals.','Small')

    page(8,'Annualized metrics and factor exposure')
    rows=[['Frozen model','CAGR','Arithmetic annual','Turnover','Annual alpha','Alpha 95% HAC interval']]
    for _,r in p.iterrows():
        rows.append([label(r.strategy_id),fmt(r.get('cagr'),True),fmt(metric(r,'annual_return'),True),fmt(metric(r,'turnover'),False,1),fmt(metric(r,'alpha'),True),fmt(metric(r,'alpha_low'),True)+' to '+fmt(metric(r,'alpha_high'),True)])
    table(rows,[usable*.30,usable*.12,usable*.14,usable*.12,usable*.12,usable*.20])
    add('These quantities have different meanings','Sub');add('CAGR extrapolates the nine-month compounded return to an annualized rate; it is not a realized twelve-month return. Arithmetic annual return is daily mean x 365. Turnover is total traded notional per unit of target capital over the actual nine-month interval, including entry and liquidation, not annualized or halved.')
    add('Alpha is the intercept from daily OLS net portfolio return against same-day BTC return, multiplied by 365. Its 95% interval uses HAC standard errors with seven daily lags and is annualized consistently. Beta is the regression slope, not a target hedge weight. Dollar neutrality does not establish zero realized beta; long/cash and own-trend long/short can carry market exposure.')
    add('Undefined quantities','Sub');add('N/A denotes an undefined or unavailable estimate. A truly all-cash path has zero return, volatility, and turnover, but its Sharpe is undefined rather than zero. Constant portfolio returns can also leave some fitted uncertainty degenerate. No undefined metric is silently replaced by a favorable score.')
    add('Model identities','Sub')
    identities=d['selection'].get('evaluated_strategies',[])
    if identities:
        table([['Canonical identifier','Frozen role']]+[[x['strategy_id'],str(x.get('role','evaluation')).replace('_',' ')] for x in identities],[usable*.68,usable*.32])
    add('The original momentum/reversal and time-scale controls retain their original selected horizons/cadences. Reference calculations here use the same holdout calendar and cost convention as champions; they are not new discoveries or fresh 2026 selections.','Small')

    page(9,'BTC-factor residual reversal')
    img('factor',225)
    add('Formation and eligibility','Sub');add('At each month start, fit using 90 daily observations ending 24 hours earlier. Estimate return beta on the earliest 30 observations; calibrate the fixed-beta log-price spread on the subsequent 60 endpoints. Require beta in [0.1, 5], positive spread variance, Holm-adjusted ADF significance at 5% across seven coins, and AR(1) half-life between one and 20 days. Ineligible coin-months remain cash; parameters are frozen within the trading month.')
    add('Trading state machine','Sub');add('Enter toward the fitted mean only when 2 <= |z| < 4. Exit after crossing the signed 0.5 boundary, reaching an adverse signed 4 stop, or holding 20 calendar days. No same-day reentry. Force cash and refit on the first day of every month; allow entries from the following day. Each non-BTC coin spread receives at most 1/7 capital including its beta-weighted BTC hedge. Aggregate all BTC legs before cost accounting.')
    add('How to interpret inactivity','Sub');add('A valid all-cash or sparse result means this predeclared model did not find enough eligible tradable spread deviations. It is not missing data and should not prompt silent relaxation of stationarity, entry, or half-life thresholds. An ADF finding over 60 observations does not establish stable future cointegration.')
    fm=d['factor_models'];elig=_col(fm,'eligible','is_eligible');dt=_col(fm,'refit_date','refit_time','month','decision_time','refit_at')
    if elig and dt:
        hold=fm.loc[pd.to_datetime(fm[dt],utc=True).ge(START)&pd.to_datetime(fm[dt],utc=True).lt(END)]
        truth=hold[elig] if hold[elig].dtype!=object else hold[elig].astype(str).str.lower().isin(['true','1'])
        add(f'Holdout model log: {int(truth.sum())} eligible coin-months out of {len(hold)} scheduled coin-months. Every eligibility result and entry/exit reason is saved in factor_models.csv and factor_events.csv. Raw logs retain seven unused October 1 terminal refits; these are excluded from Jan-Sep chart/counts and no earned holdout return uses their new models.','Small')

    page(10,'Regimes are diagnostics, not trade filters')
    img('regimes',300)
    add('Regime definitions','Sub');add('Relative quote volume, trailing 30-day BTC volatility, and cross-coin return dispersion are classified high/low using medians fitted only to 2022-2023. Labels are available at decision time and relate to the following day\'s return and turnover, not same-day outcomes. Unknown regime observations are preserved rather than assigned to low activity.')
    add('Reading the estimates','Sub');add('Each point is high-regime minus low-regime mean daily net return at 20 bps; horizontal bounds are nominal block-bootstrap 95% intervals, not Sharpe ratios or cumulative regime equity. Bootstrap uses the declared 28-day blocks and seed; Holm correction addresses the regime contrasts within each period. Sample counts and corrected p-values are retained in the notebook and regime_summary.csv.')
    add('The contrasts describe association in this fixed universe. Volume, volatility, and dispersion can move together; these cuts do not identify information-driven trading, establish causal effects, or justify market-timing gates. Sparse high/low subsets produce wide uncertainty. Missing intervals are not evidence of a zero contrast.')
    contrasts=d['regime_summary'].loc[d['regime_summary'].split.eq('holdout')].drop_duplicates(['strategy_id','feature'])
    add(f'Holdout multiplicity check: {int(contrasts.p_holm.lt(.05).sum())} of {len(contrasts)} high-minus-low contrasts pass Holm 5%; nominal uncorrected intervals should not be promoted to validated regime effects.','Small')
    add('No annualized Sharpe is computed by concatenating noncontiguous high- or low-regime days. All models trade according to their own frozen rule irrespective of these labels.','Small')

    page(11,'What the research does and does not establish')
    add('Scope of the conclusion','Sub');add('The extension answers five concrete research questions with reproducible evidence. It does not search unrestricted coin pairs, tune a volatility gate, estimate an implementable borrowing/funding system, or claim risk-free arbitrage. Momentum/reversal are signal definitions; statistical arbitrage is the course umbrella label. Dollar neutrality and beta neutrality are distinct.')
    add('Material limitations','Sub');add('The eight surviving instruments are fixed after their survival was known. The 2022-2025 period has already been inspected in earlier research. Configuration screening can capitalize on noise; 2024 winner metrics are not unbiased forecasts. A single nine-month historical holdout is sensitive to market path and cannot establish persistence. Past-data monthly residual refits are permissible but their estimates can be unstable.')
    add('Funding, borrow availability/fees, margin/collateral, taxes, measured spread and impact, exchange outages, order-book depth, guaranteed fills, and ordinary target-weight drift are excluded. The close-based one-hour lag is an idealized execution model. The 5/10/15 bps scenarios should not be treated as verified real-world fees. No live orders, public publication, or scheduled monitoring occurred.')
    add('Reproducibility and preservation','Sub');add('The source package, configuration, all tested configurations, model logs, raw-archive checksums, data-quality receipts, freeze receipt, and output hashes accompany this report. Reporting uses frozen outputs and is separate from strategy evaluation. Original report, notebook, results, time-scale scan, and ZIP are preserved; original hashes are recorded in baseline_preservation.json.')
    add('Sources and attribution','Sub')
    for name,url in [('Binance public archive documentation',SOURCE_URL),('Binance dataset terms and CC BY-NC-SA 4.0',TERMS_URL),('Binance March 24, 2023 halt account',HALT_URL)]:
        add(f'<link href="{url}" color="{BLUE}">{escape(name)}</link><br/>{escape(url)}','Small')
    add('Assignment source: ClassProject.docx, The Wall Street Quants course. Binance market data and dataset-derived charts/results: attributed to Binance, used for non-commercial educational/personal non-production research, under the source dataset\'s stated CC BY-NC-SA 4.0 terms. All source data remain traceable to original archives.','Small')
    add('Run commands','Sub');add('From the separate extension project, use the installed virtual environment. The runner stages enforce history -> screening -> freeze -> holdout -> report. For artifact regeneration only: python -m crypto_stat_arb_extensions report. This does not fetch fresh data or change selections.','Small')
    def footer(c,doc):
        c.saveState();c.setStrokeColor(colors.HexColor('#D4DEE4'));c.line(45,42,W-45,42);c.setFont('Helvetica',7.5);c.setFillColor(colors.HexColor(MUTED));c.drawString(45,29,'CRYPTO RESEARCH EXTENSIONS | Educational historical backtest');c.drawRightString(W-45,29,f'{doc.page}');c.restoreState()
    SimpleDocTemplate(str(path),pagesize=A4,rightMargin=45,leftMargin=45,topMargin=40,bottomMargin=55,title='Expanded Crypto Strategy Research',author='Course research project').build(story,onFirstPage=footer,onLaterPages=footer)
    return path


def create_notebook(root:Path,d) -> tuple[Path,Path]:
    import nbformat
    from nbclient import NotebookClient
    from nbconvert import HTMLExporter
    from jupyter_client.manager import KernelManager
    from jupyter_client.kernelspec import KernelSpec
    import sys
    root=Path(root);folder=root/'notebooks';folder.mkdir(parents=True,exist_ok=True)
    path=folder/'expanded_crypto_research.ipynb';html=folder/'expanded_crypto_research.html'
    nb=nbformat.v4.new_notebook();cells=[]
    def md(s):cells.append(nbformat.v4.new_markdown_cell(s))
    def code(s):cells.append(nbformat.v4.new_code_cell(s))
    md('# Expanded crypto strategy research\n\n## tl;dr\n\n'+'\n\n'.join('- '+x for x in findings(d))+'\n\n**Historical holdout:** January 1-September 30, 2026 (273 days); not a prospective live test. Earlier periods are exploratory/retrospective. All eight evaluations were frozen before 2026 access. This notebook never downloads data or chooses new winners.')
    md('## Context & Methods\n\nFive extensions: signal IC, lower-turnover cross-sectional momentum, own-coin trend following, fixed BTC-factor residual reversal, and descriptive regimes. Eight CS candidates + eight trend candidates + one fixed residual model. Three champions selected by 2024 20 bps Sharpe, lower-turnover/ID tie-break. The four plain CS configurations already existed in the time-scale scan.\n\n### Key Assumptions\n- Fixed eight-coin survivor universe; theoretical spot shorts.\n- Close-based one-hour signal lag; 20 bps primary full-L1 target-change costs; entry and final liquidation included.\n- No borrowing, funding, financing, capacity, or ordinary weight drift; USDT numeraire.\n- Daily compounding and 365-day annualization; zero risk-free rate; BTC OLS alpha/beta with HAC(7).\n- 2025 was already inspected; 2026 is new-to-analysis historical evidence, not a prospective test.\n- October 2021 warm-up; documented 2023 halt bridge without price filling. Unknown data faults halt evaluation.')
    md('### 1. Setup and freeze verification\n\nUse the project environment (`/Users/cosdis/.venvs/myenv/bin/python`). The receipt and analysis hashes are checked **before** any holdout-valued input is opened.')
    code("from pathlib import Path\nimport sys, json\nimport numpy as np\nimport pandas as pd\nimport matplotlib.pyplot as plt\nfrom IPython.display import display\n%matplotlib inline\nROOT = Path.cwd()\nif ROOT.name == 'notebooks': ROOT = ROOT.parent\nassert (ROOT / 'outputs/freeze_receipt.json').exists()\nsys.path.insert(0, str(ROOT / 'src'))\nfrom crypto_stat_arb_extensions.reporting import (verify_frozen_inputs, load_outputs, primary, label, plot_ic, plot_screening, plot_equity, plot_costs, plot_factor, plot_regimes, plot_stability)\nchronology = verify_frozen_inputs(ROOT)\ndisplay(pd.DataFrame([chronology]).T.rename(columns={0:'Verified value'}))\nd = load_outputs(ROOT)\nmetrics = primary(d['holdout_metrics']).sort_values('strategy_id')")
    md('## Data\n\n### 2. Verify the holdout and accounting independently\n\nWe recompute every primary model\'s gross-minus-cost accounting, compounded equity, daily return/volatility/Sharpe, and drawdown independently of the package metric summarizer. Bounds are `(2026-01-01, 2026-10-01]` in UTC.')
    code("returns = primary(d['returns']).copy()\nreturns = returns.loc[returns.bar_end.gt(pd.Timestamp('2026-01-01', tz='UTC')) & returns.bar_end.le(pd.Timestamp('2026-10-01', tz='UTC'))]\nchecks=[]\nfor sid, frame in returns.groupby('strategy_id'):\n    frame=frame.sort_values('bar_end')\n    assert len(frame)==6552, (sid, len(frame))\n    assert frame.interval_hours.sum()==6552\n    assert frame.bar_end.iloc[0]==pd.Timestamp('2026-01-01 01:00',tz='UTC')\n    assert frame.bar_end.iloc[-1]==pd.Timestamp('2026-10-01',tz='UTC')\n    np.testing.assert_allclose(frame.net_return, frame.gross_return-frame.cost, atol=1e-14)\n    np.testing.assert_allclose(frame.cost, frame.turnover*20/10000, atol=1e-14)\n    equity=np.cumprod(1+frame.net_return.to_numpy())\n    np.testing.assert_allclose(frame.equity, equity, atol=1e-12)\n    daily=(1+frame.net_return.to_numpy()).reshape(273,24).prod(axis=1)-1\n    row=metrics.loc[metrics.strategy_id.eq(sid)].iloc[0]\n    np.testing.assert_allclose(row.total_return, equity[-1]-1, atol=1e-12)\n    np.testing.assert_allclose(row.volatility, daily.std(ddof=1)*np.sqrt(365), atol=1e-12)\n    sr=daily.mean()/daily.std(ddof=1)*np.sqrt(365) if daily.std(ddof=1)>0 else np.nan\n    np.testing.assert_allclose(row.sharpe, sr, atol=1e-10, equal_nan=True)\n    peaks=np.maximum.accumulate(np.r_[1,equity])[1:]\n    np.testing.assert_allclose(row.max_drawdown, -np.min(equity/peaks-1), atol=1e-12)\n    checks.append({'Model':label(sid),'Days':len(daily),'Elapsed hours':int(frame.interval_hours.sum()),'Net return':equity[-1]-1,'Independent Sharpe':sr})\ndisplay(pd.DataFrame(checks))\nprint('All primary holdout return, cost, equity, daily-metric and drawdown checks passed.')")
    md('### 3. Reconcile holdings, hedge netting, entry and liquidation\n\nAfter the freeze check, load the authorized cached panel only. Recalculate gross P&L from held weights and actual asset returns; recompute full-L1 changes with initial cash entry and final liquidation. Because BTC weights are already aggregated, this also checks that virtual hedge legs are not double charged.')
    code("from crypto_stat_arb_extensions.data import load_full_panel\nclose, quote_volume, audit = load_full_panel(ROOT)\nweights=d['weights']\nassert weights is not None, 'Independent holdings reconciliation requires cached weights'\nsymbols=list(close.columns)\nasset_returns=close.loc[pd.Timestamp('2026-01-01',tz='UTC'):pd.Timestamp('2026-10-01',tz='UTC')].pct_change(fill_method=None).iloc[1:]\nhedge_checks=[]\nfor sid, frame in returns.groupby('strategy_id'):\n    frame=frame.sort_values('bar_end').set_index('bar_end')\n    w=weights.loc[weights.strategy_id.eq(sid) & weights.execution_lag.eq(1)].set_index('bar_end').reindex(frame.index)[symbols]\n    assert w.notna().all().all()\n    gross=(w*asset_returns.reindex(w.index)).sum(axis=1)\n    np.testing.assert_allclose(gross, frame.gross_return, atol=1e-14)\n    changes=w.diff(); changes.iloc[0]=w.iloc[0]\n    traded=changes.abs().sum(axis=1); traded.iloc[-1]+=w.iloc[-1].abs().sum()\n    np.testing.assert_allclose(traded,frame.turnover,atol=1e-12)\n    hedge_checks.append({'Model':label(sid),'Initial entry L1':w.iloc[0].abs().sum(),'Final liquidation L1':w.iloc[-1].abs().sum(),'Total turnover':traded.sum(),'Mean gross exposure':w.abs().sum(axis=1).mean(),'Mean net exposure':w.sum(axis=1).mean()})\ndisplay(pd.DataFrame(hedge_checks).round(5))\nprint('All eight primary holdings, gross P&L and full-L1 cost checks passed.')")
    md('### 4. Inspect exact primary performance\n\nThe table reports actual nine-month total return separately from annualized quantities. N/A Sharpe means a zero-volatility path, not a missing loss. Full identifiers are retained in the cached CSV.')
    code("readable=metrics.copy()\nreadable['Model']=readable.strategy_id.map(label)\nrisk=['Model','gross_total_return','total_return','volatility','sharpe','max_drawdown']\nannual=['Model','cagr','annual_return','total_turnover','alpha','alpha_ci_low','alpha_ci_high','beta']\nexposure=['Model','mean_gross_exposure','mean_net_exposure','mean_unused_gross_budget','fraction_flat']\nprint('Return/risk (return columns are decimal fractions; volatility is annualized):')\ndisplay(readable[risk].rename(columns={'gross_total_return':'Gross return','total_return':'Net return','volatility':'Annual volatility','sharpe':'Sharpe','max_drawdown':'Max drawdown'}).round(5))\nprint('Annualized quantities, actual-period turnover, and BTC-relative alpha/beta:')\ndisplay(readable[annual].rename(columns={'annual_return':'Annual arithmetic','total_turnover':'Total turnover','alpha_ci_low':'Alpha CI lower','alpha_ci_high':'Alpha CI upper'}).round(5))\nprint('Exposure: unused gross budget is actual cash only for long/cash, not short margin cash:')\ndisplay(readable[exposure].rename(columns={'mean_gross_exposure':'Mean gross','mean_net_exposure':'Mean net','mean_unused_gross_budget':'Unused gross budget','fraction_flat':'Flat-hour fraction'}).round(5))")
    md('## Results\n\n### 5. Signal diagnostics\n\nPositive IC favors momentum; negative IC favors reversal. All forward labels remain inside their split. Stars mark within-period Holm p<0.05 across 24 comparisons. Intervals are nominal 95% estimates from 4,000 seeded 28-day block-bootstrap samples; within-block structure is retained, but coverage for all serial dependence and model-search uncertainty is not guaranteed. The lone Holm p=0.04799 is borderline and subject to finite-replicate precision.')
    code("fig=plot_ic(d['ic_summary'])\nplt.show()\nic_columns=['split','lookback_h','forward_horizon_h','mean_ic','n_valid','ci_low','ci_high','p_holm']\ndisplay(d['ic_summary'].loc[d['ic_summary'].split.eq('holdout'),ic_columns].round(5))")
    md('### 6. Historical screening\n\nThe CS buffer skips an entire rebalance below L1=0.25; Monday-weekly schedules are true calendar schedules. Trend weights remain at 1/8 per coin without rescaling active allocations. No 2025/2026 result selects a champion. The fixed residual model is a predeclared control, not tuned by 2024 Sharpe.')
    code("fig=plot_screening(d['historical_metrics'])\nplt.show()\nvalidation=primary(d['historical_metrics'])\nvalidation=validation.loc[validation.split.eq('validation')].sort_values(['family','sharpe'],ascending=[True,False])\ndisplay(validation[['strategy_id','total_return','sharpe','total_turnover']].round(4))\nspecs=pd.DataFrame(d['selection']['evaluated_strategies'])\ndisplay(specs[['strategy_id','role','lookback_h','rebalance_h','buffer_l1']])")
    md('### Historical yearly stability\n\nThese are retrospective matched calculations for the same eight frozen models, each year reset from cash and liquidated. The 2024 selection and already-viewed 2025 period are not independent tests. Yearly return changes do not establish their cause.')
    code("fig=plot_stability(d['annual_metrics'])\nplt.show()")
    md('### 7. Frozen 2026 equity paths\n\nAll panels share the same equity scale. The initial unit capital is included. These paths summarize outcomes; do not use the displayed best performer as a new holdout-selected strategy.')
    code("fig=plot_equity(d['returns'])\nplt.show()")
    md('### 8. Cost and extra-delay stress\n\nThe same targets are evaluated at 0/5/10/15/20/40 bps and at 20 bps with lag two. Scenarios are not confidence intervals. Five bps total is below the course\'s assumed seven-bps commission alone.')
    code("fig=plot_costs(d['holdout_metrics'])\nplt.show()\nlag=d['holdout_metrics'].loc[d['holdout_metrics'].cost_bps.eq(20)]\ndisplay(lag[['strategy_id','execution_lag','total_return','sharpe','total_turnover']].sort_values(['strategy_id','execution_lag']).round(5))")
    md('### 9. Factor model eligibility and actual trades\n\nMonthly beta fitting uses the first 30 daily observations and spread calibration uses the following 60, all ending 24 hours before the refit decision. ADF Holm, beta and half-life gates may reject most coin-months. Monthly parameters remain frozen, first-day cash is forced, and same-day reentry is disallowed. Each spread\'s 1/7 budget includes its hedge; BTC legs are aggregated before costs. Raw logs retain October 1 terminal-boundary refits; they are excluded from Jan-Sep counts, and no earned holdout return uses the new terminal model.')
    code("fig=plot_factor(d['factor_models'], d['factor_events'])\nplt.show()\nprint(f\"Raw model-log rows: {len(d['factor_models'])}; raw event-log rows: {len(d['factor_events'])}\")\nmodel_columns=['refit_time','symbol','beta','half_life_days','adf_pvalue_holm','eligible','reason']\nmodel_time=pd.to_datetime(d['factor_models'].refit_time,utc=True)\nevent_time=pd.to_datetime(d['factor_events'].decision_time,utc=True)\nholdout_models=d['factor_models'].loc[model_time.ge(pd.Timestamp('2026-01-01',tz='UTC')) & model_time.lt(pd.Timestamp('2026-10-01',tz='UTC'))]\nholdout_events=d['factor_events'].loc[event_time.ge(pd.Timestamp('2026-01-01',tz='UTC')) & event_time.lt(pd.Timestamp('2026-10-01',tz='UTC'))]\nassert len(holdout_models)==63\nprint('Holdout:',len(holdout_models),'coin-months;',int(holdout_models.eligible.sum()),'eligible;',int(holdout_events.event.eq('entry').sum()),'entries.')\ndisplay(holdout_models[model_columns].tail(14))\ndisplay(holdout_events.tail(12))")
    md('### 10. Descriptive following-day regimes\n\nHigh/low medians are fit on development only. Unknowns remain unknown. High-minus-low mean daily-return contrasts and bootstrap intervals show association, not causation. Holm adjustment is within period across declared regime contrasts. No discontinuous regime Sharpe or trading gate is introduced.')
    code("fig=plot_regimes(d['regime_summary'])\nplt.show()\nregime=d['regime_summary'].loc[d['regime_summary'].split.eq('holdout')]\ncontrast_columns=[c for c in ['strategy_id','feature','high_minus_low_net_return','ci_low','ci_high','p_holm'] if c in regime]\ndisplay(regime.drop_duplicates(['strategy_id','feature'])[contrast_columns].round(5))\ncounts=regime.groupby(['feature','regime']).agg(Calendar_days=('n_days','first'),Min_valid_returns=('n_valid_returns','min'),Max_valid_returns=('n_valid_returns','max'))\ndisplay(counts)\nprint('Counts are shared calendar regimes; min/max preserve possible model-level return availability differences. Full conditional model means/turnover are retained in regime_summary.csv.')\nprint('Holm-corrected significant contrasts:',int(regime.drop_duplicates(['strategy_id','feature']).p_holm.lt(.05).sum()),'of 24.')")
    md('## Takeaways\n\n'+'\n\n'.join('- '+x for x in findings(d))+'\n\nNo claim of risk-free arbitrage or deployable edge is established by a historical backtest alone. Original research is preserved; this is a separate extension. Successful and unsuccessful configurations are retained. New tests after viewing these outcomes must be labeled exploratory and evaluated on further unexamined/prospective data.\n\n## Sources and reproduction\n\n- [Binance archive documentation]('+SOURCE_URL+')\n- [Binance dataset terms]('+TERMS_URL+')\n- [Official 2023 halt account]('+HALT_URL+')\n- Assignment: `/Users/cosdis/Downloads/quant_course/ClassProject.docx`\n\nBinance data and dataset-derived charts/results are attributed to Binance under the stated CC BY-NC-SA 4.0 non-commercial educational/personal non-production terms. Source archives, checksums, normalizations, analysis freeze, selections and output hashes accompany the separate project. No live orders, publication, or scheduled monitoring.\n\nRegenerate artifacts without downloading or tuning: `python -m crypto_stat_arb_extensions report`. Run tests: `python -m pytest -q`.')
    nb.cells=cells;nb.metadata={'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python','version':__import__('sys').version.split()[0]}}
    nbformat.validate(nb)
    manager=KernelManager(kernel_name='python3')
    manager._kernel_spec=KernelSpec(argv=[sys.executable,'-m','ipykernel_launcher','-f','{connection_file}'],display_name='Python 3 (myenv)',language='python')
    executed=NotebookClient(nb,timeout=600,kernel_name='python3',km=manager,resources={'metadata':{'path':str(root)}},allow_errors=False).execute()
    nbformat.write(executed,path)
    exporter=HTMLExporter();body,_=exporter.from_notebook_node(executed);html.write_text(body)
    return path,html


def create_report(root:Path) -> dict:
    """Create supplementary PDF + executed notebook from frozen outputs only."""
    root=Path(root);d=load_outputs(root)
    figures=make_figures(root,d);pdf=create_pdf(root,d,figures);notebook,html=create_notebook(root,d)
    paths={'pdf':str(pdf),'notebook':str(notebook),'html':str(html),**{'figure_'+k:v for k,v in figures.items()}}
    receipt={'artifact_paths':paths,'sha256':{k:sha256(v) for k,v in paths.items()},
      'frozen_input_chronology':d['chronology'],'reporting_source_sha256':sha256(__file__),
      'execution':'Notebook executed top to bottom without errors; independent primary holdout accounting checks passed.',
      'visual_inspection':'Pending final PDF page and notebook rendered-output inspection.'}
    (root/'reports/artifact_verification.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt

"""Availability-aware accounting with explicit lifecycle masks, full-L1 costs and known venue-halt bridges."""
import numpy as np
import pandas as pd
from .backtest import BacktestResult,_validate_hourly_index,_utc_endpoint

def _matching(frame,prices,name,bool_required=False):
    if not isinstance(frame,pd.DataFrame) or not frame.index.equals(prices.index) or not frame.columns.equals(prices.columns):raise ValueError(name+' mustexactlymatchprices')
    if frame.isna().any().any():raise ValueError(name+' cannotbemissing')
    if bool_required and not all(pd.api.types.is_bool_dtype(x) for x in frame.dtypes):raise ValueError(name+' mustbebool')

def _bridges(prices):
    result=[]
    for item in prices.attrs.get('halt_bridges',[]):
        if not isinstance(item,dict) or not {'start','end','source'}.issubset(item) or not item['source']:raise ValueError('Bridge needs sourced endpoints')
        left,right=_utc_endpoint(item['start']),_utc_endpoint(item['end'])
        if right<=left+pd.Timedelta(hours=1) or left.floor('D')!=(right-pd.Timedelta(nanoseconds=1)).floor('D'):raise ValueError('Invalid bridge duration/day')
        if right<=prices.index[0] or left>=prices.index[-1]:continue
        if left not in prices.index or right not in prices.index:raise ValueError('Applicable bridge endpoints missing')
        result.append((left,right))
    result.sort()
    if any(b[0]<a[1] for a,b in zip(result,result[1:])):raise ValueError('Overlapping global bridges')
    return result

def asset_returns(prices):
    """Real consecutive marks and explicit whole-venue bridge, not gap filling."""
    _validate_hourly_index(prices.index)
    values=prices.to_numpy(dtype=float)
    if np.isinf(values).any() or (values[np.isfinite(values)]<=0).any():raise ValueError('Invalid observedprice')
    ret=prices.div(prices.shift(1))-1
    keep=np.ones(len(prices),dtype=bool);keep[0]=False;duration={}
    for left,right in _bridges(prices):
        keep&=~((prices.index>left)&(prices.index<right))
        ret.loc[right]=prices.loc[right]/prices.loc[left]-1
        duration[right.isoformat()]=int((right-left)/pd.Timedelta(hours=1))
    ret=ret.loc[keep].copy();ret.attrs={'interval_hours':duration};return ret

def simulate(prices,targets,start,end,cost_bps=20,execution_lag=1,*,hold_allowed=None,mandatory_exit=None):
    """Same metrics result container, real marks with fixed-slot lifecycle events.

    Mandatory event target changes bypass normal lag. The expired asset exits
    at its documented last real quote; remaining assets/aggregateBTChedge change
    at the completed-hour decision mark. LUNA00:40 is attributed to its01:00
    accounting bucket, NOT an anticipatory00:00 fill. Partial event execution
    and potentially20minute orphan hedge/neutrality interval are idealizations.
    """
    _matching(targets,prices,'targets')
    tv=targets.to_numpy(dtype=float)
    if not np.isfinite(tv).all():raise ValueError('Nonfinite targets')
    if isinstance(execution_lag,bool) or execution_lag not in (1,2):raise ValueError('Supportedlag1or2')
    if not np.isfinite(cost_bps) or cost_bps<0:raise ValueError('Invalidcost')
    start,end=_utc_endpoint(start),_utc_endpoint(end)
    if start not in prices.index or end not in prices.index or end<=start:raise ValueError('Evaluationendpoints')
    if hold_allowed is None:hold_allowed=pd.DataFrame(True,index=prices.index,columns=prices.columns)
    if mandatory_exit is None:mandatory_exit=pd.DataFrame(False,index=prices.index,columns=prices.columns)
    _matching(hold_allowed,prices,'hold_allowed',True);_matching(mandatory_exit,prices,'mandatory_exit',True)
    hv=hold_allowed.to_numpy(dtype=bool);ev=mandatory_exit.to_numpy(dtype=bool)
    if (np.abs(tv[ev])>1e-14).any():raise ValueError('Mandatory exit target must be zero')
    desired=targets.shift(execution_lag,fill_value=0.).to_numpy(dtype=float)
    event_positions=np.flatnonzero(ev.any(axis=1))
    for pos in event_positions:
        for step in range(1,execution_lag):
            if pos+step<len(prices):desired[pos+step]=tv[pos]
    for left,right in _bridges(prices):
        if any(left<t<right for t in (start,end)):raise ValueError('Evaluation endpoint inside suspended bridge')
        interior=(prices.index>left)&(prices.index<right)
        if ev[interior].any():raise ValueError('Mandatory trade cannot occur inside venue halt')
        pos=prices.index.get_loc(right);anchor=prices.index.get_loc(left)+1
        desired[pos]=desired[anchor]
    if (np.abs(desired[~hv])>1e-14).any():raise ValueError('Unpermitted holding: no audited executable liquidation')
    returns=asset_returns(prices)
    window=(returns.index>start)&(returns.index<=end)
    returns=returns.loc[window].copy();locs=prices.index.get_indexer(returns.index)
    held=pd.DataFrame(desired[locs],index=returns.index,columns=prices.columns)
    rv=returns.to_numpy(dtype=float);weights=held.to_numpy(dtype=float)
    if ((~np.isfinite(rv))&(np.abs(weights)>1e-14)).any():raise ValueError('Nonzeroholdinghasunobservedreturn')
    gross=np.where(np.isfinite(rv),rv*weights,0).sum(axis=1)
    post=weights.copy();forced=ev[locs].any(axis=1)
    post[forced]=tv[locs[forced]]
    current_marks=prices.iloc[locs].to_numpy(dtype=float)
    if ((np.abs(post-weights)>1e-14)&~np.isfinite(current_marks)).any():raise ValueError('Forced trade lacks observed current quote')
    if (np.abs(post[~hv[locs]])>1e-14).any():raise ValueError('Posteventholdingnotpermitted')
    previous=np.vstack([np.zeros((1,weights.shape[1])),post[:-1]])
    ordinary=np.abs(weights-previous).sum(axis=1)
    eventturn=np.abs(post-weights).sum(axis=1)
    turnover=ordinary+eventturn
    turnover[-1]+=np.abs(post[-1]).sum()
    cost=turnover*float(cost_bps)*1e-4;net=gross-cost
    if not np.isfinite(net).all() or (net<=-1).any():raise ValueError('Noncompoundableportfoliointerval')
    equity=np.cumprod(1+net)
    if not np.isfinite(equity).all():raise ValueError('Equityoverflow')
    peak=np.maximum.accumulate(np.r_[1.,equity])[1:]
    durations=returns.attrs.get('interval_hours',{})
    frame=pd.DataFrame({'gross_return':gross,'net_return':net,'turnover':turnover,'ordinary_turnover':ordinary,'forced_event_turnover':eventturn,'cost':cost,'equity':equity,'drawdown':equity/peak-1.,'interval_hours':[durations.get(t.isoformat(),1) for t in returns.index]},index=returns.index)
    partial=[]
    t=pd.Timestamp('2022-05-13T01:00:00Z')
    if t in frame.index and 'LUNAUSDT' in prices.columns and mandatory_exit.loc[t,'LUNAUSDT']:
        partial=[{'symbol':'LUNAUSDT','event_time':'2022-05-13T00:40:00Z','bucket_end':t.isoformat(),'post_event_weight':0.}]
    frame.attrs={'interval_hours':durations,'partial_interval_events':partial,'partial_event_exposure_warning':'LUNA pre-event heldweights represent00:00→00:40 within01UTCbucket; remainingpositions change at01UTC, possibletemporaryorphanhedge.'}
    return BacktestResult(frame,held)

"""Additional diagnostics for *fixed*, already saved portfolio return paths.

No trading rules, source selection, or portfolio weights are changed here.
Timestamps are interval ends; midnight ends the previous UTC economic day.
Returns are simple per-interval returns, turnover is the full-L1 cost base
(including any supplied entry/liquidation), and elapsed_days is mandatory.
Intervals may be subhourly or audited halt bridges within a UTC day. Intervals
crossing a day boundary, partial days, or missing whole days are not fabricated.

``summarize_performance`` returns scalar metrics plus ``drawdown``, ``break_even``,
``bootstrap``, ``exposures``, and ``definitions`` dictionaries. ``rolling`` is an
optional DataFrame and should be exported separately, not serialized as a scalar.
Undefined statistics are None. Returns and drawdown depths are fractions, not
percentages; ES is a signed daily lower-tail mean and drawdown depths are positive.
All annualizations use 365 calendar days. Daily win/gain-loss statistics are NOT
portfolio trade profit factors.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
import math
from typing import Iterator

import numpy as np
import pandas as pd
from scipy.optimize import brentq

YEAR_DAYS = 365.0
DEFAULT_SEED = 20261008
NS_PER_HOUR = 3_600_000_000_000


def _vector(values, name: str, n: int | None = None) -> np.ndarray:
    try:
        result = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{name} must be a numeric vector.') from exc
    if result.ndim != 1 or not len(result) or (n is not None and len(result) != n):
        raise ValueError(f'{name} must be a nonempty vector of the same length as timestamps.')
    if not np.isfinite(result).all():
        raise ValueError(f'{name} must be finite.')
    return result


def _returns(values, name: str, n: int | None = None) -> np.ndarray:
    result = _vector(values, name, n)
    if (result <= -1).any():
        raise ValueError(f'{name} must be greater than -1; bankruptcy paths need a different convention.')
    return result


def _timeline(timestamps, elapsed_days: float, interval_hours=None):
    if isinstance(elapsed_days, (bool, np.bool_)) or not np.isfinite(elapsed_days) or elapsed_days <= 0:
        raise ValueError('elapsed_days must be explicitly supplied, finite, and positive.')
    try:
        index = pd.DatetimeIndex(pd.to_datetime(timestamps, utc=True)).as_unit('ns')
    except (TypeError, ValueError) as exc:
        raise ValueError('timestamps must be UTC-convertible interval endpoints.') from exc
    if not len(index) or index.hasnans or index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError('timestamps must be nonempty, strictly increasing, unique, and finite.')
    gaps = np.diff(index.asi8)
    if interval_hours is None:
        # Infer only a uniform frequency. Irregular/bridged observations require
        # explicit durations; a missing observation is not silently treated as a halt.
        if len(index) == 1:
            hours = np.array([float(elapsed_days) * 24])
        else:
            if not np.all(gaps == gaps[0]):
                raise ValueError('Irregular endpoints require explicit interval_hours.')
            hours = np.full(len(index), gaps[0] / NS_PER_HOUR)
    else:
        hours = _vector(interval_hours, 'interval_hours', len(index))
    if (hours <= 0).any():
        raise ValueError('interval_hours must be strictly positive.')
    raw_ns = hours * NS_PER_HOUR
    if (raw_ns > np.iinfo(np.int64).max).any():
        raise ValueError('Interval duration is too large.')
    duration_ns = np.rint(raw_ns).astype(np.int64)
    if (duration_ns <= 0).any() or not np.allclose(raw_ns, duration_ns, rtol=0, atol=1):
        raise ValueError('Intervals must be representable at nanosecond precision.')
    if len(index) > 1 and not np.array_equal(gaps, duration_ns[1:]):
        raise ValueError('Interval durations must match endpoint gaps; overlap/missing intervals are invalid.')
    if not np.isclose(hours.sum(), float(elapsed_days) * 24, rtol=0, atol=1e-8):
        raise ValueError('Declared elapsed_days does not match interval durations.')
    starts = index - pd.to_timedelta(duration_ns, unit='ns')
    days = (index - pd.Timedelta(nanoseconds=1)).floor('D')
    if not starts.floor('D').equals(days):
        raise ValueError('Intervals cannot cross UTC interval-day boundaries.')
    return index, hours, starts, days


def calendar_daily_path(net_return, gross_return, turnover, timestamps,
                        elapsed_days: float, interval_hours=None) -> pd.DataFrame:
    """Stable compounding of contiguous, complete 24-hour UTC interval-days.

    ``net_log_return``/``gross_log_return`` preserve information when the displayed
    compounded return rounds to -1. No forward fill or synthetic return is used.
    Naive timestamps, if supplied, are interpreted as UTC, never local time.
    """
    index, hours, _, days = _timeline(timestamps, elapsed_days, interval_hours)
    net = _returns(net_return, 'net_return', len(index))
    gross = _returns(gross_return, 'gross_return', len(index))
    trades = _vector(turnover, 'turnover', len(index))
    if (trades < 0).any():
        raise ValueError('turnover must be nonnegative.')
    unique, codes = np.unique(days.asi8, return_inverse=True)
    day_index = pd.DatetimeIndex(unique, tz='UTC', name='day')
    covered = np.bincount(codes, weights=hours, minlength=len(unique))
    if not np.allclose(covered, 24, rtol=0, atol=1e-8):
        raise ValueError('Every UTC interval-day must cover exactly 24 elapsed hours.')
    if len(day_index) > 1 and not np.all(np.diff(day_index.asi8) == 24 * NS_PER_HOUR):
        raise ValueError('Calendar days must be contiguous; missing whole days are invalid.')
    if not np.isclose(float(elapsed_days), len(day_index), rtol=0, atol=1e-10):
        raise ValueError('elapsed_days must equal the complete UTC day count.')
    log_net = np.bincount(codes, weights=np.log1p(net), minlength=len(unique))
    log_gross = np.bincount(codes, weights=np.log1p(gross), minlength=len(unique))
    with np.errstate(over='ignore'):
        daily_net, daily_gross = np.expm1(log_net), np.expm1(log_gross)
    if not np.isfinite(daily_net).all() or not np.isfinite(daily_gross).all():
        raise ValueError('Daily compounding overflowed.')
    return pd.DataFrame({
        'net_return': daily_net, 'gross_return': daily_gross,
        'net_log_return': log_net, 'gross_log_return': log_gross,
        'turnover': np.bincount(codes, weights=trades, minlength=len(unique)),
        'interval_hours': covered,
        'n_observations': np.bincount(codes, minlength=len(unique)),
    }, index=day_index)


def _finite_expm1(value: float) -> float | None:
    with np.errstate(over='ignore', invalid='ignore'):
        result = float(np.expm1(value))
    return result if np.isfinite(result) else None


def _daily_moments(values: np.ndarray):
    # Scaling before squaring prevents finite very large returns from yielding
    # an infinite SD and a falsely zero Sharpe. It also protects the mean sum.
    scale = float(np.max(np.abs(values)))
    normalized = values / scale if scale else values
    mean_scaled = float(np.mean(normalized))
    mean = mean_scaled * scale
    # Exact constants are undefined risk ratios even when floating-point std
    # routines report a tiny nonzero variance from mean rounding.
    if len(values) < 2:
        return mean, None, None
    std_scaled = 0.0 if np.max(values) == np.min(values) else float(np.std(normalized, ddof=1))
    with np.errstate(over='ignore'):
        std = float(np.float64(std_scaled) * scale)
    sharpe = mean_scaled / std_scaled * math.sqrt(YEAR_DAYS) if std_scaled > 0 else None
    return mean, std if np.isfinite(std) else None, sharpe


def _finite_number(value) -> float | None:
    return float(value) if np.isfinite(value) else None


def expected_shortfall(daily_returns, tail_probability: float = .05) -> float:
    """Signed lower-tail mean with exact fractional tail mass (ES95 by default).

    For n days, use n*0.05 observations of probability mass: all worst floor(n*.05)
    days plus the needed fraction of the next day. Sorting/ties do not change the
    value. An entirely positive tail gives positive ES, not an invented loss.
    """
    values = _vector(daily_returns, 'daily_returns')
    if not np.isfinite(tail_probability) or not 0 < tail_probability <= 1:
        raise ValueError('tail_probability must be in (0, 1].')
    ordered = np.sort(values)
    mass = len(ordered) * float(tail_probability)
    whole = min(int(math.floor(mass)), len(ordered))
    fractional = mass - whole
    selected = ordered[:min(whole + (fractional > 0), len(ordered))]
    scale = float(np.max(np.abs(selected)))
    if scale == 0:
        return 0.0
    # Sum normalized tail values before dividing by probability mass. Five
    # finite 1e308 days have a representable mean but an overflowing raw sum.
    total = math.fsum(ordered[:whole] / scale)
    if fractional > 0 and whole < len(ordered):
        total += fractional * (ordered[whole] / scale)
    return float(total / mass * scale)


def drawdown_statistics(net_return, timestamps, elapsed_days: float,
                        interval_hours=None) -> dict:
    """Observed-endpoint drawdowns computed in log equity, including initial NAV.

    Depth uses log trough-minus-peak, never rounded tiny equity. Durations are
    actual elapsed time. Underwater time fraction assigns each interval's duration
    to its *ending* drawdown status. It is NOT intra-interval occupancy; halt bridge
    interiors (and any unobserved intrabar variation) cannot be recovered.
    """
    index, hours, starts, _ = _timeline(timestamps, elapsed_days, interval_hours)
    net = _returns(net_return, 'net_return', len(index))
    times = starts[:1].append(index)
    log_increments = np.log1p(net)
    logs = np.r_[0.0, np.cumsum(log_increments)]
    peaks = np.maximum.accumulate(logs)
    depths = logs - peaks
    trough = int(np.argmin(depths))
    max_depth = float(-np.expm1(depths[trough]))
    # Only comparisons to a high-water mark get a machine-precision tolerance.
    # Selecting the deepest trough uses logs without a rounded-equity tie.
    # Scale roundoff to actual accumulated log magnitudes, not an absolute NAV
    # epsilon: a genuine 1e-200 loss from initial cash is not a numerical tie.
    accumulated_magnitude = np.r_[0.0, np.cumsum(np.abs(log_increments))]
    tolerance = 8 * np.finfo(float).eps * (np.abs(peaks) + accumulated_magnitude)
    underwater = depths < -tolerance
    underwater_time = float(hours[underwater[1:]].sum() / (elapsed_days * 24))
    irregular = bool(np.any(hours > np.min(hours) + 1e-10))
    result = {
        'max_drawdown': max(0.0, max_depth),
        'max_drawdown_log_depth': float(-depths[trough]),
        'peak': None, 'trough': None, 'recovery': None,
        'peak_to_trough_days': 0.0, 'underwater_days': 0.0,
        'max_drawdown_recovery_censored': False,
        'longest_underwater_days': 0.0,
        'longest_underwater_start': None, 'longest_underwater_end': None,
        'longest_underwater_censored': False,
        'time_underwater_fraction': underwater_time,
        'underwater_time_convention': 'elapsed interval duration classified by ending observed drawdown',
        'halt_interior_unobserved': irregular,
        'intrabar_drawdown_unobserved': True,
        'max_interval_hours': float(np.max(hours)),
    }
    if max_depth == 0 or not underwater.any():
        # Remove numerical dust from exactly/approximately recovered flat paths.
        result['max_drawdown'] = 0.0
        result['max_drawdown_log_depth'] = 0.0
        return result
    peak_log = peaks[trough]
    candidates = np.flatnonzero(np.abs(logs[:trough + 1] - peak_log) <= tolerance[trough])
    peak = int(candidates[-1])
    recovered = np.flatnonzero(logs[trough + 1:] >= peak_log - tolerance[trough])
    recovery = int(trough + 1 + recovered[0]) if len(recovered) else None
    end = recovery if recovery is not None else len(index)
    result.update(
        peak=times[peak].isoformat(), trough=times[trough].isoformat(),
        recovery=times[recovery].isoformat() if recovery is not None else None,
        peak_to_trough_days=float((times[trough] - times[peak]) / pd.Timedelta(days=1)),
        underwater_days=float((times[end] - times[peak]) / pd.Timedelta(days=1)),
        max_drawdown_recovery_censored=recovery is None,
    )
    episode_start = None
    episodes = []
    for i in range(1, len(logs)):
        if underwater[i] and episode_start is None:
            episode_start = i - 1
        elif not underwater[i] and episode_start is not None:
            episodes.append((episode_start, i, False))
            episode_start = None
    if episode_start is not None:
        episodes.append((episode_start, len(index), True))
    # Earliest episode wins an equal-duration tie; no future recovery is assumed.
    longest = max(episodes, key=lambda episode: times[episode[1]] - times[episode[0]])
    start, end, censored = longest
    result.update(
        longest_underwater_days=float((times[end] - times[start]) / pd.Timedelta(days=1)),
        longest_underwater_start=times[start].isoformat(),
        longest_underwater_end=times[end].isoformat(),
        longest_underwater_censored=censored,
    )
    return result


def break_even_cost_bps(gross_return, turnover) -> dict:
    """Exact compounded root for fixed gross returns and full-L1 turnover.

    Solve sum(log(1+gross_i-c*turnover_i)) = 0 for nonnegative c; return
    c*10000 bps. This is not total gross profit divided by summed turnover.
    Gross-unprofitable paths have no nonnegative root. With no trades, cost is
    unidentified. Both cases return None, not zero or a fictitious negative fee.
    """
    gross = _returns(gross_return, 'gross_return')
    trades = _vector(turnover, 'turnover', len(gross))
    if (trades < 0).any():
        raise ValueError('turnover must be nonnegative.')
    gross_log = math.fsum(np.log1p(gross))
    result = {'status': None, 'bps': None,
              'gross_total_return': _finite_expm1(gross_log),
              'gross_log_total_return': gross_log,
              'cost_convention': 'net_i = gross_i - bps/10000 * full_L1_turnover_i',
              'fixed_path_not_capacity_estimate': True}
    positive = trades > 0
    if not positive.any():
        result['status'] = 'no_trades'
        return result
    if gross_log < 0:
        result['status'] = 'gross_unprofitable'
        return result
    if gross_log == 0:
        result.update(status='root', bps=0.0, net_log_return_at_root=0.0)
        return result
    # Normalize to the solvency boundary. Solve for log(1-cost/ceiling),
    # not cost/ceiling itself: an almost-bankrupt root can otherwise round to
    # one and Brent's relative tolerance can falsely certify a nonzero return.
    with np.errstate(over='ignore'):
        ceiling = float(np.min((1 + gross[positive]) / trades[positive]))
    if not np.isfinite(ceiling):
        result['status'] = 'root_unrepresentable'
        return result
    coefficients = ceiling * trades[positive] / (1 + gross[positive])
    coefficients = np.minimum(coefficients, 1.0)
    binding = int(np.argmin((1 + gross[positive]) / trades[positive]))
    coefficients[binding] = 1.0
    with np.errstate(divide='ignore'):
        log_coefficients = np.log(coefficients)
        log_complements = np.log1p(-coefficients)
    def log_terminal(log_survival):
        if log_survival == 0:
            return gross_log
        terms = np.logaddexp(log_complements, log_coefficients + log_survival)
        return float(gross_log + math.fsum(terms))
    log_survival = brentq(log_terminal, -gross_log, 0.0,
                         xtol=np.nextafter(0.0, 1.0),
                         rtol=8 * np.finfo(float).eps, maxiter=300)
    if log_survival > -math.log(2):
        cost_fraction = ceiling * -np.expm1(log_survival)
    else:
        cost_fraction = ceiling - ceiling * np.exp(log_survival)
    bps = float(cost_fraction * 10000)
    if not np.isfinite(bps):
        result['status'] = 'root_unrepresentable'
        return result
    def actual_residual(candidate_bps):
        # Audit the same operation order as the modeled per-interval deduction,
        # including the bps -> decimal conversion used by downstream callers.
        net = gross - (candidate_bps / 10000) * trades
        return math.fsum(np.log1p(net)) if (net > -1).all() else -np.inf
    residual = actual_residual(bps)
    if not np.isfinite(residual) or abs(residual) > 1e-9:
        # Single traded-bar gross can be vastly larger than 1; then (1+gross)
        # loses its +1 in float arithmetic although gross-fee is still exact.
        # Candidate checks also prevent silently advertising an inaccurate root.
        # A small candidate set avoids O(n^2) audits on large interval paths.
        traded_indices = np.flatnonzero(positive)
        binding_index = int(traded_indices[binding])
        with np.errstate(over='ignore'):
            candidates = [bps, float(gross[binding_index] / trades[binding_index] * 10000)]
        candidates = [candidate for candidate in candidates if np.isfinite(candidate) and candidate >= 0]
        audited = [(abs(actual_residual(candidate)), candidate) for candidate in candidates]
        error, candidate = min(audited) if audited else (np.inf, None)
        if error > 1e-9:
            result.update(status='root_unrepresentable', numerical_root_residual=_finite_number(residual))
            return result
        bps = candidate
        residual = actual_residual(bps)
    result.update(status='root', bps=float(bps),
                  net_log_return_at_root=float(residual))
    return result


@dataclass(frozen=True)
class CircularBlockPlan:
    """Compact reusable period-level resampling plan for paired models/costs.

    Store block starts, not bars or a samples-by-all-bars tensor. The same plan
    must be reused for every model/cost with the same calendar-day index.
    """
    n_days: int
    samples: int
    block_days: int
    seed: int
    starts: np.ndarray

    def iter_indices(self, chunk_size: int = 128) -> Iterator[np.ndarray]:
        if not isinstance(chunk_size, (int, np.integer)) or chunk_size <= 0:
            raise ValueError('chunk_size must be a positive integer.')
        offsets = np.arange(self.block_days, dtype=np.int64)
        for start in range(0, self.samples, chunk_size):
            block_starts = self.starts[start:start + chunk_size]
            yield ((block_starts[..., None] + offsets) % self.n_days).reshape(
                len(block_starts), -1)[:, :self.n_days]


def circular_block_plan(n_days: int, samples: int = 4000, block_days: int = 28,
                        seed: int = DEFAULT_SEED) -> CircularBlockPlan:
    """Seeded circular blocks of contiguous calendar days, never iid bars."""
    for value, name in [(n_days, 'n_days'), (samples, 'samples'), (block_days, 'block_days')]:
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value <= 0:
            raise ValueError(f'{name} must be a positive integer.')
    if isinstance(seed, (bool, np.bool_)) or not isinstance(seed, (int, np.integer)) or seed < 0:
        raise ValueError('seed must be a nonnegative integer.')
    starts = np.random.default_rng(int(seed)).integers(
        0, int(n_days), size=(int(samples), math.ceil(n_days / block_days)), dtype=np.int32)
    starts.setflags(write=False)
    return CircularBlockPlan(int(n_days), int(samples), int(block_days), int(seed), starts)


def circular_block_indices(n_days: int, samples: int = 4000, block_days: int = 28,
                           seed: int = DEFAULT_SEED) -> np.ndarray:
    """Expanded reusable day-index plan; prefer circular_block_plan for big periods."""
    plan = circular_block_plan(n_days, samples, block_days, seed)
    # One final result array; chunking avoids a second full-size expansion.
    result = np.empty((samples, n_days), dtype=np.int32)
    offset = 0
    for indices in plan.iter_indices():
        result[offset:offset + len(indices)] = indices
        offset += len(indices)
    return result


def _daily_input(daily_net):
    if isinstance(daily_net, pd.DataFrame):
        if not {'net_return', 'net_log_return'}.issubset(daily_net.columns):
            raise ValueError('Daily DataFrame needs net_return and net_log_return.')
        values = _vector(daily_net['net_return'], 'daily net returns')
        logs = _vector(daily_net['net_log_return'], 'daily net log returns', len(values))
        with np.errstate(over='ignore'):
            if not np.allclose(values, np.expm1(logs), rtol=1e-12, atol=1e-14):
                raise ValueError('Daily simple returns do not match log returns.')
        index = daily_net.index
    else:
        values = _returns(daily_net, 'daily net returns')
        logs = np.log1p(values)
        index = daily_net.index if isinstance(daily_net, pd.Series) else None
    if index is not None:
        if not isinstance(index, pd.DatetimeIndex) or index.tz is None:
            raise ValueError('Daily index must be a timezone-aware DatetimeIndex.')
        index = index.tz_convert('UTC').as_unit('ns')
        if index.hasnans or index.has_duplicates or not index.is_monotonic_increasing:
            raise ValueError('Daily index must be increasing and unique.')
        if not index.equals(index.floor('D')) or (len(index) > 1 and not np.all(np.diff(index.asi8) == 24 * NS_PER_HOUR)):
            raise ValueError('Daily index must contain contiguous UTC day boundaries.')
    return values, logs, index


def bootstrap_daily(daily_net, elapsed_days: float, indices=None, samples: int = 4000,
                    block_days: int = 28, seed: int = DEFAULT_SEED,
                    confidence: float = .95, chunk_size: int = 128) -> dict:
    """Nominal percentile CIs from circular calendar-day blocks.

    Resample one fixed n-day daily net path, keeping n and elapsed duration fixed.
    Reuse ``indices`` (CircularBlockPlan or expanded indices) for paired costs and
    models. These are NOT search-adjusted, probabilistic/deflated Sharpe estimates,
    walk-forward tests, or proof of an edge. All-cash Sharpe remains undefined.
    """
    values, logs, _ = _daily_input(daily_net)
    n = len(values)
    if not np.isfinite(elapsed_days) or not np.isclose(elapsed_days, n, rtol=0, atol=1e-10):
        raise ValueError('Bootstrap elapsed_days must equal the complete daily path length.')
    if not np.isfinite(confidence) or not 0 < confidence < 1:
        raise ValueError('confidence must lie in (0, 1).')
    if not isinstance(chunk_size, (int, np.integer)) or chunk_size <= 0:
        raise ValueError('chunk_size must be positive.')
    paired_plan_supplied = indices is not None
    if indices is None:
        indices = circular_block_plan(n, samples, block_days, seed)
    if isinstance(indices, CircularBlockPlan):
        if indices.n_days != n:
            raise ValueError('Paired bootstrap plan must match the period day count.')
        samples, block_days, seed_used = indices.samples, indices.block_days, indices.seed
        chunks = indices.iter_indices(chunk_size)
    else:
        indices = np.asarray(indices)
        if indices.ndim != 2 or indices.shape[1] != n or indices.shape[0] == 0 or not np.issubdtype(indices.dtype, np.integer):
            raise ValueError('Bootstrap indices must be an integer samples-by-days matrix.')
        if (indices < 0).any() or (indices >= n).any():
            raise ValueError('Bootstrap day indices out of range.')
        if not isinstance(block_days, (int, np.integer)) or block_days <= 0:
            raise ValueError('block_days must be positive.')
        for start in range(0, n, block_days):
            block = indices[:, start:min(start + block_days, n)]
            if block.shape[1] > 1 and not np.all(np.diff(block, axis=1) % n == 1 % n):
                raise ValueError('Indices must use contiguous circular calendar-day blocks, not iid days/bars.')
        samples, seed_used = indices.shape[0], None
        chunks = (indices[start:start + chunk_size] for start in range(0, samples, chunk_size))
    sharpes = np.full(samples, np.nan)
    log_totals = np.empty(samples)
    offset = 0
    for draw in chunks:
        path = values[draw]
        count = len(draw)
        scale = np.max(np.abs(path), axis=1)
        scale[scale == 0] = 1
        normalized = path / scale[:, None]
        mean = normalized.mean(axis=1)
        if n >= 2:
            std = normalized.std(axis=1, ddof=1)
            valid = (std > 0) & (np.max(path, axis=1) != np.min(path, axis=1))
            sharpe_chunk = np.full(count, np.nan)
            sharpe_chunk[valid] = mean[valid] / std[valid] * np.sqrt(YEAR_DAYS)
            sharpes[offset:offset + count] = sharpe_chunk
        log_totals[offset:offset + count] = logs[draw].sum(axis=1)
        offset += count
    quantiles = [(1 - confidence) / 2, (1 + confidence) / 2]
    finite_sharpe = sharpes[np.isfinite(sharpes)]
    with np.errstate(over='ignore'):
        total_returns = np.expm1(log_totals)
        cagrs = np.expm1(log_totals * YEAR_DAYS / elapsed_days)
    def interval(draws):
        if not len(draws):
            return [None, None]
        with np.errstate(invalid='ignore'):
            result = np.quantile(draws, quantiles)
        return [float(value) if np.isfinite(value) else None for value in result]
    return {
        'sharpe_ci': interval(finite_sharpe),
        'total_return_ci': interval(total_returns), 'cagr_ci': interval(cagrs),
        'log_total_return_ci': interval(log_totals),
        'valid_sharpe_samples': int(len(finite_sharpe)),
        'samples': int(samples), 'block_days': int(block_days), 'seed': seed_used,
        'confidence': float(confidence),
        'method': 'circular calendar-day block bootstrap percentile intervals',
        'nominal_not_search_adjusted': True,
        'paired_plan_supplied': paired_plan_supplied,
        'shorter_than_block': n < block_days,
        'sharpe_conditioned_on_defined_samples': len(finite_sharpe) != samples,
    }


def _benchmark_values(benchmark_daily, daily_index):
    if not isinstance(benchmark_daily, pd.Series):
        raise ValueError('benchmark_daily must be a timestamp-indexed Series of daily simple returns.')
    # Validate its complete calendar, then permit extra dates outside this period.
    _daily_input(benchmark_daily)
    benchmark = benchmark_daily.copy()
    benchmark.index = benchmark.index.tz_convert('UTC')
    aligned = benchmark.reindex(daily_index)
    return _returns(aligned, 'aligned benchmark daily returns', len(daily_index))


def rolling_diagnostics(daily, window_days: int = 90,
                        benchmark_daily: pd.Series | None = None) -> pd.DataFrame:
    """Trailing contiguous net return/Sharpe and optional contemporaneous BTC OLS.

    The first window_days-1 rows are undefined. Only information up to the row's
    day is used, so appending future observations cannot change earlier windows.
    Annualized alpha is arithmetic daily intercept times 365 (not compounded).
    """
    values, logs, index = _daily_input(daily)
    if index is None:
        raise ValueError('Rolling diagnostics require a contiguous daily date index.')
    if isinstance(window_days, (bool, np.bool_)) or not isinstance(window_days, (int, np.integer)) or window_days < 2:
        raise ValueError('window_days must be an integer >= 2.')
    result = pd.DataFrame(np.nan, index=index,
                          columns=['net_return', 'sharpe', 'beta', 'annualized_alpha'])
    benchmark = _benchmark_values(benchmark_daily, index) if benchmark_daily is not None else None
    for stop in range(window_days, len(values) + 1):
        start = stop - window_days
        path = values[start:stop]
        _, _, sharpe = _daily_moments(path)
        result.iloc[stop - 1, 0] = _finite_expm1(math.fsum(logs[start:stop]))
        if sharpe is not None:
            result.iloc[stop - 1, 1] = sharpe
        if benchmark is not None:
            x = benchmark[start:stop]
            xscale = float(np.max(np.abs(x))) or 1.0
            yscale = float(np.max(np.abs(path))) or 1.0
            xnormal, ynormal = x / xscale, path / yscale
            xmean, ymean = float(xnormal.mean()), float(ynormal.mean())
            variance = float(np.mean((xnormal - xmean) ** 2))
            if np.max(x) != np.min(x) and variance > 0:
                beta_normal = float(np.mean((xnormal - xmean) * (ynormal - ymean)) / variance)
                with np.errstate(over='ignore'):
                    beta = beta_normal * (np.float64(yscale) / xscale)
                    alpha = (ymean - beta_normal * xmean) * np.float64(yscale) * YEAR_DAYS
                result.iloc[stop - 1, 2] = _finite_number(beta)
                result.iloc[stop - 1, 3] = _finite_number(alpha)
    result.index.name = 'day'
    return result


def exposure_statistics(exposures: pd.DataFrame, timestamps, elapsed_days: float,
                        interval_hours=None) -> dict:
    """Elapsed-weighted diagnostics from independently supplied held exposures.

    Recognized interval-level columns are gross/net/long/short, unused_gross_budget,
    cash_allocation, inactive_slot_budget, and unallocated_spread_budget. The
    latter budgets are deliberately separate: missing short capacity is NOT cash.
    No cash value is inferred from 1-gross. Optional entirely-NaN columns are
    omitted; partially missing or nonfinite exposure paths are rejected.
    """
    index, hours, _, _ = _timeline(timestamps, elapsed_days, interval_hours)
    if not isinstance(exposures, pd.DataFrame) or not isinstance(exposures.index, pd.DatetimeIndex):
        raise ValueError('Exposure paths must be a timestamp-indexed DataFrame.')
    normalized = pd.DatetimeIndex(pd.to_datetime(exposures.index, utc=True)).as_unit('ns')
    if not normalized.equals(index):
        raise ValueError('Exposure endpoints must exactly match return endpoints.')
    weights = hours / hours.sum()
    result = {'averaging': 'elapsed interval-hours weighted supplied held exposure',
              'cash_inferred_from_unused_gross': False}
    recognized = ['gross', 'net', 'long', 'short', 'unused_gross_budget',
                  'cash_allocation', 'inactive_slot_budget', 'unallocated_spread_budget']
    for name in recognized:
        if name not in exposures or exposures[name].isna().all():
            continue
        values = _vector(exposures[name], f'exposure {name}', len(index))
        if name != 'net' and (values < -1e-12).any():
            raise ValueError(f'{name} exposure/budget must be nonnegative.')
        result[f'mean_{name}'] = float(np.dot(values, weights))
        result[f'min_{name}'] = float(np.min(values))
        result[f'max_{name}'] = float(np.max(values))
        if name == 'gross':
            result['fraction_flat'] = float(np.dot((values == 0).astype(float), weights))
    return result


def summarize_performance(net_return, gross_return, turnover, timestamps,
                          elapsed_days: float, interval_hours=None,
                          bootstrap_plan=None, exposures: Mapping | pd.DataFrame | None = None,
                          benchmark_daily: pd.Series | None = None,
                          include_rolling: bool = True,
                          bootstrap_samples: int = 4000,
                          bootstrap_seed: int = DEFAULT_SEED,
                          bootstrap_block_days: int = 28) -> dict:
    """Enrich one fixed path; all full-path observations/cash days remain included.

    Provide exposures as an independently audited summary mapping or same-index
    per-interval DataFrame. This function never infers trades or profit factor
    from aggregate returns, nor cash from unused short/gross capacity.
    ``bootstrap_plan`` must be shared for all paired paths in a calendar period.
    """
    daily = calendar_daily_path(net_return, gross_return, turnover, timestamps,
                                elapsed_days, interval_hours)
    values = daily.net_return.to_numpy()
    mean, std, sharpe = _daily_moments(values)
    total_log = math.fsum(daily.net_log_return.to_numpy())
    gross_log = math.fsum(daily.gross_log_return.to_numpy())
    cagr = _finite_expm1(total_log * YEAR_DAYS / elapsed_days)
    scale = float(np.max(np.abs(values))) or 1.0
    normalized = values / scale
    # Scale negatives separately: scaling by a giant positive return would erase
    # real downside, while squaring tiny negatives directly can underflow.
    negative = np.minimum(values, 0)
    downside_scale = float(np.max(np.abs(negative)))
    downside_normal = float(np.sqrt(np.mean((negative / downside_scale) ** 2))) if downside_scale else 0.0
    downside = downside_normal * downside_scale
    mean_normal = float(np.mean(normalized))
    std_normal = (0.0 if np.max(values) == np.min(values) else float(np.std(normalized, ddof=1))) if len(values) >= 2 else None
    with np.errstate(over='ignore'):
        annual_return = _finite_number(np.float64(mean_normal) * YEAR_DAYS * scale)
        annual_volatility = _finite_number(np.float64(std_normal) * math.sqrt(YEAR_DAYS) * scale) if std_normal is not None else None
        sortino = _finite_number(np.float64(mean_normal) * (np.float64(scale) / downside_scale)
                                 / downside_normal * math.sqrt(YEAR_DAYS)) if downside_normal > 0 else None
    drawdown = drawdown_statistics(net_return, timestamps, elapsed_days, interval_hours)
    worst_day = int(np.argmin(daily.net_log_return.to_numpy()))
    worst_week_return = worst_week_start = worst_week_end = None
    if len(daily) >= 7:
        # Daily log sums retain the true worst window even when expm1 rounds -1.
        logs = daily.net_log_return.to_numpy()
        windows = np.convolve(logs, np.ones(7), mode='valid')
        worst_week = int(np.argmin(windows))
        worst_week_return = _finite_expm1(float(windows[worst_week]))
        worst_week_start = daily.index[worst_week].date().isoformat()
        worst_week_end = daily.index[worst_week + 6].date().isoformat()
    gains = float(np.maximum(normalized, 0).sum())
    losses = float(-np.minimum(normalized, 0).sum())
    trades = float(np.sum(np.asarray(turnover, dtype=float)))
    if isinstance(exposures, pd.DataFrame):
        exposure_summary = exposure_statistics(exposures, timestamps, elapsed_days, interval_hours)
    elif exposures is None:
        exposure_summary = {}
    elif isinstance(exposures, Mapping):
        exposure_summary = dict(exposures)
    else:
        raise ValueError('exposures must be an independently calculated summary mapping.')
    summary = {
        'n_observations': len(np.asarray(net_return)), 'n_days': len(daily),
        'elapsed_days': float(elapsed_days),
        'first_day': daily.index[0].date().isoformat(),
        'last_day': daily.index[-1].date().isoformat(),
        'total_return': _finite_expm1(total_log), 'cagr': cagr,
        'log_total_return': total_log,
        'gross_total_return': _finite_expm1(gross_log),
        'gross_cagr': _finite_expm1(gross_log * YEAR_DAYS / elapsed_days),
        'annual_return': annual_return,
        'annual_volatility': annual_volatility,
        'sharpe': sharpe,
        'sortino': sortino,
        'daily_downside_deviation': downside,
        'es95': expected_shortfall(values),
        'worst_day_return': float(values[worst_day]),
        'worst_day_date': daily.index[worst_day].date().isoformat(),
        'worst_7day_return': worst_week_return,
        'worst_7day_start': worst_week_start, 'worst_7day_end': worst_week_end,
        'max_drawdown': drawdown['max_drawdown'],
        'calmar': cagr / drawdown['max_drawdown'] if cagr is not None and drawdown['max_drawdown'] > 0 else None,
        'total_turnover': trades, 'mean_daily_turnover': trades / elapsed_days,
        'annualized_turnover': trades / elapsed_days * YEAR_DAYS,
        'entry_liquidation_included_if_present_in_input': True,
        'daily_win_rate': float(np.mean(values > 0)),
        'daily_gain_loss_ratio': gains / losses if losses > 0 else None,
        'drawdown': drawdown,
        'break_even': break_even_cost_bps(gross_return, turnover),
        'bootstrap': bootstrap_daily(daily, elapsed_days, indices=bootstrap_plan,
                                     samples=bootstrap_samples,
                                     block_days=bootstrap_block_days, seed=bootstrap_seed),
        'exposures': exposure_summary,
        'definitions': {
            'daily_return': 'UTC interval-days; midnight endpoint belongs to preceding day; each day covers 24h',
            'year_days': YEAR_DAYS, 'sharpe': 'daily arithmetic mean / sample SD * sqrt(365), risk-free zero',
            'sortino': 'MAR zero; downside sqrt(mean(min(daily_net,0)^2)) over ALL days, *sqrt(365)',
            'es95': 'signed daily net lower-tail mean, exact fractional worst 5% probability mass',
            'calmar': 'actual elapsed-time CAGR / full-period observed-endpoint max drawdown; undefined for zero DD',
            'turnover': 'full-L1 supplied target changes; do not halve fees or exclude cash days',
            'daily_gain_loss_ratio': 'sum positive daily net returns / absolute sum negative daily net returns; NOT trade profit factor',
            'trade_profit_factor': 'not reported: no unambiguous aggregate-portfolio trade grouping',
            'uncertainty': 'nominal dependence-aware intervals; NOT adjusted for model/parameter search',
            'rolling': 'trailing 90 contiguous UTC days; contemporaneous benchmark OLS, alpha=365*intercept',
            'drawdown_observation': 'observed endpoints only; intrabar/halt interior paths unobserved',
        },
    }
    summary['rolling'] = rolling_diagnostics(daily, benchmark_daily=benchmark_daily) if include_rolling else None
    return summary

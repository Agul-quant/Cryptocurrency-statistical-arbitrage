"""Chronological research pipeline with a persisted pre-test selection receipt."""
from __future__ import annotations

import hashlib
import json
import platform
import tomllib
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import numpy as np
import pandas as pd


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, value: dict) -> None:
    def clean(obj):
        if isinstance(obj, dict):
            return {str(k): clean(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [clean(v) for v in obj]
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (float, np.floating)):
            return float(obj) if np.isfinite(obj) else None
        if isinstance(obj, (pd.Timestamp, Path)):
            return str(obj)
        return obj
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(clean(value), indent=2, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(path)


def load_config(path: Path) -> dict:
    with path.open("rb") as stream:
        config = tomllib.load(stream)
    names = ["development", "validation", "test"]
    splits = config["splits"]
    for name in names:
        if pd.Timestamp(splits[name]["start"]) >= pd.Timestamp(splits[name]["end"]):
            raise ValueError(f"Invalid {name} date window")
    for previous, following in zip(names, names[1:]):
        if splits[previous]["end"] != splits[following]["start"]:
            raise ValueError("Research splits must be contiguous and chronological")
    if config["research"]["primary_cost_bps"] != 20:
        raise ValueError("The course's primary market-order cost must remain 20 bps")
    return config


def experiment_grid(config: dict) -> list[dict]:
    research = config["research"]
    return [
        {"strategy_id": f"{family}_h{h:03d}_r{r:02d}", "family": family,
         "lookback_h": h, "rebalance_h": r}
        for family in ["momentum", "reversal"]
        for h in research[f"{family}_lookbacks"]
        for r in research["rebalance_hours"]
    ]


def select_strategies(experiments: pd.DataFrame) -> tuple[list[dict], bool]:
    """Use validation rows only; never infer selections from test performance."""
    validation = experiments.loc[experiments["split"].eq("validation")].copy()
    validation["sharpe"] = pd.to_numeric(validation["sharpe"], errors="coerce")
    selected = []
    for family in ["momentum", "reversal"]:
        candidates = validation.loc[validation["family"].eq(family)]
        candidates = candidates.loc[np.isfinite(candidates["sharpe"])]
        if candidates.empty:
            raise ValueError(f"No defined validation Sharpe for {family}")
        best = candidates.sort_values(
            ["sharpe", "mean_hourly_turnover", "strategy_id"],
            ascending=[False, True, True], kind="stable",
        ).iloc[0]
        selected.append({
            "strategy_id": str(best["strategy_id"]), "family": family,
            "lookback_h": int(best["lookback_h"]), "rebalance_h": int(best["rebalance_h"]),
            "validation_net_sharpe": float(best["sharpe"]),
            "validation_annual_return": float(best["annual_return"]),
            "validation_mean_hourly_turnover": float(best["mean_hourly_turnover"]),
        })
    eligible = all(s["validation_net_sharpe"] > 0 and s["validation_annual_return"] > 0 for s in selected)
    return selected, eligible


def activity_ratio(quote_volume: pd.DataFrame, lookback_h: int = 168) -> pd.Series:
    """Current completed-hour activity relative to strictly previous volume."""
    prior = quote_volume.shift(1).rolling(lookback_h, min_periods=lookback_h).mean()
    ratios = quote_volume.div(prior.where(prior > 0))
    return ratios.mean(axis=1, skipna=False).rename("activity_ratio")


def activity_diagnostics(result, activity: pd.Series, threshold: float,
                         rebalance_h: int, execution_lag: int, halt_bridges: list | None = None) -> list[dict]:
    decisions = (activity.index.hour % rebalance_h) == 0
    for bridge in halt_bridges or []:
        begin, finish = pd.Timestamp(bridge["start"]), pd.Timestamp(bridge["end"])
        decisions &= ~((activity.index > begin) & (activity.index < finish))
    # Reindex decision observations, retaining unknown values at actual decisions.
    # Ordinary ffill() would silently replace unknown current volume with stale data.
    held_activity = activity.loc[decisions].reindex(activity.index, method="ffill").shift(execution_lag)
    for bridge in halt_bridges or []:
        begin, finish = pd.Timestamp(bridge["start"]), pd.Timestamp(bridge["end"])
        signal_time = begin - pd.Timedelta(hours=execution_lag - 1)
        if finish in held_activity.index and signal_time in activity.index:
            held_activity.loc[finish] = activity.loc[decisions].reindex([signal_time], method="ffill").iloc[0]
    held_activity = held_activity.reindex(result.frame.index)
    active = result.held_weights.abs().sum(axis=1) > 0
    durations = result.frame.get("interval_hours", pd.Series(1.0, index=result.frame.index))
    elapsed_hours = float(durations.sum())
    rows = []
    for regime, mask in [("high", held_activity >= threshold), ("low", held_activity < threshold),
                         ("unknown", held_activity.isna())]:
        frame = result.frame.loc[mask]
        n_hours = float(durations.loc[mask].sum())
        one_hour = frame.loc[durations.loc[mask].eq(1)]
        rows.append({
            "activity_regime": regime, "n_hours": int(n_hours), "n_observations": len(frame),
            "exposure_share": n_hours / elapsed_hours,
            "active_share_within_regime": float(active.loc[mask].mean()) if len(frame) else np.nan,
            "mean_hourly_net_return": float(frame["net_return"].sum() / n_hours) if n_hours else np.nan,
            "std_hourly_net_return": float(one_hour["net_return"].std(ddof=1)),
            "mean_hourly_gross_return": float(frame["gross_return"].sum() / n_hours) if n_hours else np.nan,
            "mean_hourly_turnover": float(frame["turnover"].sum() / n_hours) if n_hours else np.nan,
            "mean_activity_ratio": float(held_activity.loc[mask].mean()),
            "non_hourly_observations": int((durations.loc[mask] != 1).sum()),
        })
    return rows


def environment_versions() -> dict:
    result = {"python": platform.python_version()}
    for package in ["numpy", "pandas", "scipy", "statsmodels", "requests", "pyarrow", "matplotlib",
                    "reportlab", "nbformat", "nbclient", "nbconvert", "pytest"]:
        try:
            result[package] = version(package)
        except PackageNotFoundError:
            result[package] = None
    return result


def run_research(root: Path, config: dict) -> dict:
    from .backtest import generate_targets, simulate, observed_asset_returns
    from .data import load_panel
    from .metrics import summarize

    output = root / "outputs"
    output.mkdir(parents=True, exist_ok=True)
    started = utc_now()
    close, quote_volume, audit = load_panel(root)
    splits = config["splits"]
    research = config["research"]
    primary_cost = research["primary_cost_bps"]
    primary_lag = research["primary_execution_lag"]
    config_hash = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    # Development / validation computation sees no prices after the validation boundary.
    validation_end = pd.Timestamp(splits["validation"]["end"], tz="UTC")
    development_prices = close.loc[close.index <= validation_end]
    development_volume = quote_volume.loc[quote_volume.index <= validation_end]
    development_btc = observed_asset_returns(development_prices)["BTCUSDT"]
    grid = experiment_grid(config)
    rows = []
    for number, experiment in enumerate(grid, 1):
        targets = generate_targets(development_prices, experiment["family"],
                                   experiment["lookback_h"], experiment["rebalance_h"])
        for split_name in ["development", "validation"]:
            split = splits[split_name]
            result = simulate(development_prices, targets, split["start"], split["end"], primary_cost, primary_lag)
            gross_result = simulate(development_prices, targets, split["start"], split["end"], 0, primary_lag)
            summary = summarize(result, development_btc)
            gross_summary = summarize(gross_result, development_btc)
            rows.append({**experiment, "split": split_name, "cost_bps": primary_cost,
                         "execution_lag": primary_lag, **summary,
                         **{f"gross_{k}": gross_summary[k] for k in ["total_return", "cagr", "annual_return",
                                                                     "annual_volatility", "sharpe", "max_drawdown"]}})
        print(f"Development/validation {number:02d}/{len(grid)}: {experiment['strategy_id']}", flush=True)
    experiments = pd.DataFrame(rows)
    experiments_path = output / "experiments.csv"
    experiments.to_csv(experiments_path, index=False, float_format="%.17g")
    selected, combination_eligible = select_strategies(experiments)
    dev_activity = activity_ratio(development_volume, research["activity_lookback_hours"])
    development_mask = (dev_activity.index > pd.Timestamp(splits["development"]["start"], tz="UTC")) & (
        dev_activity.index <= pd.Timestamp(splits["development"]["end"], tz="UTC"))
    threshold = float(dev_activity.loc[development_mask].median())
    if not np.isfinite(threshold):
        raise ValueError("Undefined development-only activity threshold")
    selection = {
        "selection_timestamp_utc": utc_now(),
        "selection_rule": "Highest 2024 net daily Sharpe at 20 bps; ties: lower hourly turnover, then experiment ID",
        "selected": selected, "primary_cost_bps": primary_cost, "primary_execution_lag": primary_lag,
        "combination_eligible": combination_eligible,
        "combination_weights": {s["strategy_id"]: 0.5 for s in selected} if combination_eligible else {},
        "config_sha256": config_hash, "selection_evidence_sha256": sha256_file(experiments_path),
        "activity_threshold": threshold, "development_end": splits["development"]["end"],
        "validation_end": splits["validation"]["end"], "test_start": splits["test"]["start"],
        "test_evaluated_before_selection": False,
    }
    selection_path = output / "selection.json"
    if selection_path.exists():
        previous = json.loads(selection_path.read_text())
        for field in ["config_sha256", "selection_evidence_sha256", "selected", "combination_eligible", "activity_threshold"]:
            if previous[field] != selection[field]:
                raise ValueError(f"Existing frozen selection differs in {field}; preserve it and investigate before rerunning")
        selection = previous
    else:
        write_json(selection_path, selection)
    # This receipt is on disk BEFORE any 2025 strategy-return calculation below.
    test_started = utc_now()
    print("Selection frozen before test:", json.dumps(selection["selected"]), flush=True)
    full_btc = observed_asset_returns(close)["BTCUSDT"]
    full_activity = activity_ratio(quote_volume, research["activity_lookback_hours"])
    selected_targets = {
        s["strategy_id"]: generate_targets(close, s["family"], s["lookback_h"], s["rebalance_h"])
        for s in selected
    }
    evaluated = [dict(s) for s in selected]
    if combination_eligible:
        selected_targets["combination_50_50"] = sum(0.5 * selected_targets[s["strategy_id"]] for s in selected)
        evaluated.append({"strategy_id": "combination_50_50", "family": "combination", "lookback_h": 0,
                          "rebalance_h": min(s["rebalance_h"] for s in selected)})
    scenarios = [(float(c), primary_lag) for c in research["cost_scenarios_bps"]]
    scenarios.append((float(primary_cost), research["delay_scenario_lag"]))
    final_rows, return_frames, weight_frames, activity_rows, annual_rows = [], [], [], [], []
    for selected_strategy in evaluated:
        sid = selected_strategy["strategy_id"]
        metadata = {k: selected_strategy[k] for k in ["strategy_id", "family", "lookback_h", "rebalance_h"]}
        targets = selected_targets[sid]
        for split_name, split in splits.items():
            gross_results = {}
            for cost, lag in scenarios:
                if lag not in gross_results:
                    gross_results[lag] = simulate(close, targets, split["start"], split["end"], 0, lag)
                result = gross_results[lag] if cost == 0 else simulate(close, targets, split["start"], split["end"], cost, lag)
                summary = summarize(result, full_btc)
                gross_summary = summarize(gross_results[lag], full_btc)
                final_rows.append({**metadata, "split": split_name, "cost_bps": cost, "execution_lag": lag, **summary,
                                   **{f"gross_{k}": gross_summary[k] for k in ["total_return", "cagr", "annual_return",
                                                                               "annual_volatility", "sharpe", "max_drawdown"]}})
                frame = result.frame.rename_axis("bar_end").reset_index()
                frame["strategy_id"], frame["split"] = sid, split_name
                frame["cost_bps"], frame["execution_lag"] = cost, lag
                return_frames.append(frame)
                if cost == primary_cost and lag == primary_lag:
                    weights = result.held_weights.rename_axis("bar_end").reset_index().melt(
                        id_vars="bar_end", var_name="symbol", value_name="weight")
                    weights["strategy_id"], weights["split"] = sid, split_name
                    weight_frames.append(weights)
                    diagnostics = activity_diagnostics(result, full_activity, threshold,
                                                        selected_strategy["rebalance_h"], lag,
                                                        close.attrs.get("halt_bridges", []))
                    activity_rows.extend({**metadata, "split": split_name, "cost_bps": cost,
                                          "execution_lag": lag, **d} for d in diagnostics)
            print(f"Frozen evaluation: {sid} / {split_name}", flush=True)
        for year in range(2022, 2026):
            annual = simulate(close, targets, f"{year}-01-01", f"{year + 1}-01-01", primary_cost, primary_lag)
            annual_rows.append({**metadata, "year": year, "cost_bps": primary_cost,
                                "execution_lag": primary_lag, **summarize(annual, full_btc)})
    pd.DataFrame(final_rows).to_csv(output / "final_metrics.csv", index=False, float_format="%.17g")
    pd.concat(return_frames, ignore_index=True).to_parquet(output / "selected_returns.parquet", index=False)
    pd.concat(weight_frames, ignore_index=True).to_parquet(output / "selected_weights.parquet", index=False)
    pd.DataFrame(annual_rows).to_csv(output / "annual_metrics.csv", index=False, float_format="%.17g")
    pd.DataFrame(activity_rows).to_csv(output / "activity_diagnostics.csv", index=False, float_format="%.17g")
    base = Path(__file__).parent
    source_hashes = {name: sha256_file(base / name) for name in ["data.py", "backtest.py", "metrics.py", "runner.py"]}
    manifest = {
        "started_at_utc": started, "selection_frozen_at_utc": selection["selection_timestamp_utc"],
        "test_evaluation_started_at_utc": test_started, "completed_at_utc": utc_now(),
        "config_sha256": config_hash, "selection_sha256": sha256_file(selection_path),
        "data_parquet_sha256": sha256_file(root / "data" / "processed" / "bars.parquet"),
        "source_code_sha256": source_hashes, "environment": environment_versions(),
        "baseline_configurations": len(grid), "development_validation_rows": len(rows),
        "final_metric_rows": len(final_rows), "evaluated_strategies": [s["strategy_id"] for s in evaluated],
        "combination_eligible": combination_eligible, "activity_threshold_development_only": threshold,
        "source_attribution": "Binance Vision public historical spot OHLCV archives",
        "source_documentation": "https://github.com/binance/binance-public-data",
        "dataset_terms": "https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md",
        "research_license": "CC BY-NC-SA 4.0 for dataset-derived materials; educational non-production research only",
        "limitations": ["Purposive fixed survivor sample", "USDT denomination, not USD",
                        "Theoretical shorts without funding, borrowing, margin or capacity constraints",
                        "Idealized close execution with target-weight-change turnover; weight drift omitted",
                        "18 validation comparisons; selected performance is not an unbiased estimate",
                        "Known March 2023 halt uses one invested four-hour observed interval; intra-halt drawdown unknown",
                        "Unknown activity regimes retained where missing source volume prevents a full 168-hour denominator"],
        "data_quality": audit,
    }
    write_json(output / "run_manifest.json", manifest)
    return {"root": str(root), "selected": selected, "combination_eligible": combination_eligible,
            "test_primary_metrics": [r for r in final_rows if r["split"] == "test" and
                                     r["cost_bps"] == primary_cost and r["execution_lag"] == primary_lag],
            "completed_at_utc": manifest["completed_at_utc"]}

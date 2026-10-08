"""Independent checks of research selection and split isolation."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from crypto_stat_arb.runner import activity_ratio, experiment_grid, load_config, select_strategies, write_json


def configuration():
    root = Path(__file__).resolve().parents[1]
    return load_config(root / "configs" / "research.toml")


def candidate(sid, family, sharpe, turnover, split="validation", annual_return=0.1):
    return dict(strategy_id=sid, family=family, sharpe=sharpe, mean_hourly_turnover=turnover,
                split=split, annual_return=annual_return, lookback_h=4, rebalance_h=4)


def test_predeclared_grid():
    grid = experiment_grid(configuration())
    assert len(grid) == 18
    assert len({x["strategy_id"] for x in grid}) == 18
    assert {x["lookback_h"] for x in grid if x["family"] == "reversal"} == {1, 4, 12}
    assert {x["lookback_h"] for x in grid if x["family"] == "momentum"} == {24, 72, 168}


def test_selection_ignores_test_and_development():
    rows = [candidate("m_valid", "momentum", -1, 0.2), candidate("r_valid", "reversal", 0.5, 0.2),
            candidate("m_test_winner", "momentum", 100, 0, "test"),
            candidate("m_train_winner", "momentum", 100, 0, "development")]
    selected, combo = select_strategies(pd.DataFrame(rows))
    assert [x["strategy_id"] for x in selected] == ["m_valid", "r_valid"]
    assert not combo


def test_selection_ties_turnover_then_id():
    rows = [candidate("m_c", "momentum", 1, 0.2), candidate("m_b", "momentum", 1, 0.1),
            candidate("m_a", "momentum", 1, 0.1), candidate("r", "reversal", 1, 0.1)]
    selected, combo = select_strategies(pd.DataFrame(rows))
    assert selected[0]["strategy_id"] == "m_a"
    assert combo


def test_undefined_sharpe_not_selected():
    rows = [candidate("m_na", "momentum", None, 0), candidate("m_valid", "momentum", -1, 0.1),
            candidate("r_valid", "reversal", 0.2, 0.1)]
    assert select_strategies(pd.DataFrame(rows))[0][0]["strategy_id"] == "m_valid"
    with pytest.raises(ValueError, match="momentum"):
        select_strategies(pd.DataFrame([rows[0], rows[2]]))


def test_activity_denominator_excludes_current_volume():
    index = pd.date_range("2022-01-01", periods=8, freq="h", tz="UTC")
    volume = pd.DataFrame({"A": [1.] * 7 + [10.], "B": [2.] * 7 + [20.]}, index=index)
    ratio = activity_ratio(volume, 3)
    assert ratio.iloc[:3].isna().all()
    assert ratio.iloc[-1] == pytest.approx(10)
    assert ratio.iloc[3] == pytest.approx(1)


def test_activity_no_future_leakage():
    index = pd.date_range("2022-01-01", periods=100, freq="h", tz="UTC")
    rng = np.random.default_rng(8)
    volume = pd.DataFrame(rng.uniform(1, 5, (100, 3)), index=index)
    changed = volume.copy()
    changed.iloc[50:] *= 100
    pd.testing.assert_series_equal(activity_ratio(volume, 8).iloc[:50], activity_ratio(changed, 8).iloc[:50])


def test_json_receipt_is_strict_and_atomic(tmp_path):
    target = tmp_path / "selection.json"
    write_json(target, {"metric": np.nan, "n": np.int64(8), "nested": [np.inf, 0.2]})
    assert json.loads(target.read_text()) == {"metric": None, "n": 8, "nested": [None, 0.2]}
    assert not target.with_suffix(".json.tmp").exists()


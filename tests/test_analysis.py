import numpy as np
import pandas as pd
import pytest

from analysis import _max_drawdown, hedge_calculator, optimal_hedge_ratio
from portfolio import compare_out_of_sample, strategy_schedules


def sample(n=140):
    rng = np.random.default_rng(71)
    futures = rng.normal(0, 0.01, n)
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2024-01-01", periods=n),
            "Futures_Return": futures,
            "Spot_Return": 0.8 * futures + rng.normal(0, 0.002, n),
        }
    )


def test_drawdown_counts_loss_before_first_observed_peak():
    assert _max_drawdown(pd.Series([0.9, 0.95, 0.8])) == pytest.approx(-20)


def test_covariance_and_ols_agree():
    d = sample()
    h = optimal_hedge_ratio(d)
    assert h["h_star"] == pytest.approx(h["ols_beta"])


def test_degenerate_fit_has_actionable_error():
    d = sample()
    d["Futures_Return"] = 0
    with pytest.raises(ValueError, match="variance"):
        optimal_hedge_ratio(d)


def test_identical_evaluation_dates_and_prior_only_training():
    d = sample()
    comparison = compare_out_of_sample(d)
    assert comparison["Start"].nunique() == comparison["End"].nunique() == 1
    assert comparison["Observations"].nunique() == 1
    evaluation, schedules, start = strategy_schedules(d)
    altered = d.copy()
    altered.loc[start:, "Spot_Return"] *= 50
    _, changed, _ = strategy_schedules(altered)
    pd.testing.assert_series_equal(schedules["Fixed training h*"], changed["Fixed training h*"])
    assert schedules["Rolling prior-window h*"].iloc[0] == changed["Rolling prior-window h*"].iloc[0]
    assert evaluation.Date.iloc[0] == d.Date.iloc[start]
    assert schedules["Rolling prior-window h*"].iloc[0] == pytest.approx(
        optimal_hedge_ratio(d.iloc[start - 60 : start])["h_star"]
    )


@pytest.mark.parametrize("rounding,lots", [("down", 1), ("nearest", 2)])
def test_lot_rounding(rounding, lots):
    result = hedge_calculator(1500, 100, 100, 10, 1, rounding)
    assert result["number_of_lots"] == lots


def test_small_portfolio_does_not_force_a_lot():
    assert hedge_calculator(100, 100, 100, 10, 1)["number_of_lots"] == 0

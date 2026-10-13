import numpy as np
import pandas as pd
import pytest

from data_cleaning import build_continuous_series, build_master, build_rollover_schedule, legacy_lot_size


def test_expiry_is_taken_from_contract_instead_of_last_thursday():
    calendar = pd.bdate_range("2025-09-01", "2025-10-31")
    futures = pd.DataFrame({"Expiry": pd.to_datetime(["2025-09-30", "2025-11-25"])})
    schedule = build_rollover_schedule(futures, calendar)
    assert schedule.EffectiveExpiry.iloc[0] == pd.Timestamp("2025-09-30")
    assert schedule.RolloverDate.iloc[0] == pd.Timestamp("2025-09-23")
    assert pd.isna(schedule.RolloverDate.iloc[1])


def test_roll_return_uses_same_new_contract_on_both_dates():
    dates = pd.bdate_range("2024-01-01", periods=10)
    expiries = pd.to_datetime(["2024-01-12", "2024-02-29"])
    rows = [
        {"Date": day, "Expiry": expiry, "Close": 100 + i + j * 20, "Lot_Size": 25}
        for i, day in enumerate(dates)
        for j, expiry in enumerate(expiries)
    ]
    futures = pd.DataFrame(rows)
    schedule = build_rollover_schedule(futures, dates)
    continuous = build_continuous_series(futures, schedule)
    master = build_master(pd.DataFrame({"Date": dates, "Spot_Price": 100 + np.arange(10)}), continuous)
    rolled = master[master.Is_Roll_Day].iloc[0]
    assert rolled.Date == schedule.RolloverDate.iloc[0].strftime("%Y-%m-%d")
    assert rolled.Futures_Return == pytest.approx(np.log(rolled.Futures_Price / rolled.Previous_Active_Close))
    assert abs(rolled.Futures_Return) < 0.02


@pytest.mark.parametrize(
    "day,expiry,expected",
    [
        ("2020-01-01", "2020-01-30", 75),
        ("2021-05-01", "2021-06-24", 75),
        ("2021-05-01", "2021-07-29", 50),
        ("2024-04-25", "2024-05-30", 50),
        ("2024-04-26", "2024-05-30", 25),
    ],
)
def test_legacy_lot_changes(day, expiry, expected):
    assert legacy_lot_size(pd.Timestamp(day), pd.Timestamp(expiry)) == expected


def test_misaligned_calendars_are_rejected():
    dates = pd.bdate_range("2024-01-01", periods=10)
    futures = pd.DataFrame(
        {"Date": dates, "Expiry": pd.Timestamp("2024-02-29"), "Close": 101 + np.arange(10), "Lot_Size": 25}
    )
    continuous = build_continuous_series(futures, build_rollover_schedule(futures, dates))
    spot = pd.DataFrame({"Date": dates.delete(2), "Spot_Price": np.arange(9) + 100})
    with pytest.raises(ValueError, match="gaps"):
        build_master(spot, continuous)

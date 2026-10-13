import numpy as np
import pandas as pd
import pytest

from portfolio import TradingAssumptions, simulate_portfolio


def ledger_data():
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-05", "2024-01-08"]),
            "Previous_Date": pd.to_datetime(["2024-01-04", "2024-01-05"]),
            "Spot_Price": [90.0, 95.0],
            "Previous_Spot_Price": [100.0, 90.0],
            "Futures_Price": [91.0, 96.0],
            "Previous_Active_Close": [101.0, 91.0],
            "Previous_Lot_Size": [10, 10],
            "Active_Expiry": ["2024-01-25", "2024-01-25"],
        }
    )


ZERO = TradingAssumptions(0, 0, 0, 0)


def test_cash_identity_and_actual_price_change_pnl():
    d = ledger_data()
    ledger = simulate_portfolio(d, [1, 1], 2020, ZERO)
    # 20.2 spot units; two lots short on first day.
    assert ledger.Spot_PnL.iloc[0] == pytest.approx(-202)
    assert ledger.Futures_PnL.iloc[0] == pytest.approx(200)
    np.testing.assert_allclose(ledger.Net_Equity, 2020 + ledger.Net_PnL.cumsum())
    np.testing.assert_allclose(ledger.Cash_Balance, ledger.Futures_PnL.cumsum())
    assert ledger.Lots.iloc[0] == 2


def test_no_hedge_has_no_futures_costs_or_margin():
    ledger = simulate_portfolio(ledger_data(), [0, 0], 2020)
    assert ledger[["Futures_PnL", "Trading_Cost", "Funding_Cost", "Margin_Required"]].to_numpy().sum() == 0
    np.testing.assert_allclose(ledger.Net_Equity, ledger.Spot_Equity)


def test_roll_has_two_transaction_legs_without_fake_price_gap_gain():
    d = ledger_data()
    d.loc[1, "Active_Expiry"] = "2024-02-29"
    d.loc[1, ["Previous_Active_Close", "Futures_Price"]] = [110.0, 115.0]
    ledger = simulate_portfolio(d, [1, 1], 2020, TradingAssumptions(1, 0, 0, 0))
    assert ledger.Futures_PnL.iloc[1] == -50  # One new lot, 110 -> 115.
    assert ledger.Turnover.iloc[1] == 20 * 91 + 10 * 110 + 10 * 115
    assert ledger.Trading_Cost.iloc[1] == pytest.approx(ledger.Turnover.iloc[1] / 10000)
    assert ledger.Is_Roll.iloc[1]


def test_entry_and_final_exit_are_both_charged():
    ledger = simulate_portfolio(ledger_data().iloc[:1], [1], 2020, TradingAssumptions(1, 1, 0, 0))
    assert ledger.Trading_Cost.iloc[0] == pytest.approx((20 * 101 + 20 * 91) * 0.0002)


def test_margin_principal_is_not_a_loss_and_weekend_funding_counts():
    ledger = simulate_portfolio(ledger_data(), [1, 1], 2020, TradingAssumptions(0, 0, 0.1, 0.365))
    assert ledger.Funding_Cost.iloc[1] == pytest.approx(ledger.Margin_Required.iloc[1] * 0.003)
    assert ledger.Net_PnL.iloc[0] == pytest.approx(
        ledger.Spot_PnL.iloc[0] + ledger.Futures_PnL.iloc[0] - ledger.Funding_Cost.iloc[0]
    )


def test_historical_multiplier_is_used():
    d = ledger_data()
    d.loc[0, "Previous_Lot_Size"] = 25
    ledger = simulate_portfolio(d, [1, 1], 10100, ZERO)
    assert ledger.Lot_Size.iloc[0] == 25
    assert ledger.Futures_PnL.iloc[0] == ledger.Lots.iloc[0] * 25 * 10


def test_invalid_or_gapped_prices_are_rejected():
    d = ledger_data()
    d.loc[1, "Previous_Date"] = pd.Timestamp("2024-01-04")
    with pytest.raises(ValueError, match="contiguous"):
        simulate_portfolio(d, [1, 1], 2020, ZERO)

"""Whole-lot, close-marked futures ledger and fair out-of-sample comparisons.

The spot holding is a fixed number of NIFTY index-equivalent units. Futures
are rebalanced at the preceding close, before the return being evaluated.
Margin is externally funded collateral; it is not deducted as a loss.
This is a transparent scenario, not an exchange settlement/margin replica.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from analysis import _max_drawdown, _performance_metrics, optimal_hedge_ratio


@dataclass(frozen=True)
class TradingAssumptions:
    fee_bps: float = 1.0
    slippage_bps: float = 1.0
    margin_fraction: float = 0.12
    annual_funding_rate: float = 0.08
    rounding: str = "down"

    def validate(self):
        for name in ("fee_bps", "slippage_bps", "margin_fraction", "annual_funding_rate"):
            value = getattr(self, name)
            if not np.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if self.margin_fraction > 1:
            raise ValueError("margin_fraction cannot exceed 1")
        if self.rounding not in {"down", "nearest"}:
            raise ValueError("rounding must be down or nearest")


def strategy_schedules(master, window=60, train_frac=0.5):
    """All four strategies share identical evaluation dates and a prior-only fit."""
    if not isinstance(window, int) or window < 2:
        raise ValueError("window must be an integer of at least 2")
    if not 0 < train_frac < 1:
        raise ValueError("train_frac must be between 0 and 1")
    d = master.sort_values("Date").reset_index(drop=True).copy()
    if d["Date"].duplicated().any():
        raise ValueError("Duplicate dates are not allowed")
    start = max(int(len(d) * train_frac), window)
    if len(d) - start < 2:
        raise ValueError("Not enough observations for a common out-of-sample test")
    fixed = optimal_hedge_ratio(d.iloc[:start])["h_star"]
    rolling = (
        d["Spot_Return"].rolling(window).cov(d["Futures_Return"]) / d["Futures_Return"].rolling(window).var()
    ).shift(1)
    evaluation = d.iloc[start:].reset_index(drop=True)
    schedules = {
        "No hedge": pd.Series(0.0, index=evaluation.index),
        "One-for-one": pd.Series(1.0, index=evaluation.index),
        "Fixed training h*": pd.Series(fixed, index=evaluation.index),
        "Rolling prior-window h*": rolling.iloc[start:].reset_index(drop=True),
    }
    if not all(np.isfinite(h).all() for h in schedules.values()):
        raise ValueError("A training window has zero variance or invalid returns")
    return evaluation, schedules, start


def compare_out_of_sample(master, window=60, train_frac=0.5):
    """Statistical log-return comparison; deliberately excludes any hindsight fit."""
    d, schedules, _ = strategy_schedules(master, window, train_frac)
    rows = []
    for name, h in schedules.items():
        metrics = _performance_metrics(d["Spot_Return"], d["Spot_Return"] - h * d["Futures_Return"])
        rows.append(
            {
                "Strategy": name,
                "Mean hedge ratio": h.mean(),
                "Start": str(d["Date"].iloc[0])[:10],
                "End": str(d["Date"].iloc[-1])[:10],
                "Observations": len(d),
                "Annualized volatility": metrics["vol_hedged_annualized"],
                "Max drawdown (%)": metrics["max_drawdown_hedged"],
                "Variance reduction (%)": metrics["hedging_effectiveness_pct"],
            }
        )
    return pd.DataFrame(rows)


def simulate_portfolio(master, hedge_ratios, amount=2_500_000.0, assumptions=None):
    """Buy-and-hold spot plus short futures, with entry/roll/rebalance/exit costs.

    Daily cash = short units * (previous same-contract close - today's close)
    minus costs. Final futures liquidation is charged on the last day. Futures
    notional is not invested cash. Whole lots use the preceding session's lot
    size; changes in contract multipliers are treated as quantity changes.
    """
    assumptions = assumptions or TradingAssumptions()
    assumptions.validate()
    required = [
        "Spot_Price",
        "Futures_Price",
        "Previous_Spot_Price",
        "Previous_Active_Close",
        "Previous_Lot_Size",
    ]
    d = master.reset_index(drop=True).copy()
    missing = set(required + ["Date", "Previous_Date", "Active_Expiry"]) - set(d.columns)
    if missing:
        raise ValueError(f"Rebuild the master dataset; missing fields: {sorted(missing)}")
    dates = pd.to_datetime(d["Date"])
    previous_dates = pd.to_datetime(d["Previous_Date"])
    if d.empty or dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError("Portfolio dates must be unique and ordered")
    if not previous_dates.iloc[1:].reset_index(drop=True).equals(dates.iloc[:-1].reset_index(drop=True)):
        raise ValueError("Portfolio sessions must be contiguous")
    if (dates <= previous_dates).any():
        raise ValueError("Previous_Date must precede Date")
    if not np.isfinite(amount) or amount <= 0:
        raise ValueError("amount must be positive and finite")
    if not np.isfinite(d[required]).all().all() or (d[required] <= 0).any().any():
        raise ValueError("Portfolio prices and lot sizes must be positive and finite")
    if (d["Previous_Lot_Size"] % 1 != 0).any():
        raise ValueError("Historical lot sizes must be whole units")
    h = np.asarray(hedge_ratios, dtype=float)
    if h.ndim != 1 or len(h) != len(d) or not np.isfinite(h).all() or (h < 0).any():
        raise ValueError("One finite non-negative prior hedge ratio is required per session")
    units = amount / d["Previous_Spot_Price"].iloc[0]
    cash = 0.0
    old_units = 0
    old_expiry = None
    last_close = 0.0
    rows = []
    rate = (assumptions.fee_bps + assumptions.slippage_bps) / 10_000
    for i, row in d.iterrows():
        prior_price = row["Previous_Active_Close"]
        lot_size = int(row["Previous_Lot_Size"])
        desired_lots = h[i] * units * row["Previous_Spot_Price"] / (prior_price * lot_size)
        lots = int(np.floor(desired_lots) if assumptions.rounding == "down" else np.floor(desired_lots + 0.5))
        short_units = lots * lot_size
        expiry = str(row["Active_Expiry"])
        rolled = old_expiry is not None and expiry != old_expiry
        turnover = (
            old_units * last_close + short_units * prior_price
            if rolled
            else abs(short_units - old_units) * prior_price
        )
        margin = short_units * prior_price * assumptions.margin_fraction
        days = (dates.iloc[i] - previous_dates.iloc[i]).days
        funding = margin * assumptions.annual_funding_rate * days / 365
        trading_cost = turnover * rate
        futures_pnl = short_units * (prior_price - row["Futures_Price"])
        if i == len(d) - 1:
            exit_turnover = short_units * row["Futures_Price"]
            turnover += exit_turnover
            trading_cost += exit_turnover * rate
        net_cash = futures_pnl - trading_cost - funding
        cash += net_cash
        spot_pnl = units * (row["Spot_Price"] - row["Previous_Spot_Price"])
        spot_value = units * row["Spot_Price"]
        rows.append(
            {
                "Date": dates.iloc[i],
                "Active_Expiry": expiry,
                "Hedge_Ratio": h[i],
                "Lot_Size": lot_size,
                "Lots": lots,
                "Spot_Units": units,
                "Spot_PnL": spot_pnl,
                "Futures_PnL": futures_pnl,
                "Turnover": turnover,
                "Trading_Cost": trading_cost,
                "Funding_Cost": funding,
                "Net_PnL": spot_pnl + net_cash,
                "Cash_Balance": cash,
                "Margin_Required": margin,
                "Spot_Equity": spot_value,
                "Net_Equity": spot_value + cash,
                "Is_Roll": rolled,
            }
        )
        old_units, old_expiry, last_close = short_units, expiry, row["Futures_Price"]
    ledger = pd.DataFrame(rows)
    previous_equity = ledger["Net_Equity"].shift(1).fillna(amount)
    if (previous_equity <= 0).any() or (ledger["Net_Equity"] <= 0).any():
        raise ValueError("Portfolio exhausted its equity; simple-return metrics are undefined")
    ledger["Net_Return"] = ledger["Net_PnL"] / previous_equity
    ledger["Spot_Simple_Return"] = ledger["Spot_PnL"] / ledger["Spot_Equity"].shift(1).fillna(amount)
    peak = ledger["Net_Equity"].cummax().clip(lower=amount)
    ledger["Drawdown_Rupees"] = ledger["Net_Equity"] - peak
    return ledger


def portfolio_summary(ledger, amount):
    variance = ledger["Net_Return"].var()
    unhedged_variance = ledger["Spot_Simple_Return"].var()
    return {
        "Net profit (₹)": ledger["Net_Equity"].iloc[-1] - amount,
        "Annualized volatility": ledger["Net_Return"].std() * np.sqrt(252),
        "Max drawdown (%)": _max_drawdown(ledger["Net_Equity"] / amount),
        "Variance reduction (%)": (1 - variance / unhedged_variance) * 100
        if unhedged_variance > 0
        else np.nan,
        "Trading costs (₹)": ledger["Trading_Cost"].sum(),
        "Funding costs (₹)": ledger["Funding_Cost"].sum(),
        "Peak margin (₹)": ledger["Margin_Required"].max(),
        "Peak cash deficit (₹)": max(0.0, -ledger["Cash_Balance"].min()),
        "Peak external cash needed (₹)": (ledger["Margin_Required"] - ledger["Cash_Balance"])
        .clip(lower=0)
        .max(),
    }


def compare_portfolios(master, amount=2_500_000.0, assumptions=None, window=60, train_frac=0.5):
    evaluation, schedules, training_rows = strategy_schedules(master, window, train_frac)
    ledgers, rows = {}, []
    for name, h in schedules.items():
        ledger = simulate_portfolio(evaluation, h, amount, assumptions)
        ledgers[name] = ledger
        rows.append({"Strategy": name, "Observations": len(ledger), **portfolio_summary(ledger, amount)})
    return pd.DataFrame(rows), ledgers, training_rows

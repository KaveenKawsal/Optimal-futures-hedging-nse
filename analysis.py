"""
analysis.py — Core financial analysis functions for the NIFTY hedging project.

Pure functions only (no Streamlit / plotting) so they can be unit-tested,
called from a notebook, or reused by app.py.

Expects a "master" DataFrame with columns:
    Date, Spot_Price, Futures_Price, Spot_Return, Futures_Return, Basis
as produced by data_cleaning.py.
"""

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Descriptive statistics
# ---------------------------------------------------------------------------


def descriptive_stats(master: pd.DataFrame) -> pd.DataFrame:
    """
    Per-series descriptive stats for Spot_Return and Futures_Return:
    mean, std, variance, min, max, skew, kurtosis, annualized vol.

    Annualization assumes ~252 trading days/year (standard convention).
    """
    rows = []
    for col, label in [("Spot_Return", "Spot"), ("Futures_Return", "Futures")]:
        s = master[col].dropna()
        rows.append(
            {
                "Series": label,
                "Mean (daily)": s.mean(),
                "Std Dev (daily)": s.std(),
                "Variance (daily)": s.var(),
                "Min": s.min(),
                "Max": s.max(),
                "Skewness": s.skew(),
                "Kurtosis": s.kurtosis(),
                "Annualized Vol": s.std() * np.sqrt(252),
            }
        )
    return pd.DataFrame(rows).set_index("Series")


def spot_futures_relationship(master: pd.DataFrame) -> dict:
    """Correlation, covariance, and basis summary between spot and futures."""
    aligned = master.dropna(subset=["Spot_Return", "Futures_Return"])

    return {
        "correlation": aligned["Spot_Return"].corr(aligned["Futures_Return"]),
        "covariance": aligned["Spot_Return"].cov(aligned["Futures_Return"]),
        "basis_mean": master["Basis"].mean(),
        "basis_std": master["Basis"].std(),
        "basis_min": master["Basis"].min(),
        "basis_max": master["Basis"].max(),
        "pct_days_contango": (master["Basis"] > 0).mean() * 100,  # futures > spot
        "pct_days_backwardation": (master["Basis"] < 0).mean() * 100,
    }


# ---------------------------------------------------------------------------
# Analysis 1 — Optimal Hedge Ratio
# ---------------------------------------------------------------------------


def optimal_hedge_ratio(master: pd.DataFrame) -> dict:
    """
    Minimum-variance optimal hedge ratio:
        h* = Cov(R_spot, R_futures) / Var(R_futures)

    This is mathematically identical to the OLS slope coefficient of
    regressing Spot_Return on Futures_Return, which is included here as a
    cross-check (and gives R^2, useful for the report).
    """
    aligned = master.dropna(subset=["Spot_Return", "Futures_Return"])
    if len(aligned) < 2 or not np.isfinite(aligned[["Spot_Return", "Futures_Return"]]).all().all():
        raise ValueError("At least two finite paired returns are required")
    rs = aligned["Spot_Return"]
    rf = aligned["Futures_Return"]

    cov_sf = rs.cov(rf)
    var_f = rf.var()
    if var_f <= 0 or rs.var() <= 0:
        raise ValueError("Spot and futures returns must both have positive variance")
    h_star = cov_sf / var_f

    # OLS cross-check: Spot_Return = alpha + beta * Futures_Return
    beta, alpha = np.polyfit(rf, rs, deg=1)
    y_pred = alpha + beta * rf
    ss_res = np.sum((rs - y_pred) ** 2)
    ss_tot = np.sum((rs - rs.mean()) ** 2)
    r_squared = 1 - ss_res / ss_tot

    return {
        "cov_spot_futures": cov_sf,
        "var_futures": var_f,
        "h_star": h_star,
        "ols_beta": beta,
        "ols_alpha": alpha,
        "r_squared": r_squared,
        "n_obs": len(aligned),
    }


# ---------------------------------------------------------------------------
# Analysis 2 — Hedging Effectiveness
# ---------------------------------------------------------------------------


def hedging_effectiveness(master: pd.DataFrame, h_star: float) -> dict:
    """
    Build the hedged return series using h_star, compare variance/volatility
    against the unhedged (spot-only) position.

        Hedged_Return = Spot_Return - h_star * Futures_Return

    HE = 1 - Var(Hedged) / Var(Unhedged)
    """
    aligned = master.dropna(subset=["Spot_Return", "Futures_Return"]).copy()
    aligned["Hedged_Return"] = aligned["Spot_Return"] - h_star * aligned["Futures_Return"]

    var_unhedged = aligned["Spot_Return"].var()
    var_hedged = aligned["Hedged_Return"].var()
    he = 1 - (var_hedged / var_unhedged)

    vol_unhedged = aligned["Spot_Return"].std()
    vol_hedged = aligned["Hedged_Return"].std()

    # Returns are logarithmic, so cumulative wealth is exp(cumulative log return).
    aligned["Cum_Unhedged"] = np.exp(aligned["Spot_Return"].cumsum())
    aligned["Cum_Hedged"] = np.exp(aligned["Hedged_Return"].cumsum())

    return {
        "var_unhedged": var_unhedged,
        "var_hedged": var_hedged,
        "vol_unhedged_daily": vol_unhedged,
        "vol_hedged_daily": vol_hedged,
        "vol_unhedged_annualized": vol_unhedged * np.sqrt(252),
        "vol_hedged_annualized": vol_hedged * np.sqrt(252),
        "hedging_effectiveness_pct": he * 100,
        "max_drawdown_unhedged": _max_drawdown(aligned["Cum_Unhedged"]),
        "max_drawdown_hedged": _max_drawdown(aligned["Cum_Hedged"]),
        "series": aligned[
            ["Date", "Spot_Return", "Futures_Return", "Hedged_Return", "Cum_Unhedged", "Cum_Hedged"]
        ],
    }


def _max_drawdown(cum_series: pd.Series) -> float:
    """Maximum peak-to-trough decline of a cumulative return series, as a %."""
    running_max = cum_series.cummax().clip(lower=1.0)
    drawdown = (cum_series - running_max) / running_max
    return drawdown.min() * 100


def _performance_metrics(unhedged: pd.Series, hedged: pd.Series) -> dict:
    """Return comparable risk metrics for two aligned log-return series."""
    var_unhedged = unhedged.var()
    var_hedged = hedged.var()
    cum_unhedged = np.exp(unhedged.cumsum())
    cum_hedged = np.exp(hedged.cumsum())

    return {
        "var_unhedged": var_unhedged,
        "var_hedged": var_hedged,
        "vol_unhedged_annualized": unhedged.std() * np.sqrt(252),
        "vol_hedged_annualized": hedged.std() * np.sqrt(252),
        "hedging_effectiveness_pct": (1 - var_hedged / var_unhedged) * 100,
        "max_drawdown_unhedged": _max_drawdown(cum_unhedged),
        "max_drawdown_hedged": _max_drawdown(cum_hedged),
        "cum_unhedged": cum_unhedged,
        "cum_hedged": cum_hedged,
    }


def out_of_sample_hedge(master: pd.DataFrame, train_frac: float = 0.5) -> dict:
    """Estimate h* on the first sample portion and evaluate it on the rest."""
    if not 0 < train_frac < 1:
        raise ValueError("train_frac must be between 0 and 1")

    aligned = master.dropna(subset=["Spot_Return", "Futures_Return"]).sort_values("Date").copy()
    split = int(len(aligned) * train_frac)
    if split < 2 or len(aligned) - split < 2:
        raise ValueError("Not enough observations for the requested train/test split")

    train = aligned.iloc[:split]
    test = aligned.iloc[split:].copy()
    hedge = optimal_hedge_ratio(train)
    test["Hedged_Return"] = test["Spot_Return"] - hedge["h_star"] * test["Futures_Return"]
    metrics = _performance_metrics(test["Spot_Return"], test["Hedged_Return"])

    return {
        "h_star": hedge["h_star"],
        "train_frac": train_frac,
        "n_train": len(train),
        "n_test": len(test),
        **{key: value for key, value in metrics.items() if not key.startswith("cum_")},
        "series": test[["Date", "Spot_Return", "Futures_Return", "Hedged_Return"]].assign(
            Cum_Unhedged=metrics["cum_unhedged"].values,
            Cum_Hedged=metrics["cum_hedged"].values,
        ),
    }


def rolling_out_of_sample(master: pd.DataFrame, window: int = 60) -> dict:
    """Use each prior rolling window to hedge the following day's return."""
    if window < 2:
        raise ValueError("window must be at least 2")

    aligned = master.dropna(subset=["Spot_Return", "Futures_Return"]).sort_values("Date").copy()
    if len(aligned) <= window:
        raise ValueError("Not enough observations for the requested rolling window")

    rows = []
    for index in range(window, len(aligned)):
        train = aligned.iloc[index - window : index]
        hedge = optimal_hedge_ratio(train)
        current = aligned.iloc[index]
        rows.append(
            {
                "Date": current["Date"],
                "Spot_Return": current["Spot_Return"],
                "Futures_Return": current["Futures_Return"],
                "Hedge_Ratio": hedge["h_star"],
                "Hedged_Return": current["Spot_Return"] - hedge["h_star"] * current["Futures_Return"],
            }
        )

    series = pd.DataFrame(rows)
    metrics = _performance_metrics(series["Spot_Return"], series["Hedged_Return"])
    series["Cum_Unhedged"] = metrics["cum_unhedged"].values
    series["Cum_Hedged"] = metrics["cum_hedged"].values

    return {
        "window": window,
        "n_obs": len(series),
        "mean_h_star": series["Hedge_Ratio"].mean(),
        **{key: value for key, value in metrics.items() if not key.startswith("cum_")},
        "series": series,
    }


def compare_hedges(master: pd.DataFrame) -> pd.DataFrame:
    """Compare full-sample h*, a one-for-one hedge, and no hedge."""
    aligned = master.dropna(subset=["Spot_Return", "Futures_Return"]).copy()
    full_sample_h = optimal_hedge_ratio(aligned)["h_star"]
    strategies = [
        ("h* (full sample)", full_sample_h),
        ("h = 1 (naive)", 1.0),
        ("No hedge", 0.0),
    ]

    rows = []
    for name, hedge_ratio in strategies:
        hedged = aligned["Spot_Return"] - hedge_ratio * aligned["Futures_Return"]
        metrics = _performance_metrics(aligned["Spot_Return"], hedged)
        rows.append(
            {
                "Strategy": name,
                "Hedge Ratio": hedge_ratio,
                "Variance": metrics["var_hedged"],
                "Annualized Volatility": metrics["vol_hedged_annualized"],
                "Max Drawdown": metrics["max_drawdown_hedged"],
                "Hedging Effectiveness (%)": metrics["hedging_effectiveness_pct"],
            }
        )

    return pd.DataFrame(rows)


def hedge_calculator(
    amount: float,
    spot_price: float,
    futures_price: float,
    lot_size: float,
    h_star: float,
    rounding: str = "down",
) -> dict:
    """Calculate whole-lot futures sizing for a rupee spot exposure.

    ``rounding="down"`` avoids over-hedging; ``rounding="nearest"`` selects
    the closest whole lot. The first five arguments remain compatible with
    existing callers.
    """
    values = {
        "amount": amount,
        "spot_price": spot_price,
        "futures_price": futures_price,
        "lot_size": lot_size,
    }
    for name, value in values.items():
        if not np.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be a positive finite number")
    if not np.isfinite(h_star) or h_star < 0:
        raise ValueError("h_star must be a non-negative finite number")
    if rounding not in {"down", "nearest"}:
        raise ValueError("rounding must be 'down' or 'nearest'")

    futures_notional_to_short = amount * h_star
    notional_per_lot = futures_price * lot_size
    unrounded_lots = futures_notional_to_short / notional_per_lot
    if rounding == "down":
        number_of_lots = int(np.floor(unrounded_lots))
    else:
        number_of_lots = int(np.floor(unrounded_lots + 0.5))
    actual_hedged_notional = number_of_lots * notional_per_lot
    hedge_difference = actual_hedged_notional - futures_notional_to_short

    return {
        "futures_notional_to_short": futures_notional_to_short,
        "notional_per_lot": notional_per_lot,
        "unrounded_lots": unrounded_lots,
        "number_of_lots": number_of_lots,
        "actual_hedged_notional": actual_hedged_notional,
        "hedge_difference": hedge_difference,
        "rounding": rounding,
        # Kept as a compatibility alias for earlier callers.
        "leftover_unhedged_amount": amount - actual_hedged_notional,
    }


# ---------------------------------------------------------------------------
# Rolling hedge ratio (optional extra — shows adaptivity over time)
# ---------------------------------------------------------------------------


def rolling_hedge_ratio(master: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    """
    Rolling-window estimate of h* to show how the optimal hedge ratio
    drifts over time, rather than assuming it's constant across the sample.
    """
    aligned = master.dropna(subset=["Spot_Return", "Futures_Return"]).copy()
    roll_cov = aligned["Spot_Return"].rolling(window).cov(aligned["Futures_Return"])
    roll_var = aligned["Futures_Return"].rolling(window).var()
    aligned["Rolling_H_Star"] = roll_cov / roll_var
    return aligned[["Date", "Rolling_H_Star"]].dropna()


# ---------------------------------------------------------------------------
# Convenience: run everything and produce the final summary conclusion
# ---------------------------------------------------------------------------


def run_full_analysis(master: pd.DataFrame) -> dict:
    desc = descriptive_stats(master)
    rel = spot_futures_relationship(master)
    hedge = optimal_hedge_ratio(master)
    eff = hedging_effectiveness(master, hedge["h_star"])

    conclusion = (
        f"Based on the analysed period ({master['Date'].min()} to "
        f"{master['Date'].max()}, n={hedge['n_obs']} trading days), the "
        f"estimated optimal NIFTY futures hedge ratio was "
        f"{hedge['h_star']:.4f}. Applying this hedge reduced the variance "
        f"of the unhedged NIFTY exposure by approximately "
        f"{eff['hedging_effectiveness_pct']:.2f}%, lowering annualized "
        f"volatility from {eff['vol_unhedged_annualized'] * 100:.2f}% to "
        f"{eff['vol_hedged_annualized'] * 100:.2f}%."
    )

    return {
        "descriptive_stats": desc,
        "relationship": rel,
        "hedge_ratio": hedge,
        "effectiveness": eff,
        "conclusion": conclusion,
    }


if __name__ == "__main__":
    # Quick CLI sanity check: python3 analysis.py
    master = pd.read_csv("nifty_master.csv", parse_dates=["Date"])
    results = run_full_analysis(master)

    print("\n=== Descriptive Statistics ===")
    print(results["descriptive_stats"])

    print("\n=== Spot-Futures Relationship ===")
    for k, v in results["relationship"].items():
        print(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")

    print("\n=== Optimal Hedge Ratio ===")
    for k, v in results["hedge_ratio"].items():
        print(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")

    print("\n=== Hedging Effectiveness ===")
    for k, v in results["effectiveness"].items():
        if k != "series":
            print(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")

    print("\n=== Conclusion ===")
    print(results["conclusion"])

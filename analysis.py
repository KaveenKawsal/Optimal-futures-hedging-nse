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
        rows.append({
            "Series": label,
            "Mean (daily)": s.mean(),
            "Std Dev (daily)": s.std(),
            "Variance (daily)": s.var(),
            "Min": s.min(),
            "Max": s.max(),
            "Skewness": s.skew(),
            "Kurtosis": s.kurtosis(),
            "Annualized Vol": s.std() * np.sqrt(252),
        })
    return pd.DataFrame(rows).set_index("Series")


def spot_futures_relationship(master: pd.DataFrame) -> dict:
    """Correlation, covariance, and basis summary between spot and futures."""
    rs = master["Spot_Return"].dropna()
    rf = master["Futures_Return"].dropna()
    aligned = master.dropna(subset=["Spot_Return", "Futures_Return"])

    return {
        "correlation": aligned["Spot_Return"].corr(aligned["Futures_Return"]),
        "covariance": aligned["Spot_Return"].cov(aligned["Futures_Return"]),
        "basis_mean": master["Basis"].mean(),
        "basis_std": master["Basis"].std(),
        "basis_min": master["Basis"].min(),
        "basis_max": master["Basis"].max(),
        "pct_days_contango": (master["Basis"] > 0).mean() * 100,   # futures > spot
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
    rs = aligned["Spot_Return"]
    rf = aligned["Futures_Return"]

    cov_sf = rs.cov(rf)
    var_f = rf.var()
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

    # Cumulative return series for charting (starting at 1.0)
    aligned["Cum_Unhedged"] = (1 + aligned["Spot_Return"]).cumprod()
    aligned["Cum_Hedged"] = (1 + aligned["Hedged_Return"]).cumprod()

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
        "series": aligned[["Date", "Spot_Return", "Futures_Return",
                            "Hedged_Return", "Cum_Unhedged", "Cum_Hedged"]],
    }


def _max_drawdown(cum_series: pd.Series) -> float:
    """Maximum peak-to-trough decline of a cumulative return series, as a %."""
    running_max = cum_series.cummax()
    drawdown = (cum_series - running_max) / running_max
    return drawdown.min() * 100


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
        f"volatility from {eff['vol_unhedged_annualized']*100:.2f}% to "
        f"{eff['vol_hedged_annualized']*100:.2f}%."
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

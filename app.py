"""
app.py — Streamlit interface for the NIFTY Futures Hedging project.

Run:
    pip install streamlit plotly pandas numpy
    streamlit run app.py

Expects nifty_master.csv (output of data_cleaning.py) in the same directory.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analysis import (
    descriptive_stats,
    spot_futures_relationship,
    optimal_hedge_ratio,
    hedging_effectiveness,
    rolling_hedge_ratio,
)

st.set_page_config(
    page_title="NIFTY Futures Hedging Analysis",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data
def load_master(path: str = "nifty_master.csv") -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["Date"])
    return df


st.title("Optimal Futures Hedging and Risk Reduction")
st.caption("An Empirical Study Using NSE NIFTY Futures Data")

try:
    master = load_master()
except FileNotFoundError:
    st.error(
        "nifty_master.csv not found. Run fetch_nse_data.py then "
        "data_cleaning.py first, and place nifty_master.csv next to app.py."
    )
    st.stop()

st.sidebar.header("Dataset")
st.sidebar.write(f"**Rows:** {len(master)}")
st.sidebar.write(f"**Date range:** {master['Date'].min().date()} → {master['Date'].max().date()}")

date_range = st.sidebar.date_input(
    "Filter date range",
    value=(master["Date"].min().date(), master["Date"].max().date()),
    min_value=master["Date"].min().date(),
    max_value=master["Date"].max().date(),
)
if len(date_range) == 2:
    start, end = date_range
    master = master[(master["Date"].dt.date >= start) & (master["Date"].dt.date <= end)].reset_index(drop=True)

if len(master) < 10:
    st.warning("Selected range has too few observations for meaningful analysis.")
    st.stop()


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_overview, tab_stats, tab_hedge, tab_effectiveness, tab_basis = st.tabs(
    ["Overview", "Descriptive Statistics", "Optimal Hedge Ratio",
     "Hedging Effectiveness", "Basis Analysis"]
)

# --- Overview ---------------------------------------------------------------
with tab_overview:
    st.subheader("Spot vs Futures Prices")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=master["Date"], y=master["Spot_Price"], name="NIFTY Spot"))
    fig.add_trace(go.Scatter(x=master["Date"], y=master["Futures_Price"], name="NIFTY Futures"))
    fig.update_layout(xaxis_title="Date", yaxis_title="Price", height=450)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Daily Returns: Spot vs Futures")
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=master["Date"], y=master["Spot_Return"], name="Spot Return", opacity=0.7))
    fig2.add_trace(go.Scatter(x=master["Date"], y=master["Futures_Return"], name="Futures Return", opacity=0.7))
    fig2.update_layout(xaxis_title="Date", yaxis_title="Log Return", height=400)
    st.plotly_chart(fig2, use_container_width=True)

# --- Descriptive stats --------------------------------------------------
with tab_stats:
    st.subheader("Descriptive Statistics")
    desc = descriptive_stats(master)
    st.dataframe(desc.style.format("{:.6f}"), use_container_width=True)

    st.subheader("Spot–Futures Relationship")
    rel = spot_futures_relationship(master)
    c1, c2, c3 = st.columns(3)
    c1.metric("Correlation", f"{rel['correlation']:.4f}")
    c2.metric("Covariance", f"{rel['covariance']:.6f}")
    c3.metric("Mean Basis", f"{rel['basis_mean']:.2f}")

    st.subheader("Return Distribution")
    fig3 = go.Figure()
    fig3.add_trace(go.Histogram(x=master["Spot_Return"], name="Spot", opacity=0.6, nbinsx=50))
    fig3.add_trace(go.Histogram(x=master["Futures_Return"], name="Futures", opacity=0.6, nbinsx=50))
    fig3.update_layout(barmode="overlay", xaxis_title="Log Return", height=400)
    st.plotly_chart(fig3, use_container_width=True)

# --- Hedge ratio -----------------------------------------------------------
with tab_hedge:
    st.subheader("Analysis 1 — Optimal Hedge Ratio")
    hedge = optimal_hedge_ratio(master)

    c1, c2, c3 = st.columns(3)
    c1.metric("h* (Cov/Var method)", f"{hedge['h_star']:.4f}")
    c2.metric("OLS beta (cross-check)", f"{hedge['ols_beta']:.4f}")
    c3.metric("R²", f"{hedge['r_squared']:.4f}")

    st.markdown(
        f"""
        **h\\* = Cov(R_spot, R_futures) / Var(R_futures) = {hedge['cov_spot_futures']:.6f} / {hedge['var_futures']:.6f} = {hedge['h_star']:.4f}**

        This means: to hedge ₹1 of NIFTY spot exposure, take an offsetting
        short futures position sized at approximately **{hedge['h_star']:.2%}**
        of that exposure. The OLS regression cross-check (regressing spot
        returns on futures returns) gives an essentially identical beta,
        as expected — the two methods are mathematically equivalent.
        R² of {hedge['r_squared']:.4f} indicates the futures return
        explains {hedge['r_squared']*100:.1f}% of the variation in spot
        returns.
        """
    )

    st.subheader("Rolling Hedge Ratio (60-day window)")
    roll = rolling_hedge_ratio(master, window=60)
    if len(roll):
        fig4 = go.Figure()
        fig4.add_trace(go.Scatter(x=roll["Date"], y=roll["Rolling_H_Star"], name="Rolling h*"))
        fig4.add_hline(y=hedge["h_star"], line_dash="dash",
                        annotation_text=f"Full-sample h* = {hedge['h_star']:.3f}")
        fig4.update_layout(xaxis_title="Date", yaxis_title="h*", height=400)
        st.plotly_chart(fig4, use_container_width=True)
    else:
        st.info("Not enough observations for a 60-day rolling window in the selected range.")

# --- Hedging effectiveness --------------------------------------------------
with tab_effectiveness:
    st.subheader("Analysis 2 — Hedging Effectiveness")
    hedge = optimal_hedge_ratio(master)
    eff = hedging_effectiveness(master, hedge["h_star"])

    c1, c2, c3 = st.columns(3)
    c1.metric("Variance Reduction (HE)", f"{eff['hedging_effectiveness_pct']:.2f}%")
    c2.metric("Annualized Vol — Unhedged", f"{eff['vol_unhedged_annualized']*100:.2f}%")
    c3.metric("Annualized Vol — Hedged", f"{eff['vol_hedged_annualized']*100:.2f}%")

    c4, c5 = st.columns(2)
    c4.metric("Max Drawdown — Unhedged", f"{eff['max_drawdown_unhedged']:.2f}%")
    c5.metric("Max Drawdown — Hedged", f"{eff['max_drawdown_hedged']:.2f}%")

    st.subheader("Volatility Comparison")
    fig5 = go.Figure(go.Bar(
        x=["Unhedged", "Hedged"],
        y=[eff["vol_unhedged_annualized"] * 100, eff["vol_hedged_annualized"] * 100],
        text=[f"{eff['vol_unhedged_annualized']*100:.2f}%", f"{eff['vol_hedged_annualized']*100:.2f}%"],
        textposition="auto",
    ))
    fig5.update_layout(yaxis_title="Annualized Volatility (%)", height=350)
    st.plotly_chart(fig5, use_container_width=True)

    st.subheader("Cumulative Performance: Unhedged vs Hedged")
    series = eff["series"]
    fig6 = go.Figure()
    fig6.add_trace(go.Scatter(x=series["Date"], y=series["Cum_Unhedged"], name="Unhedged"))
    fig6.add_trace(go.Scatter(x=series["Date"], y=series["Cum_Hedged"], name="Hedged"))
    fig6.update_layout(xaxis_title="Date", yaxis_title="Cumulative Return (start = 1.0)", height=450)
    st.plotly_chart(fig6, use_container_width=True)

    st.subheader("Conclusion")
    st.success(
        f"Based on the analysed period ({master['Date'].min().date()} to "
        f"{master['Date'].max().date()}, n={hedge['n_obs']} trading days), "
        f"the estimated optimal NIFTY futures hedge ratio was "
        f"**{hedge['h_star']:.4f}**. Applying this hedge reduced the "
        f"variance of the unhedged NIFTY exposure by approximately "
        f"**{eff['hedging_effectiveness_pct']:.2f}%**, lowering annualized "
        f"volatility from {eff['vol_unhedged_annualized']*100:.2f}% to "
        f"{eff['vol_hedged_annualized']*100:.2f}%."
    )

# --- Basis analysis ----------------------------------------------------
with tab_basis:
    st.subheader("Basis = Futures Price − Spot Price")
    rel = spot_futures_relationship(master)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Mean Basis", f"{rel['basis_mean']:.2f}")
    c2.metric("Basis Std Dev", f"{rel['basis_std']:.2f}")
    c3.metric("% Days Contango", f"{rel['pct_days_contango']:.1f}%")
    c4.metric("% Days Backwardation", f"{rel['pct_days_backwardation']:.1f}%")

    fig7 = go.Figure()
    fig7.add_trace(go.Scatter(x=master["Date"], y=master["Basis"], name="Basis", fill="tozeroy"))
    fig7.add_hline(y=0, line_dash="dash")
    fig7.update_layout(
        xaxis_title="Date", yaxis_title="Basis (Futures − Spot)", height=400,
        annotations=[dict(text="Positive = Contango, Negative = Backwardation",
                           xref="paper", yref="paper", x=0, y=1.05, showarrow=False)]
    )
    st.plotly_chart(fig7, use_container_width=True)

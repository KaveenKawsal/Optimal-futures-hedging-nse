"""
app.py — Streamlit interface for the NIFTY Futures Hedging project.

Run:
    pip install streamlit plotly pandas numpy
    streamlit run app.py

Expects nifty_master.csv (output of data_cleaning.py) in the same directory.
"""

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analysis import (
    hedge_calculator,
    hedging_effectiveness,
    optimal_hedge_ratio,
    rolling_hedge_ratio,
    spot_futures_relationship,
)
from portfolio import TradingAssumptions, compare_out_of_sample, compare_portfolios

st.set_page_config(
    page_title="NIFTY Futures Hedging Analysis",
    layout="wide",
)


def format_rupees(value: float) -> str:
    """Format rupee amounts with Indian digit grouping or lakh units."""
    sign = "-" if value < 0 else ""
    amount = abs(float(value))
    if amount > 100000:
        return f"{sign}₹{amount / 100000:.1f} lakh"

    integer = str(int(round(amount)))
    if len(integer) <= 3:
        indian_number = integer
    else:
        last_three = integer[-3:]
        prefix = integer[:-3]
        prefix_groups = []
        while prefix:
            prefix_groups.insert(0, prefix[-2:])
            prefix = prefix[:-2]
        indian_number = ",".join(prefix_groups + [last_three])
    return f"{sign}₹{indian_number}"


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
    datasets = {"2024 baseline": "nifty_master.csv"}
    extended_path = "data/2020_2025/master.csv"
    manifest_path = Path("data/2020_2025/download_manifest.json")
    if Path(extended_path).exists() and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("status") == "ready":
            datasets["2020–2025 history"] = extended_path
    dataset_name = st.sidebar.selectbox("Study dataset", list(datasets))
    master = load_master(datasets[dataset_name])
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
    master = master[(master["Date"].dt.date >= start) & (master["Date"].dt.date <= end)].reset_index(
        drop=True
    )

investment_amount = st.sidebar.number_input(
    "Investment amount (₹)",
    min_value=10000.0,
    value=2500000.0,
    step=50000.0,
)

with st.sidebar.expander("Trading assumptions"):
    st.caption("Illustrative cost and collateral assumptions; these are not broker quotes.")
    fee_bps = st.number_input("Fees per traded notional (basis points)", min_value=0.0, value=1.0, step=0.1)
    slippage_bps = st.number_input("Slippage (basis points)", min_value=0.0, value=1.0, step=0.1)
    margin_pct = st.number_input("Margin (% of futures notional)", min_value=0.0, max_value=100.0, value=12.0)
    funding_pct = st.number_input("Annual margin funding rate (%)", min_value=0.0, value=8.0)
assumptions = TradingAssumptions(fee_bps, slippage_bps, margin_pct / 100, funding_pct / 100)


with st.sidebar.expander("Glossary"):
    st.write("**Spot price:** The current value of the NIFTY 50 index.")
    st.write("**Futures price:** The market price of a NIFTY futures contract for a future date.")
    st.write("**Hedge:** A position intended to reduce losses in another position.")
    st.write("**Hedge ratio:** The amount of futures exposure used for each rupee of shares.")
    st.write("**Basis:** The futures price minus the spot price.")
    st.write("**Contango:** Futures trade above the spot price.")
    st.write("**Backwardation:** Futures trade below the spot price.")
    st.write("**Rollover:** Moving the hedge from an expiring futures contract to a later one.")
    st.write("**Lot:** The fixed number of index units in one futures contract.")
    st.write("**Volatility (risk):** How widely returns typically move around their average.")
    st.write("**Drawdown:** The fall from a previous high point.")

if len(master) < 10:
    st.warning("Selected range has too few observations for meaningful analysis.")
    st.stop()


def render_problem(master: pd.DataFrame) -> None:
    hedge = optimal_hedge_ratio(master)
    effectiveness = hedging_effectiveness(master, hedge["h_star"])
    st.info(
        f"In this sample, shorting about ₹{hedge['h_star']:.2f} of futures per ₹1 of shares cut the typical yearly swing "
        f"from {effectiveness['vol_unhedged_annualized'] * 100:.2f}% to {effectiveness['vol_hedged_annualized'] * 100:.2f}%."
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Hedge ratio h*", f"{hedge['h_star']:.4f}")
    c2.metric("Risk removed", f"{effectiveness['hedging_effectiveness_pct']:.2f}%")
    c3.metric("Trading days analysed", hedge["n_obs"])
    st.subheader("The Hedging Question")
    st.write(
        "You own NIFTY shares and are worried that the market may fall. A short NIFTY futures position can offset some of the loss if the shares decline. The practical question is how much futures exposure to short, because too little leaves risk and too much creates a new risk. This project estimates that amount from real NSE spot and futures data."
    )
    steps = st.columns(3)
    steps[0].write("**1. Your shares fall**")
    steps[1].write("**2. Your short futures gain**")
    steps[2].write("**3. The two cancel out**")


def render_data(master: pd.DataFrame) -> None:
    st.info(
        f"NIFTY spot and futures prices moved almost together across all {len(master)} selected trading days."
    )
    st.subheader("NIFTY Spot and Futures Prices")
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=master["Date"], y=master["Spot_Price"], name="NIFTY Spot", line=dict(color="#1f77b4"))
    )
    fig.add_trace(
        go.Scatter(
            x=master["Date"], y=master["Futures_Price"], name="NIFTY Futures", line=dict(color="#ff7f0e")
        )
    )
    fig.update_layout(xaxis_title="Date", yaxis_title="Price", height=450)
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "What you're seeing: two price lines over the selected dates. What it means: similar movement suggests futures can help offset changes in shares."
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Rows", len(master), help="Number of daily records in the selected date range.")
    c2.metric("First date", str(master["Date"].min().date()))
    c3.metric("Last date", str(master["Date"].max().date()))
    st.caption(
        "This is the price history used by every later calculation; the sidebar filter applies here and across all tabs."
    )


def render_data_quality(master: pd.DataFrame) -> None:
    missing_by_column = master.isna().sum()
    duplicate_dates = int(master["Date"].duplicated().sum())
    date_range_valid = master["Date"].notna().all() and master["Date"].min() <= master["Date"].max()
    st.info(
        f"The selected dataset has {len(master)} rows, {int(missing_by_column.sum())} missing values, "
        f"and {duplicate_dates} duplicate dates."
    )
    st.subheader("Dataset Checks")
    checks = [
        ("Row count", len(master), len(master) > 0),
        ("Date range", f"{master['Date'].min().date()} to {master['Date'].max().date()}", date_range_valid),
        ("Total missing values", int(missing_by_column.sum()), int(missing_by_column.sum()) == 0),
        ("Duplicate dates", duplicate_dates, duplicate_dates == 0),
    ]
    all_checks_valid = all(check[2] for check in checks)
    status_message = (
        f"All {len(master)} rows complete, no duplicates, and dates run from "
        f"{master['Date'].min().date()} to {master['Date'].max().date()}"
    )
    (st.success if all_checks_valid else st.error)(
        status_message if all_checks_valid else "One or more basic dataset checks needs attention."
    )
    st.caption(
        "These checks confirm that the selected data has rows, a valid date span, no missing cells, and no repeated dates."
    )

    st.subheader("Missing Values Per Column")
    missing_table = missing_by_column.rename("Missing values").rename_axis("Column").reset_index()
    missing_table["Column"] = missing_table["Column"].str.replace("_", " ", regex=False)
    st.dataframe(missing_table, hide_index=True, width="stretch")
    missing_status = (
        "No missing values across all columns."
        if missing_by_column.sum() == 0
        else "Some columns contain missing values."
    )
    (st.success if missing_by_column.sum() == 0 else st.error)(missing_status)
    st.caption("Each number counts unavailable values in one column; zero means that field is complete.")

    st.subheader("Roll Days")
    roll_days = master.loc[master["Is_Roll_Day"]].copy()
    roll_days["Return Difference"] = roll_days["Spot_Return"] - roll_days["Futures_Return"]
    roll_table = roll_days[["Date", "Active_Expiry", "Futures_Return", "Return Difference"]].copy()
    roll_table["Date"] = roll_table["Date"].dt.strftime("%Y-%m-%d")
    roll_table["Active_Expiry"] = roll_table["Active_Expiry"].astype(str)
    roll_table = roll_table.rename(
        columns={
            "Active_Expiry": "Active expiry",
            "Futures_Return": "Futures return",
            "Return Difference": "Return difference",
        }
    )
    st.dataframe(
        roll_table.sort_values("Date").style.format(
            {"Futures return": "{:.6f}", "Return difference": "{:.6f}"}
        ),
        hide_index=True,
        width="stretch",
    )
    st.caption(
        "This lists the dates when the active futures contract changed and checks the associated return difference."
    )

    st.subheader("Largest Spot-Futures Return Differences")
    return_differences = master.assign(
        Return_Difference=master["Spot_Return"] - master["Futures_Return"],
    )
    return_differences["Absolute Difference"] = return_differences["Return_Difference"].abs()
    largest_differences = return_differences.nlargest(10, "Absolute Difference")
    largest_table = largest_differences[
        [
            "Date",
            "Spot_Return",
            "Futures_Return",
            "Return_Difference",
            "Absolute Difference",
            "Is_Roll_Day",
        ]
    ].copy()
    largest_table["Date"] = largest_table["Date"].dt.strftime("%Y-%m-%d")
    largest_table = largest_table.rename(
        columns={
            "Spot_Return": "Spot return",
            "Futures_Return": "Futures return",
            "Return_Difference": "Return difference",
            "Absolute Difference": "Absolute difference",
            "Is_Roll_Day": "Roll day",
        }
    )
    st.dataframe(
        largest_table.style.format(
            {
                "Spot return": "{:.6f}",
                "Futures return": "{:.6f}",
                "Return difference": "{:.6f}",
                "Absolute difference": "{:.6f}",
            }
        ),
        hide_index=True,
        width="stretch",
    )
    st.caption(
        "This ranks the ten dates where spot and futures moved most differently, including whether each was a roll day."
    )

    st.subheader("Basis With Roll Days")
    basis_quality = go.Figure()
    basis_quality.add_trace(go.Scatter(x=master["Date"], y=master["Basis"], name="Basis", mode="lines"))
    basis_quality.add_trace(
        go.Scatter(
            x=roll_days["Date"],
            y=roll_days["Basis"],
            name="Roll day",
            mode="markers",
            marker=dict(color="crimson", size=9, symbol="diamond"),
        )
    )
    basis_quality.update_layout(xaxis_title="Date", yaxis_title="Basis (Futures − Spot)", height=420)
    st.plotly_chart(basis_quality, width="stretch")
    st.caption(
        "What you're seeing: the futures price minus the spot price, with roll-day markers. What it means: the markers make contract-switch dates easy to inspect against basis movements."
    )


def render_relationship(master: pd.DataFrame) -> None:
    rel = spot_futures_relationship(master)
    st.info(f"Their daily moves have a correlation of {rel['correlation']:.3f}, which is very high.")
    st.subheader("Daily Returns")
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=master["Date"],
            y=master["Spot_Return"],
            name="Spot Return",
            opacity=0.55,
            line=dict(color="#1f77b4", width=1),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=master["Date"],
            y=master["Futures_Return"],
            name="Futures Return",
            opacity=0.55,
            line=dict(color="#ff7f0e", width=1),
        )
    )
    fig.update_layout(xaxis_title="Date", yaxis_title="Daily return", height=400)
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "What you're seeing: daily changes in spot and futures. What it means: lines that move together show that futures track the shares closely."
    )

    c1, c2 = st.columns(2)
    c1.metric(
        "Correlation",
        f"{rel['correlation']:.4f}",
        help="How closely the two daily returns move together. 1 means they move identically.",
    )
    with st.expander("For the curious"):
        st.metric(
            "Covariance",
            f"{rel['covariance']:.6f}",
            help="A measure of whether the two daily returns tend to move in the same direction.",
        )

    st.subheader("Return Distribution")
    fig = go.Figure()
    fig.add_trace(
        go.Histogram(x=master["Spot_Return"], name="Spot", opacity=0.6, nbinsx=50, marker_color="#1f77b4")
    )
    fig.add_trace(
        go.Histogram(
            x=master["Futures_Return"], name="Futures", opacity=0.6, nbinsx=50, marker_color="#ff7f0e"
        )
    )
    fig.update_layout(barmode="overlay", xaxis_title="Daily return", height=400)
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "What you're seeing: how often different daily returns occurred. What it means: similar distributions suggest the two instruments carry similar day-to-day risk. All selected observations are included."
    )

    st.subheader("Spot Returns vs Futures Returns")
    hedge = optimal_hedge_ratio(master)
    x_values = master["Futures_Return"].sort_values()
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=master["Futures_Return"],
            y=master["Spot_Return"],
            name="Observed days",
            mode="markers",
            marker=dict(size=7, opacity=0.65, color="#ff7f0e"),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=hedge["ols_alpha"] + hedge["ols_beta"] * x_values,
            name="Fitted line",
            mode="lines",
            line=dict(color="#1f77b4"),
        )
    )
    fig.update_layout(xaxis_title="Futures return", yaxis_title="Spot return", height=420)
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "What you're seeing: each dot is one day and the line is the fitted relationship. What it means: the line shows the average spot-return response to a futures return. All selected observations are included."
    )


def render_hedge_ratio(master: pd.DataFrame) -> None:
    hedge = optimal_hedge_ratio(master)
    st.info(
        f"Selling about ₹{hedge['h_star']:.2f} of futures per ₹1 of shares gave the lowest risk in this sample."
    )
    st.subheader("How Much to Hedge?")
    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Optimal hedge ratio h*",
        f"{hedge['h_star']:.4f}",
        help="The futures position that minimizes the variance of the hedged spot exposure.",
    )
    c2.metric(
        "Regression cross-check",
        f"{hedge['ols_beta']:.4f}",
        help="The slope from fitting spot returns against futures returns.",
    )
    c3.metric(
        "R-squared",
        f"{hedge['r_squared']:.4f}",
        help="The share of spot-return variation explained by futures returns.",
    )
    st.write(
        f"For each ₹1 of spot exposure, the model suggests a short futures position of about "
        f"₹{hedge['h_star']:.2f}. The two independent estimates agree closely."
    )

    st.subheader("Find the Safest Amount to Hedge")
    chosen_h = st.slider(
        "Amount of futures to short per ₹1 of shares (hedge ratio h)",
        min_value=0.0,
        max_value=1.5,
        value=0.5,
        step=0.01,
    )
    spot_returns = master["Spot_Return"]
    futures_returns = master["Futures_Return"]
    hedge_values = [index / 100 for index in range(151)]
    annualized_risks = [
        (spot_returns - hedge_value * futures_returns).std() * (252**0.5) * 100
        for hedge_value in hedge_values
    ]
    chosen_risk = (spot_returns - chosen_h * futures_returns).std() * (252**0.5) * 100
    no_hedge_risk = annualized_risks[0]
    risk_change = (chosen_risk - no_hedge_risk) / no_hedge_risk * 100

    chart_column, metric_column = st.columns([3, 1])
    with chart_column:
        risk_curve = go.Figure()
        risk_curve.add_trace(
            go.Scatter(
                x=hedge_values,
                y=annualized_risks,
                name="Annualized risk",
                mode="lines",
            )
        )
        risk_curve.add_vline(
            x=hedge["h_star"],
            line_dash="dash",
            line_color="seagreen",
            annotation_text=f"Safest: h* = {hedge['h_star']:.4f}",
            annotation_position="top right",
        )
        risk_curve.add_trace(
            go.Scatter(
                x=[chosen_h],
                y=[chosen_risk],
                name="Your chosen h",
                mode="markers",
                marker=dict(size=11, color="crimson"),
            )
        )
        risk_curve.update_layout(
            xaxis_title="Hedge ratio h",
            yaxis_title="Annualized risk (%)",
            height=430,
        )
        st.plotly_chart(risk_curve, width="stretch")
    with metric_column:
        st.metric("Risk with no hedge", f"{no_hedge_risk:.2f}%")
        st.metric("Risk at your chosen h", f"{chosen_risk:.2f}%")
        st.metric("Percentage change", f"{risk_change:+.2f}%")

    st.caption(
        "What you're seeing: how risky your position is for each amount of futures sold. "
        "What it means: risk is highest with no hedge, falls as you add futures, bottoms out near h*, "
        "and rises again if you sell too many."
    )

    st.subheader("Rolling Hedge Ratio")
    roll = rolling_hedge_ratio(master, window=60)
    if len(roll):
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=roll["Date"], y=roll["Rolling_H_Star"], name="Rolling h*"))
        fig.add_hline(
            y=hedge["h_star"], line_dash="dash", annotation_text=f"Full sample = {hedge['h_star']:.3f}"
        )
        fig.update_layout(
            xaxis_title="Date", yaxis_title="Hedge ratio", height=400, yaxis=dict(range=[0.8, 1.2])
        )
        st.plotly_chart(fig, width="stretch")
        st.caption(
            "What you're seeing: the estimated hedge ratio recalculated over a moving 60-day window. What it means: each estimate uses a different 60-day window, so its value changes with market conditions."
        )
    else:
        st.info("There are not enough observations for a 60-day rolling estimate in this date range.")


def render_effectiveness(master: pd.DataFrame) -> None:
    hedge = optimal_hedge_ratio(master)
    eff = hedging_effectiveness(master, hedge["h_star"])
    st.subheader("Statistical hedge estimate")
    st.caption(
        "Full-sample log-return result: estimated and evaluated on the same dates. This is a hindsight fit, not trading profit."
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Hedge ratio", f"{hedge['h_star']:.4f}")
    c2.metric("Variance reduction", f"{eff['hedging_effectiveness_pct']:.2f}%")
    c3.metric("Annualized hedged volatility", f"{eff['vol_hedged_annualized']:.2%}")
    try:
        comparison = compare_out_of_sample(master)
        portfolio_comparison, ledgers, training_rows = compare_portfolios(
            master, investment_amount, assumptions
        )
    except ValueError as exc:
        st.info(str(exc) + ". Choose a longer date range for the portfolio test.")
        return
    st.subheader("Fair out-of-sample comparison")
    st.caption(
        f"Training uses the first {training_rows} observations. Every strategy is evaluated on the same remaining dates. Rolling estimates use only the preceding 60 returns."
    )
    st.dataframe(
        comparison.style.format(
            {
                "Mean hedge ratio": "{:.4f}",
                "Annualized volatility": "{:.2%}",
                "Max drawdown (%)": "{:.2f}",
                "Variance reduction (%)": "{:.2f}",
            }
        ),
        hide_index=True,
        width="stretch",
    )
    st.caption("This table compares fractional log-return hedges. It does not include trading costs.")
    st.subheader("Whole-lot portfolio after costs")
    st.dataframe(
        portfolio_comparison.style.format(
            {
                "Annualized volatility": "{:.2%}",
                "Max drawdown (%)": "{:.2f}",
                "Variance reduction (%)": "{:.2f}",
                **{column: "{:,.2f}" for column in portfolio_comparison if "₹" in column},
            }
        ),
        hide_index=True,
        width="stretch",
    )
    st.caption(
        "Fixed index-equivalent spot units, historical contract lots, daily cash gains/losses marked at closing prices, and entry/rebalance/roll/exit costs. Margin is externally funded; funding accrues over calendar days. Change the assumptions in the sidebar."
    )
    fig = go.Figure()
    for name, ledger in ledgers.items():
        # Include starting capital in the displayed path and drawdown calculation.
        previous_date = pd.to_datetime(master.iloc[training_rows]["Previous_Date"])
        fig.add_trace(
            go.Scatter(
                x=[previous_date, *ledger["Date"]], y=[investment_amount, *ledger["Net_Equity"]], name=name
            )
        )
    fig.update_layout(xaxis_title="Date", yaxis_title="Portfolio value after costs (₹)", height=450)
    st.plotly_chart(fig, width="stretch")
    chosen = st.selectbox("Portfolio ledger", list(ledgers))
    st.dataframe(ledgers[chosen], hide_index=True, width="stretch")
    st.download_button(
        "Download daily portfolio ledger",
        ledgers[chosen].to_csv(index=False),
        file_name="portfolio_ledger.csv",
        mime="text/csv",
    )
    st.caption(
        "External cash needed estimates collateral plus cash losses using end-of-day balances. Intraday margin calls, broker liquidation, dividends, taxes by category, and actual settlement-price execution are not modelled."
    )


def render_real_life(master: pd.DataFrame) -> None:
    st.subheader("Worst days in the out-of-sample portfolio")
    try:
        _, ledgers, _ = compare_portfolios(master, investment_amount, assumptions)
    except ValueError as exc:
        st.info(str(exc) + ". Choose a longer date range.")
        return
    ledger = ledgers["Fixed training h*"]
    worst_days = ledger.nsmallest(10, "Spot_PnL").copy()
    columns = [
        "Date",
        "Lot_Size",
        "Lots",
        "Spot_PnL",
        "Futures_PnL",
        "Trading_Cost",
        "Funding_Cost",
        "Net_PnL",
    ]
    st.dataframe(worst_days[columns], hide_index=True, width="stretch")
    labels = worst_days["Date"].dt.strftime("%Y-%m-%d").tolist()
    selected_date = st.selectbox("Pick a day", labels)
    selected = worst_days[worst_days["Date"].dt.strftime("%Y-%m-%d").eq(selected_date)].iloc[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("Shares alone", format_rupees(selected["Spot_PnL"]))
    c2.metric("Short futures cash gain/loss", format_rupees(selected["Futures_PnL"]))
    c3.metric("Combined after costs", format_rupees(selected["Net_PnL"]))
    st.caption(
        "These cash results use a hedge ratio fitted before the test period, historical whole lots, and the same ledger shown in 'Did It Work?'. Closing-price marking is an approximation to exchange daily settlement."
    )


def render_basis(master: pd.DataFrame) -> None:
    rel = spot_futures_relationship(master)
    st.info(
        f"Futures traded above spot on {rel['pct_days_contango']:.1f}% of days, in the selected sample; the basis also changes when contracts roll."
    )
    st.subheader("The Basis")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Mean basis", f"{rel['basis_mean']:.2f}")
    c2.metric("Basis variation", f"{rel['basis_std']:.2f}")
    c3.metric("Days futures were higher", f"{rel['pct_days_contango']:.1f}%")
    c4.metric("Days futures were lower", f"{rel['pct_days_backwardation']:.1f}%")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=master["Date"], y=master["Basis"], name="Basis", fill="tozeroy"))
    fig.add_hline(y=0, line_dash="dash")
    fig.update_layout(
        xaxis_title="Date",
        yaxis_title="Futures price minus spot price",
        height=420,
        annotations=[
            dict(
                text="Above zero means futures are higher than spot",
                xref="paper",
                yref="paper",
                x=0,
                y=1.05,
                showarrow=False,
            )
        ],
    )
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "What you're seeing: the futures price minus the spot price over time. What it means: positive values show futures above spot, and the gap normally narrows near expiry."
    )


def render_calculator(master: pd.DataFrame) -> None:
    latest = master.iloc[-1]
    calculator_h = optimal_hedge_ratio(master)["h_star"]
    st.info(
        f"Use the selected historical prices and hedge ratio to estimate how many whole futures lots would match your ₹{investment_amount:,.0f} share exposure."
    )
    st.subheader("NIFTY Futures Hedge Calculator")
    c1, c2 = st.columns(2)
    amount = c1.number_input(
        "Investment amount (₹)", min_value=1.0, value=float(investment_amount), step=10000.0
    )
    spot_price = c1.number_input(
        "NIFTY spot price (₹)", min_value=0.01, value=float(latest["Spot_Price"]), step=0.05
    )
    futures_price = c2.number_input(
        "NIFTY futures price (₹)", min_value=0.01, value=float(latest["Futures_Price"]), step=0.05
    )
    lot_size = c2.number_input("NIFTY lot size", min_value=1.0, value=float(latest["Lot_Size"]), step=1.0)
    st.caption("Verify the current NIFTY lot size on the NSE before trading.")
    rounding_label = st.selectbox("Lot rounding", ["Round down (never over-hedge)", "Nearest lot"])
    rounding = "down" if rounding_label.startswith("Round down") else "nearest"
    h_input = st.number_input(
        "Hedge ratio h*", min_value=0.0, value=float(calculator_h), step=0.0001, format="%.4f"
    )
    st.caption(f"Defaults use the latest visible dataset row: {latest['Date'].date()}")
    sizing = hedge_calculator(amount, spot_price, futures_price, lot_size, h_input, rounding=rounding)
    if amount < sizing["notional_per_lot"]:
        st.warning("Your investment is smaller than one futures lot, so an exact hedge isn't possible.")
    c1, c2, c3 = st.columns(3)
    c1.metric("Futures notional to short", f"₹{sizing['futures_notional_to_short']:,.2f}")
    c2.metric("Whole futures lots", f"{sizing['number_of_lots']:,}")
    c3.metric("Actual hedged notional", f"₹{sizing['actual_hedged_notional']:,.2f}")
    difference = sizing["hedge_difference"]
    if abs(difference) < 0.005:
        st.write("The rounded hedge matches the target futures notional.")
    elif difference < 0:
        st.write(f"You are under-hedged by ₹{abs(difference):,.2f}.")
    else:
        st.write(f"You are over-hedged by ₹{difference:,.2f}.")


def render_limits(master: pd.DataFrame) -> None:
    st.info("These limits explain why the historical result should guide a decision, not guarantee one.")
    st.subheader("Limits to Keep in Mind")
    st.markdown(
        "- Available history may not cover every market environment; inspect dataset coverage.\n"
        "- Results may be different in other years.\n"
        "- Portfolio costs and margin are scenarios; actual broker rates and intraday calls may differ.\n"
        "- Whole futures lots make small portfolios difficult to hedge exactly.\n"
        "- The best hedge ratio changes over time, so one fixed number may not stay best."
    )


tab_names = [
    "The Problem",
    "The Data",
    "Can We Trust the Data?",
    "Do They Move Together?",
    "How Much to Hedge?",
    "Did It Work?",
    "Real-Life Test",
    "The Basis",
    "Hedge Calculator",
    "Limits",
]
tabs = st.tabs(tab_names)
renderers = [
    render_problem,
    render_data,
    render_data_quality,
    render_relationship,
    render_hedge_ratio,
    render_effectiveness,
    render_real_life,
    render_basis,
    render_calculator,
    render_limits,
]
for tab, renderer in zip(tabs, renderers):
    with tab:
        renderer(master)

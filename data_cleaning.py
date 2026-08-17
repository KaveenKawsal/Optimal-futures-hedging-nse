"""
data_cleaning.py — Stage 2: Build nifty_master.csv
=====================================================
Reads nifty_spot.csv and nifty_futures.csv (outputs of fetch_nse_data.py),
constructs a continuous near-month futures series with a pre-expiry rollover,
merges with spot data, computes log returns and basis, and writes
nifty_master.csv.

Rollover Rule
-------------
NIFTY monthly futures expire on the last Thursday of each calendar month.
We roll from the near-month to the next-month contract 5 trading days
before the effective expiry date, to avoid the final-settlement-price
artifact and thin trading near expiry.

Returns
-------
Daily log returns: r_t = ln(P_t / P_{t-1}).

Output columns
--------------
Date, Spot_Price, Futures_Price, Spot_Return, Futures_Return, Basis

Usage
-----
    python3 data_cleaning.py
"""

import os
import sys
import calendar
from datetime import date

import numpy as np
import pandas as pd

# -- paths ------------------------------------------------------------------
SPOT_CSV = "nifty_spot.csv"
FUTURES_CSV = "nifty_futures.csv"
MASTER_CSV = "nifty_master.csv"

# -- rollover parameter -------------------------------------------------------
ROLL_DAYS_BEFORE_EXPIRY = 5


# -----------------------------------------------------------------------------
# Helper: last Thursday of a month
# -----------------------------------------------------------------------------
def last_thursday(year: int, month: int) -> date:
    """Return the last Thursday (weekday==3) of the given month."""
    last_day = calendar.monthrange(year, month)[1]
    d = date(year, month, last_day)
    while d.weekday() != 3:
        d = d.replace(day=d.day - 1)
    return d


# -----------------------------------------------------------------------------
# Step 1a - Load spot data
# -----------------------------------------------------------------------------
def load_spot(path: str) -> pd.DataFrame:
    """Load and standardise the spot CSV produced by fetch_nse_data.py.

    Expected columns (from build_spot_dataset in fetch_nse_data.py):
    Date, Open Index Value, High Index Value, Low Index Value, Close
    """
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.rename(columns={"Close": "Spot_Price"})

    df = df.dropna(subset=["Date", "Spot_Price"])
    df = df.drop_duplicates(subset="Date").sort_values("Date")
    return df[["Date", "Spot_Price"]].reset_index(drop=True)


# -----------------------------------------------------------------------------
# Step 1b - Load futures data
# -----------------------------------------------------------------------------
def load_futures(path: str) -> pd.DataFrame:
    """
    Load the futures CSV. nifty_futures.csv was built by concatenating
    old-format and new-format NSE bhavcopy rows, so a single file contains
    BOTH column sets -- old-format rows have NaN in the new-format columns
    and vice versa. We detect format per row (not per file) using which
    columns are actually populated.

    Old NSE bhavcopy: INSTRUMENT (== "FUTIDX"), SYMBOL (== "NIFTY"),
                       EXPIRY_DT, CLOSE, TIMESTAMP
    New NSE bhavcopy: FinInstrmTp (== "IDF"), TckrSymb (== "NIFTY"),
                       XpryDt, ClsPric, TradDt
        NOTE: confirmed IDF, not STF -- NSE's new UDiFF format uses "IDF"
        for index futures.
    """
    raw = pd.read_csv(path, low_memory=False)
    raw.columns = [c.strip() for c in raw.columns]

    old_cols = {"INSTRUMENT", "SYMBOL", "EXPIRY_DT", "CLOSE", "TIMESTAMP"}
    new_cols = {"FinInstrmTp", "TckrSymb", "XpryDt", "ClsPric", "TradDt"}
    prenorm_cols = {"Date", "Expiry", "Close"}

    frames = []

    if old_cols.issubset(raw.columns):
        old = raw[raw["INSTRUMENT"].notna() & raw["TIMESTAMP"].notna()].copy()
        old = old[
            (old["INSTRUMENT"].astype(str).str.strip() == "FUTIDX")
            & (old["SYMBOL"].astype(str).str.strip().str.upper() == "NIFTY")
        ]
        if len(old):
            old = old.rename(
                columns={"TIMESTAMP": "Date", "EXPIRY_DT": "Expiry", "CLOSE": "Close"}
            )
            old["Date"] = pd.to_datetime(old["Date"], dayfirst=True, errors="coerce")
            old["Expiry"] = pd.to_datetime(old["Expiry"], dayfirst=True, errors="coerce")
            old["Close"] = pd.to_numeric(old["Close"], errors="coerce")
            old = old.dropna(subset=["Date", "Expiry", "Close"])
            frames.append(old[["Date", "Expiry", "Close"]])

    if new_cols.issubset(raw.columns):
        new = raw[raw["FinInstrmTp"].notna() & raw["TradDt"].notna()].copy()
        new = new[
            (new["FinInstrmTp"].astype(str).str.strip() == "IDF")
            & (new["TckrSymb"].astype(str).str.strip().str.upper() == "NIFTY")
        ]
        if len(new):
            new = new.rename(
                columns={"TradDt": "Date", "XpryDt": "Expiry", "ClsPric": "Close"}
            )
            new["Date"] = pd.to_datetime(new["Date"], errors="coerce")
            new["Expiry"] = pd.to_datetime(new["Expiry"], errors="coerce")
            new["Close"] = pd.to_numeric(new["Close"], errors="coerce")
            new = new.dropna(subset=["Date", "Expiry", "Close"])
            frames.append(new[["Date", "Expiry", "Close"]])

    # Fallback: already-normalised intermediate file with no raw schema cols
    if not frames and prenorm_cols.issubset(raw.columns):
        df = raw.copy()
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df["Expiry"] = pd.to_datetime(df["Expiry"], errors="coerce")
        df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
        df = df.dropna(subset=["Date", "Expiry", "Close"])
        frames.append(df[["Date", "Expiry", "Close"]])

    if not frames:
        raise ValueError(
            "Could not identify futures bhavcopy format in "
            f"{path}. Available columns: {raw.columns.tolist()}"
        )

    fut = pd.concat(frames, ignore_index=True)
    fut = fut.drop_duplicates(subset=["Date", "Expiry"])
    fut = fut.sort_values(["Date", "Expiry"]).reset_index(drop=True)
    return fut


# -----------------------------------------------------------------------------
# Step 2 - Build expiry calendar & rollover schedule
# -----------------------------------------------------------------------------
def build_rollover_schedule(futures: pd.DataFrame, trading_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """
    For each (Year, Month) that appears in the futures data:
      1. Compute the theoretical last-Thursday expiry.
      2. If that Thursday is not a trading day (NSE holiday), step back to
         the previous trading day.
      3. RolloverDate = the trading day ROLL_DAYS_BEFORE_EXPIRY sessions
         before the effective expiry.
    """
    expiry_periods = sorted(futures["Expiry"].dt.to_period("M").unique())
    td_array = pd.DatetimeIndex(sorted(trading_dates))

    records = []
    for period in expiry_periods:
        y, m = period.year, period.month
        theo = pd.Timestamp(last_thursday(y, m))

        if theo in td_array:
            eff = theo
        else:
            prior = td_array[td_array < theo]
            eff = prior[-1] if len(prior) > 0 else theo

        if eff in td_array:
            eff_idx = td_array.get_loc(eff)
            roll_date = td_array[eff_idx - ROLL_DAYS_BEFORE_EXPIRY] if eff_idx >= ROLL_DAYS_BEFORE_EXPIRY else eff
        else:
            roll_date = eff

        records.append({
            "YearMonth": str(period),
            "TheoreticalExpiry": theo,
            "EffectiveExpiry": eff,
            "RolloverDate": roll_date,
        })

    return pd.DataFrame(records)


# -----------------------------------------------------------------------------
# Step 3 - Construct continuous near-month futures series
# -----------------------------------------------------------------------------
def build_continuous_series(futures: pd.DataFrame, rollover_schedule: pd.DataFrame) -> pd.DataFrame:
    """
    On date D, the active contract is the smallest-expiry contract whose
    RolloverDate has not yet passed (D <= RolloverDate). Once D exceeds
    that contract's RolloverDate, we advance to the next expiry.
    """
    all_dates = sorted(futures["Date"].unique())
    roll_sched = rollover_schedule.sort_values("RolloverDate").reset_index(drop=True)
    rows = []

    for d in all_dates:
        d_ts = pd.Timestamp(d)
        day_data = futures[futures["Date"] == d_ts]
        if day_data.empty:
            continue

        available_expiries = sorted(day_data["Expiry"].unique())
        selected_expiry = None

        for exp in available_expiries:
            exp_period = pd.Timestamp(exp).to_period("M")
            match = roll_sched[roll_sched["YearMonth"] == str(exp_period)]
            if match.empty:
                selected_expiry = exp
                break
            roll_date = match.iloc[0]["RolloverDate"]
            if d_ts <= roll_date:
                selected_expiry = exp
                break

        if selected_expiry is None:
            selected_expiry = available_expiries[0]

        price_row = day_data[day_data["Expiry"] == selected_expiry]
        if price_row.empty:
            continue

        rows.append({
            "Date": d_ts,
            "Futures_Price": price_row["Close"].values[0],
            "Active_Expiry": selected_expiry,
        })

    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# Step 4 - Merge & compute returns / basis
# -----------------------------------------------------------------------------
def build_master(spot: pd.DataFrame, cont_futures: pd.DataFrame) -> pd.DataFrame:
    merged = pd.merge(spot, cont_futures[["Date", "Futures_Price"]], on="Date", how="inner")
    merged = merged.sort_values("Date").reset_index(drop=True)

    merged = merged[(merged["Spot_Price"] > 0) & (merged["Futures_Price"] > 0)]
    merged = merged.dropna(subset=["Spot_Price", "Futures_Price"])

    merged["Spot_Return"] = np.log(merged["Spot_Price"] / merged["Spot_Price"].shift(1))
    merged["Futures_Return"] = np.log(merged["Futures_Price"] / merged["Futures_Price"].shift(1))
    merged["Basis"] = merged["Futures_Price"] - merged["Spot_Price"]

    merged = merged.dropna(subset=["Spot_Return", "Futures_Return"])

    master = merged[["Date", "Spot_Price", "Futures_Price",
                      "Spot_Return", "Futures_Return", "Basis"]].copy()
    master["Date"] = master["Date"].dt.strftime("%Y-%m-%d")
    return master


# -----------------------------------------------------------------------------
# Step 5 - Data-quality summary
# -----------------------------------------------------------------------------
def print_quality_summary(spot_raw, futures_raw, master, rollover_schedule, cont_futures):
    print("\n" + "=" * 60)
    print("DATA QUALITY SUMMARY")
    print("=" * 60)

    print(f"\nSpot data   : {spot_raw['Date'].nunique()} trading days")
    print(f"Futures data: {futures_raw['Date'].nunique()} unique dates (all contracts)")
    print(f"Master file : {len(master)} rows (after inner-join + returns)")

    date_series = pd.to_datetime(master["Date"])
    print(f"\nDate range  : {date_series.min().date()}  ->  {date_series.max().date()}")

    outer = pd.merge(spot_raw, cont_futures[["Date"]], on="Date", how="outer", indicator=True)
    spot_only = (outer["_merge"] == "left_only").sum()
    futures_only = (outer["_merge"] == "right_only").sum()

    print("\nCalendar alignment:")
    print(f"  Dates in spot only (no futures match)  : {spot_only}")
    print(f"  Dates in futures only (no spot match)  : {futures_only}")
    print(f"  Dates in both (inner join)             : {len(master) + 1}")  # +1 for shift-dropped row

    print(f"\nFutures rollover schedule ({ROLL_DAYS_BEFORE_EXPIRY} trading days before expiry):")
    print(f"  {'YearMonth':<12}  {'EffectiveExpiry':<18}  {'RolloverDate'}")
    print(f"  {'-'*12}  {'-'*18}  {'-'*12}")
    for _, row in rollover_schedule.iterrows():
        print(f"  {row['YearMonth']:<12}  {str(row['EffectiveExpiry'].date()):<18}  {row['RolloverDate'].date()}")

    print("\nReturns summary (log returns):")
    for col in ["Spot_Return", "Futures_Return"]:
        s = pd.to_numeric(master[col])
        print(f"  {col:<20}  mean={s.mean():.6f}  std={s.std():.6f}  min={s.min():.4f}  max={s.max():.4f}")

    print(f"\nMissing values in master: {master.isnull().sum().sum()}")
    print(f"Duplicate dates in master: {master['Date'].duplicated().sum()}")
    print("=" * 60 + "\n")


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main():
    for path in [SPOT_CSV, FUTURES_CSV]:
        if not os.path.exists(path):
            print(f"ERROR: {path} not found. Run fetch_nse_data.py first.")
            sys.exit(1)

    print("Loading spot data...")
    spot = load_spot(SPOT_CSV)
    print(f"  {len(spot)} rows loaded from {SPOT_CSV}")

    print("Loading futures data...")
    futures_raw = load_futures(FUTURES_CSV)
    print(f"  {len(futures_raw)} rows loaded from {FUTURES_CSV}")

    trading_dates = pd.DatetimeIndex(
        sorted(set(spot["Date"].tolist()) | set(futures_raw["Date"].tolist()))
    )
    print(f"  Trading calendar: {len(trading_dates)} unique dates")

    print("Building rollover schedule...")
    rollover_schedule = build_rollover_schedule(futures_raw, trading_dates)
    print(f"  {len(rollover_schedule)} monthly expiry cycles identified")

    print("Constructing continuous near-month futures series...")
    cont_futures = build_continuous_series(futures_raw, rollover_schedule)
    print(f"  {len(cont_futures)} rows in continuous series")

    print("Building master dataset...")
    master = build_master(spot, cont_futures)
    print(f"  {len(master)} rows in nifty_master.csv")

    master.to_csv(MASTER_CSV, index=False)
    print(f"\nSaved: {MASTER_CSV}")

    print_quality_summary(spot, futures_raw, master, rollover_schedule, cont_futures)


if __name__ == "__main__":
    main()
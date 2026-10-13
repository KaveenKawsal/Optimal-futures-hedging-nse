"""
data_cleaning.py — Stage 2: Build nifty_master.csv
=====================================================
Reads nifty_spot.csv and nifty_futures.csv (outputs of fetch_nse_data.py),
constructs a continuous near-month futures series with a pre-expiry rollover,
merges with spot data, computes log returns and basis, and writes
nifty_master.csv.

Rollover Rule
-------------
Expiry dates come from the actual contract rows, supporting historical
calendar changes without a hard-coded weekday. We roll to the next contract
on the fifth observed trading session before expiry. Returns use the same
contract on both dates, so switching contracts does not create a fake gain.

Returns
-------
Daily log returns: r_t = ln(P_t / P_{t-1}).

Output columns
--------------
Date, Spot_Price, Futures_Price, Spot_Return, Futures_Return, Basis,
Active_Expiry, Is_Roll_Day

Usage
-----
    python3 data_cleaning.py
"""

import argparse
import calendar
import os
import sys
from datetime import date

import numpy as np
import pandas as pd

# -- paths ------------------------------------------------------------------
SPOT_CSV = "nifty_spot.csv"
FUTURES_CSV = "nifty_futures.csv"
MASTER_CSV = "nifty_master.csv"

# -- rollover parameter -------------------------------------------------------
ROLL_DAYS_BEFORE_EXPIRY = 5


def legacy_lot_size(trading_date, expiry):
    """NIFTY monthly futures lots for legacy files (2020 to July 2024).

    Sources: NSE FAOP/47854 (2021) and FAOP/61415 (2024).
    The April 2024 revision changed existing non-April contracts on April 26.
    UDiFF files carry their own contract-level NewBrdLotQty instead.
    """
    if trading_date >= pd.Timestamp("2024-04-26") and expiry > pd.Timestamp("2024-04-25"):
        return 25
    return 50 if expiry >= pd.Timestamp("2021-07-01") else 75


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
            old = old.rename(columns={"TIMESTAMP": "Date", "EXPIRY_DT": "Expiry", "CLOSE": "Close"})
            old["Date"] = pd.to_datetime(old["Date"], format="%d-%b-%Y", errors="coerce")
            old["Expiry"] = pd.to_datetime(old["Expiry"], format="%d-%b-%Y", errors="coerce")
            old["Close"] = pd.to_numeric(old["Close"], errors="coerce")
            old = old.dropna(subset=["Date", "Expiry", "Close"])
            old["Lot_Size"] = [legacy_lot_size(d, e) for d, e in zip(old["Date"], old["Expiry"])]
            frames.append(old[["Date", "Expiry", "Close", "Lot_Size"]])

    if new_cols.issubset(raw.columns):
        new = raw[raw["FinInstrmTp"].notna() & raw["TradDt"].notna()].copy()
        new = new[
            (new["FinInstrmTp"].astype(str).str.strip() == "IDF")
            & (new["TckrSymb"].astype(str).str.strip().str.upper() == "NIFTY")
        ]
        if len(new):
            new = new.rename(columns={"TradDt": "Date", "XpryDt": "Expiry", "ClsPric": "Close"})
            new["Date"] = pd.to_datetime(new["Date"], errors="coerce")
            new["Expiry"] = pd.to_datetime(new["Expiry"], errors="coerce")
            new["Close"] = pd.to_numeric(new["Close"], errors="coerce")
            new = new.dropna(subset=["Date", "Expiry", "Close"])
            if "NewBrdLotQty" not in new:
                raise ValueError("UDiFF data must include the historical contract lot size")
            new["Lot_Size"] = pd.to_numeric(new["NewBrdLotQty"], errors="raise")
            frames.append(new[["Date", "Expiry", "Close", "Lot_Size"]])

    # Fallback: already-normalised intermediate file with no raw schema cols
    if not frames and prenorm_cols.issubset(raw.columns):
        df = raw.copy()
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df["Expiry"] = pd.to_datetime(df["Expiry"], errors="coerce")
        df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
        df = df.dropna(subset=["Date", "Expiry", "Close"])
        if "Lot_Size" not in df:
            raise ValueError("Normalised futures data must include Lot_Size")
        frames.append(df[["Date", "Expiry", "Close", "Lot_Size"]])

    if not frames:
        raise ValueError(
            f"Could not identify futures bhavcopy format in {path}. Available columns: {raw.columns.tolist()}"
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
    Use observed contract expiries, including holiday-adjusted dates.
    RolloverDate is five sessions before expiry. Future expiries beyond the
    available calendar have no rollover date until that calendar is extended.
    """
    expiries = sorted(futures["Expiry"].unique())
    td_array = pd.DatetimeIndex(sorted(trading_dates))

    records = []
    for expiry in expiries:
        eff = pd.Timestamp(expiry)
        period = eff.to_period("M")
        # Do not fabricate a rollover for contracts expiring after the dataset.
        if eff > td_array.max():
            roll_date = pd.NaT
        else:
            prior = td_array[td_array <= eff]
            if len(prior) <= ROLL_DAYS_BEFORE_EXPIRY:
                raise ValueError("Trading calendar has insufficient pre-expiry history")
            roll_date = prior[-1 - ROLL_DAYS_BEFORE_EXPIRY]

        records.append(
            {
                "YearMonth": str(period),
                "TheoreticalExpiry": eff,
                "EffectiveExpiry": eff,
                "RolloverDate": roll_date,
            }
        )

    return pd.DataFrame(records)


# -----------------------------------------------------------------------------
# Step 3 - Construct continuous near-month futures series
# -----------------------------------------------------------------------------
def build_continuous_series(futures: pd.DataFrame, rollover_schedule: pd.DataFrame) -> pd.DataFrame:
    """
    On date D, the active contract is the smallest-expiry contract whose
    rollover date is still ahead (D < RolloverDate). On the rollover date
    we advance to the next expiry. The active
    expiry is stateful and can never move backward if a later date has an
    incomplete set of contract prices.
    """
    all_dates = sorted(futures["Date"].unique())
    roll_sched = rollover_schedule.sort_values("RolloverDate").reset_index(drop=True)
    rows = []
    current_expiry = None

    for date_index, d in enumerate(all_dates):
        d_ts = pd.Timestamp(d)
        day_data = futures[futures["Date"] == d_ts]
        if day_data.empty:
            continue

        available_expiries = sorted(day_data["Expiry"].unique())
        selected_expiry = None

        for exp in available_expiries:
            match = roll_sched[roll_sched["EffectiveExpiry"] == pd.Timestamp(exp)]
            if match.empty:
                selected_expiry = exp
                break
            roll_date = match.iloc[0]["RolloverDate"]
            if pd.Timestamp(exp) >= d_ts and (pd.isna(roll_date) or d_ts < roll_date):
                selected_expiry = exp
                break

        if selected_expiry is None:
            raise ValueError(f"No eligible forward futures contract on {d_ts.date()}")

        if current_expiry is not None:
            if current_expiry in available_expiries and selected_expiry < current_expiry:
                selected_expiry = current_expiry
            elif selected_expiry < current_expiry:
                forward_expiries = [expiry for expiry in available_expiries if expiry > current_expiry]
                if not forward_expiries:
                    continue
                selected_expiry = forward_expiries[0]

        price_row = day_data[day_data["Expiry"] == selected_expiry]
        if price_row.empty:
            continue

        current_expiry = selected_expiry

        previous_close = np.nan
        previous_lot_size = np.nan
        if date_index > 0:
            previous_date = pd.Timestamp(all_dates[date_index - 1])
            previous_price_row = futures[
                (futures["Date"] == previous_date) & (futures["Expiry"] == selected_expiry)
            ]
            if not previous_price_row.empty:
                previous_close = previous_price_row["Close"].iloc[0]
                previous_lot_size = previous_price_row["Lot_Size"].iloc[0]

        rows.append(
            {
                "Date": d_ts,
                "Futures_Price": price_row["Close"].values[0],
                "Active_Expiry": selected_expiry,
                "Previous_Active_Close": previous_close,
                "Lot_Size": price_row["Lot_Size"].iloc[0],
                "Previous_Lot_Size": previous_lot_size,
                "Previous_Date": pd.Timestamp(all_dates[date_index - 1]) if date_index > 0 else pd.NaT,
            }
        )

    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# Step 4 - Merge & compute returns / basis
# -----------------------------------------------------------------------------
def build_master(spot: pd.DataFrame, cont_futures: pd.DataFrame) -> pd.DataFrame:
    if set(spot["Date"]) != set(cont_futures["Date"]):
        raise ValueError("Spot and futures calendars have gaps; repair missing sessions first")
    merged = pd.merge(
        spot,
        cont_futures[
            [
                "Date",
                "Futures_Price",
                "Active_Expiry",
                "Previous_Active_Close",
                "Lot_Size",
                "Previous_Lot_Size",
                "Previous_Date",
            ]
        ],
        on="Date",
        how="inner",
    )
    merged = merged.sort_values("Date").reset_index(drop=True)

    merged = merged[(merged["Spot_Price"] > 0) & (merged["Futures_Price"] > 0)]
    merged = merged.dropna(subset=["Spot_Price", "Futures_Price"])

    merged["Previous_Spot_Price"] = merged["Spot_Price"].shift(1)
    # Reject mismatched intervals rather than comparing a multi-day spot move
    # with a one-day futures move when either series has missing sessions.
    valid_interval = merged["Previous_Date"].eq(merged["Date"].shift(1))
    if not valid_interval.iloc[1:].all():
        raise ValueError("Spot and futures calendars have gaps; repair missing sessions first")
    merged["Spot_Return"] = np.log(merged["Spot_Price"] / merged["Previous_Spot_Price"])
    merged["Futures_Return"] = np.log(merged["Futures_Price"] / merged["Previous_Active_Close"])
    if merged["Futures_Return"].iloc[1:].isna().any():
        raise ValueError("Missing previous same-contract price; repair the futures archive first")
    merged["Basis"] = merged["Futures_Price"] - merged["Spot_Price"]
    merged["Is_Roll_Day"] = merged["Active_Expiry"].ne(merged["Active_Expiry"].shift(1))
    merged.loc[merged.index[0], "Is_Roll_Day"] = False

    merged = merged.dropna(subset=["Spot_Return", "Futures_Return"])

    master = merged[
        [
            "Date",
            "Spot_Price",
            "Futures_Price",
            "Spot_Return",
            "Futures_Return",
            "Basis",
            "Active_Expiry",
            "Is_Roll_Day",
            "Previous_Active_Close",
            "Previous_Spot_Price",
            "Lot_Size",
            "Previous_Lot_Size",
            "Previous_Date",
        ]
    ].copy()
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
    print(f"  {'-' * 12}  {'-' * 18}  {'-' * 12}")
    for _, row in rollover_schedule.iterrows():
        print(
            f"  {row['YearMonth']:<12}  {str(row['EffectiveExpiry'].date()):<18}  {row['RolloverDate'].date()}"
        )

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
    parser = argparse.ArgumentParser(description="Build the study using actual contract expiry dates")
    parser.add_argument("--spot", default=SPOT_CSV)
    parser.add_argument("--futures", default=FUTURES_CSV)
    parser.add_argument("--output", default=MASTER_CSV)
    args = parser.parse_args()
    for path in [args.spot, args.futures]:
        if not os.path.exists(path):
            print(f"ERROR: {path} not found. Run fetch_nse_data.py first.")
            sys.exit(1)

    print("Loading spot data...")
    spot = load_spot(args.spot)
    print(f"  {len(spot)} rows loaded from {SPOT_CSV}")

    print("Loading futures data...")
    futures_raw = load_futures(args.futures)
    print(f"  {len(futures_raw)} rows loaded from {FUTURES_CSV}")

    trading_dates = pd.DatetimeIndex(sorted(set(spot["Date"].tolist()) | set(futures_raw["Date"].tolist())))
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

    master.to_csv(args.output, index=False, lineterminator="\n")
    print(f"\nSaved: {MASTER_CSV}")

    print_quality_summary(spot, futures_raw, master, rollover_schedule, cont_futures)


if __name__ == "__main__":
    main()

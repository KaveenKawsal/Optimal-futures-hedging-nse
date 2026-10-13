"""
Fetch NIFTY 50 spot (index) and NIFTY index futures historical data from NSE.

Setup:
    pip install jugaad-data pandas

Run:
    python fetch_nse_data.py

Notes:
    - Must be run with normal internet access (NSE blocks many cloud/CI IPs).
    - NSE only serves trading-day data; weekends/holidays are skipped automatically.
    - Bhavcopy downloads are per-day, so this loops over the date range. NSE can be
      slow/rate-limit-ish, so this is deliberately sequential with a small delay.
    - Output: two CSVs — nifty_spot.csv and nifty_futures.csv — ready for the
      cleaning step (date alignment, returns, etc).
"""

import glob
import os
import time
from datetime import date, timedelta

import pandas as pd
from jugaad_data.nse import bhavcopy_fo_raw, bhavcopy_index_save

RAW_DIR = "raw_nse_data"
os.makedirs(RAW_DIR, exist_ok=True)

START_DATE = date(2024, 1, 1)
END_DATE = date(2024, 12, 31)


def daterange(start, end):
    for n in range((end - start).days + 1):
        yield start + timedelta(n)


def save_futures_bhavcopy(trading_date):
    """Download one futures bhavcopy and preserve its detected NSE format."""
    text = bhavcopy_fo_raw(trading_date)
    header = text.splitlines()[0].strip()

    if header.startswith("TradDt,"):
        filename = f"BhavCopy_NSE_FO_0_0_0_{trading_date:%Y%m%d}_F_0000.csv"
    elif header.startswith("INSTRUMENT,"):
        filename = f"fo{trading_date:%d%b%Y}bhav.csv"
    else:
        raise ValueError(f"Unknown NSE futures format for {trading_date}: {header[:80]}")

    path = os.path.join(RAW_DIR, filename)
    with open(path, "w", newline="", encoding="utf-8") as output:
        output.write(text)
    return path


def download_raw_bhavcopies():
    """Downloads one index bhavcopy + one F&O bhavcopy CSV per trading day."""
    for d in daterange(START_DATE, END_DATE):
        if d.weekday() >= 5:  # skip Sat/Sun; NSE holidays will just fail/skip
            continue
        try:
            bhavcopy_index_save(d, RAW_DIR)
        except Exception as e:
            print(f"[spot] skip {d}: {e}")
        try:
            save_futures_bhavcopy(d)
        except Exception as e:
            print(f"[futures] skip {d}: {e}")
        time.sleep(0.3)  # be polite to NSE's servers


def build_spot_dataset():
    """Combine daily index bhavcopy files and filter to NIFTY 50."""

    files = glob.glob(os.path.join(RAW_DIR, "ind_close_all_*.csv"))
    frames = []

    print(f"Found {len(files)} spot files")

    for f in files:
        try:
            df = pd.read_csv(f)
            df.columns = [c.strip() for c in df.columns]

            required_cols = {
                "Index Name",
                "Index Date",
                "Open Index Value",
                "High Index Value",
                "Low Index Value",
                "Closing Index Value",
            }

            if not required_cols.issubset(df.columns):
                print(f"[spot] invalid format, skipping: {os.path.basename(f)}")
                continue

            nifty = df[df["Index Name"].astype(str).str.strip().str.upper() == "NIFTY 50"]

            if not nifty.empty:
                frames.append(nifty)

        except Exception as e:
            print(f"[spot] could not read {os.path.basename(f)}: {e}")

    if not frames:
        raise RuntimeError("No valid NIFTY 50 spot data was found.")

    spot = pd.concat(frames, ignore_index=True)

    spot = spot.rename(columns={"Index Date": "Date", "Closing Index Value": "Close"})

    spot["Date"] = pd.to_datetime(spot["Date"], dayfirst=True, errors="coerce")

    spot = spot[["Date", "Open Index Value", "High Index Value", "Low Index Value", "Close"]]

    spot = spot.dropna(subset=["Date", "Close"]).drop_duplicates(subset=["Date"]).sort_values("Date")

    spot.to_csv("nifty_spot.csv", index=False, lineterminator="\n")

    print(f"Wrote nifty_spot.csv with {len(spot)} rows")


def build_futures_dataset():
    """Combine legacy and UDiFF F&O files, filtering NIFTY index futures."""
    files = glob.glob(os.path.join(RAW_DIR, "fo*bhav.csv")) + glob.glob(
        os.path.join(RAW_DIR, "BhavCopy_NSE_FO*.csv")
    )
    frames = []
    format_counts = {"legacy": 0, "UDiFF": 0}
    for f in files:
        try:
            df = pd.read_csv(f, low_memory=False)
            df.columns = [c.strip() for c in df.columns]
            # Column names vary by NSE format version.
            if {"INSTRUMENT", "SYMBOL"}.issubset(df.columns):
                format_counts["legacy"] += 1
                mask = (df["INSTRUMENT"].astype(str).str.strip() == "FUTIDX") & (
                    df["SYMBOL"].astype(str).str.strip().str.upper() == "NIFTY"
                )
            elif {"FinInstrmTp", "TckrSymb"}.issubset(df.columns):
                format_counts["UDiFF"] += 1
                mask = (df["FinInstrmTp"].astype(str).str.strip() == "IDF") & (
                    df["TckrSymb"].astype(str).str.strip().str.upper() == "NIFTY"
                )
            else:
                print(f"[futures] unsupported format, skipping: {os.path.basename(f)}")
                continue
            frames.append(df[mask])
        except Exception as e:
            print(f"[futures] could not read {os.path.basename(f)}: {e}")

    print(
        f"Found {format_counts['legacy']} legacy futures files and "
        f"{format_counts['UDiFF']} UDiFF futures files"
    )
    if not frames:
        print(
            "No futures files parsed — inspect column names in raw_nse_data/ "
            "and adjust build_futures_dataset() filter."
        )
        return
    fut = pd.concat(frames, ignore_index=True)
    fut.to_csv("nifty_futures.csv", index=False, lineterminator="\n")
    date_columns = [column for column in ("TIMESTAMP", "TradDt") if column in fut]
    dates = pd.concat([pd.to_datetime(fut[column], errors="coerce") for column in date_columns]).dropna()
    print(f"Wrote nifty_futures.csv with {len(fut)} rows ({dates.min().date()} to {dates.max().date()})")


if __name__ == "__main__":
    print("Downloading raw bhavcopies (this will take a while for a 2-year range)...")
    download_raw_bhavcopies()
    print("Building spot dataset...")
    build_spot_dataset()
    print("Building futures dataset...")
    build_futures_dataset()

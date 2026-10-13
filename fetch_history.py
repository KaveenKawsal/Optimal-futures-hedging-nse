"""Resumable official NSE archive download; retains only NIFTY rows.

Run: python fetch_history.py --start 2020-01-01 --end 2025-12-31
Successful responses are hashed in a manifest. Unavailable archives and
network failures are recorded separately; partial data never replaces the
dashboard's verified dataset. No invented prices or substitute providers.
"""

import argparse
import hashlib
import io
import json
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from data_cleaning import build_continuous_series, build_master, build_rollover_schedule, legacy_lot_size


def archive_url(day, kind):
    if kind == "spot":
        return f"https://www.niftyindices.com/Daily_Snapshot/ind_close_all_{day:%d%m%Y}.csv"
    if day >= date(2024, 7, 8):
        return (
            f"https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{day:%Y%m%d}_F_0000.csv.zip"
        )
    month = day.strftime("%b").upper()
    return f"https://nsearchives.nseindia.com/content/historical/DERIVATIVES/{day.year}/{month}/fo{day:%d}{month}{day.year}bhav.csv.zip"


def normalise(text, kind):
    raw = pd.read_csv(io.StringIO(text), low_memory=False)
    raw.columns = raw.columns.str.strip()
    if kind == "spot":
        d = raw[raw["Index Name"].astype(str).str.strip().str.upper().eq("NIFTY 50")].copy()
        d = d.rename(columns={"Index Date": "Date", "Closing Index Value": "Close"})
        d["Date"] = pd.to_datetime(d["Date"], dayfirst=True, errors="raise")
        d = d[["Date", "Close"]]
    elif "INSTRUMENT" in raw:
        d = raw[raw["INSTRUMENT"].eq("FUTIDX") & raw["SYMBOL"].eq("NIFTY")].copy()
        d = d.rename(columns={"TIMESTAMP": "Date", "EXPIRY_DT": "Expiry", "CLOSE": "Close"})
        d["Date"] = pd.to_datetime(d["Date"], format="%d-%b-%Y", errors="raise")
        d["Expiry"] = pd.to_datetime(d["Expiry"], format="%d-%b-%Y", errors="raise")
        d["Lot_Size"] = [legacy_lot_size(t, e) for t, e in zip(d["Date"], d["Expiry"])]
        d = d[["Date", "Expiry", "Close", "Lot_Size"]]
    else:
        d = raw[raw["FinInstrmTp"].eq("IDF") & raw["TckrSymb"].eq("NIFTY")].copy()
        d = d.rename(
            columns={"TradDt": "Date", "XpryDt": "Expiry", "ClsPric": "Close", "NewBrdLotQty": "Lot_Size"}
        )
        d["Date"] = pd.to_datetime(d["Date"], errors="raise")
        d["Expiry"] = pd.to_datetime(d["Expiry"], errors="raise")
        d = d[["Date", "Expiry", "Close", "Lot_Size"]]
    if d.empty:
        raise ValueError("Archive has no matching NIFTY rows")
    d["Close"] = pd.to_numeric(d["Close"], errors="raise")
    if (d["Close"] <= 0).any():
        raise ValueError("Archive contains non-positive prices")
    return d


def local_archive(day, kind):
    name = (
        f"ind_close_all_{day:%d%m%Y}.csv"
        if kind == "spot"
        else f"BhavCopy_NSE_FO_0_0_0_{day:%Y%m%d}_F_0000.csv"
        if day >= date(2024, 7, 8)
        else f"fo{day:%d%b%Y}bhav.csv"
    )
    path = Path("raw_nse_data") / name
    return path if path.exists() else None


def fetch_one(session, day, kind, cache, timeout):
    url = archive_url(day, kind)
    cached = cache / f"{kind}_{day.isoformat()}.csv"
    metadata_path = cached.with_suffix(".json")
    if metadata_path.exists() and not cached.exists():
        metadata = json.loads(metadata_path.read_text())
        if metadata.get("status") in {"unavailable", "unavailable_html"}:
            return None, {**metadata, "cache_hit": True}
    local = local_archive(day, kind)
    if cached.exists():
        result = pd.read_csv(cached, parse_dates=["Date"] + (["Expiry"] if kind == "futures" else []))
        metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
        return result, {
            **metadata,
            "date": day.isoformat(),
            "kind": kind,
            "url": url,
            "status": "cached",
            "normalised_sha256": hashlib.sha256(cached.read_bytes()).hexdigest(),
        }
    if local:
        payload = local.read_bytes()
        text = payload.decode("utf-8-sig")
        source = "local_archive"
    else:
        response = session.get(url, timeout=timeout)
        if response.status_code in (404, 410):
            metadata = {
                "date": day.isoformat(),
                "kind": kind,
                "url": url,
                "status": "unavailable",
                "http_status": response.status_code,
            }
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            return None, metadata
        response.raise_for_status()
        payload = response.content
        # Nifty Indices redirects missing CSVs to a branded HTML error page
        # with HTTP 200. Preserve the response hash and do not parse it as CSV.
        if "text/html" in response.headers.get("Content-Type", ""):
            metadata = {
                "date": day.isoformat(),
                "kind": kind,
                "url": url,
                "status": "unavailable_html",
                "response_url": response.url,
                "source_sha256": hashlib.sha256(payload).hexdigest(),
            }
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            return None, metadata
        if kind == "futures":
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                text = archive.read(archive.namelist()[0]).decode("utf-8-sig")
        else:
            text = payload.decode("utf-8-sig")
        source = "downloaded"
    if "<html" in text[:500].lower() or "<!doctype html" in text[:500].lower():
        metadata = {
            "date": day.isoformat(),
            "kind": kind,
            "url": url,
            "status": "unavailable_html",
            "source": source,
            "source_sha256": hashlib.sha256(payload).hexdigest(),
        }
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        return None, metadata
    result = normalise(text, kind)
    if not result["Date"].dt.date.eq(day).all():
        raise ValueError("Archive dates do not match the requested session")
    result.to_csv(cached, index=False, lineterminator="\n")
    metadata = {
        "date": day.isoformat(),
        "kind": kind,
        "url": url,
        "status": source,
        "source_sha256": hashlib.sha256(payload).hexdigest(),
        "rows": len(result),
    }
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    return result, metadata


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start", type=date.fromisoformat, default=date(2020, 1, 1))
    p.add_argument("--end", type=date.fromisoformat, default=date(2025, 12, 31))
    p.add_argument("--timeout", type=float, default=12)
    p.add_argument("--max-network-failures", type=int, default=3)
    p.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    p.add_argument("--output-dir", type=Path, default=Path("data/2020_2025"))
    args = p.parse_args()
    if args.start > args.end:
        p.error("start must precede end")
    cache = Path(".data-cache")
    cache.mkdir(exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    sessions = threading.local()
    previous_manifest = args.output_dir / "download_manifest.json"
    if previous_manifest.exists():
        previous_records = json.loads(previous_manifest.read_text()).get("records", [])
        for record in previous_records:
            if (
                record.get("source_sha256") and record["status"] in {"downloaded", "local_archive"}
            ) or record["status"] in {"unavailable", "unavailable_html"}:
                metadata_file = cache / f"{record['kind']}_{record['date']}.json"
                if not metadata_file.exists():
                    metadata_file.write_text(json.dumps(record))

    def fetch_day(day):
        if not hasattr(sessions, "client"):
            sessions.client = requests.Session()
            sessions.client.headers.update(
                {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nseindia.com/"}
            )
        day_results = []
        for kind in ("spot", "futures"):
            try:
                frame, record = fetch_one(sessions.client, day, kind, cache, args.timeout)
            except (requests.RequestException, ValueError, KeyError, zipfile.BadZipFile) as exc:
                frame = None
                record = {
                    "date": day.isoformat(),
                    "kind": kind,
                    "url": archive_url(day, kind),
                    "status": "failed",
                    "error": str(exc),
                }
            day_results.append((kind, frame, record))
            if record["status"] != "cached" and not record.get("cache_hit"):
                time.sleep(0.15)
        return day, day_results

    records, frames = [], {"spot": [], "futures": []}
    failures = 0
    stopped = False
    days = [args.start + timedelta(days=n) for n in range((args.end - args.start).days + 1)]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        # Bounded batches allow the circuit breaker to stop without leaving
        # thousands of submitted requests running in the background.
        for batch_start in range(0, len(days), args.workers * 4):
            for day, day_results in pool.map(fetch_day, days[batch_start : batch_start + args.workers * 4]):
                for kind, frame, record in day_results:
                    records.append(record)
                    if record["status"] == "failed":
                        failures += 1
                        print(f"{day} {kind}: {record['error'][:100]}", flush=True)
                    if frame is not None:
                        frames[kind].append(frame)
                if failures >= args.max_network_failures:
                    stopped = True
                if stopped:
                    break
            print(
                f"Checked through {day}; loaded {sum(map(len, frames.values()))} daily archives", flush=True
            )
            if stopped:
                break
    manifest = {
        "requested_start": args.start.isoformat(),
        "requested_end": args.end.isoformat(),
        "status": "blocked" if stopped else "needs_coverage_review" if failures else "downloaded",
        "network_failures": failures,
        "records": records,
        "note": "404/410 means unavailable archive, not independently verified exchange holiday. Review coverage before claiming completeness.",
    }
    if frames["spot"] and frames["futures"] and not stopped and not failures:
        spot = pd.concat(frames["spot"], ignore_index=True).sort_values("Date")
        futures = pd.concat(frames["futures"], ignore_index=True).sort_values(["Date", "Expiry"])
        # A small number of legacy ZIP archives are missing even on genuine
        # trading days. Recover only from the official contract-history API.
        for missing_day in sorted(set(spot.Date) - set(futures.Date)):
            try:
                recovered, metadata = recover_futures(missing_day, futures, cache, args.timeout)
                futures = pd.concat([futures, recovered], ignore_index=True).sort_values(["Date", "Expiry"])
                records = [
                    metadata
                    if r["date"] == missing_day.strftime("%Y-%m-%d") and r["kind"] == "futures"
                    else r
                    for r in records
                ]
            except (requests.RequestException, ValueError, KeyError) as exc:
                manifest["recovery_error"] = str(exc)
        manifest["spot_only_dates"] = [str(d.date()) for d in sorted(set(spot.Date) - set(futures.Date))]
        manifest["futures_only_dates"] = [str(d.date()) for d in sorted(set(futures.Date) - set(spot.Date))]
        spot.to_csv(args.output_dir / "spot.csv", index=False, lineterminator="\n")
        futures.to_csv(args.output_dir / "futures.csv", index=False, lineterminator="\n")
        spot_clean = spot.rename(columns={"Close": "Spot_Price"})
        calendar = pd.DatetimeIndex(sorted(set(spot.Date) | set(futures.Date)))
        try:
            schedule = build_rollover_schedule(futures, calendar)
            master = build_master(spot_clean, build_continuous_series(futures, schedule))
            master.to_csv(args.output_dir / "master.csv", index=False, lineterminator="\n")
            manifest["observations_by_year"] = (
                master.groupby(pd.to_datetime(master.Date).dt.year).size().to_dict()
            )
            manifest["master_sha256"] = hashlib.sha256(
                (args.output_dir / "master.csv").read_bytes()
            ).hexdigest()
            observed_years = set(pd.to_datetime(master.Date).dt.year)
            requested_years = set(range(args.start.year, args.end.year + 1))
            if (
                observed_years == requested_years
                and not manifest["spot_only_dates"]
                and not manifest["futures_only_dates"]
            ):
                manifest["status"] = "ready"
            else:
                manifest["status"] = "needs_coverage_review"
        except ValueError as exc:
            manifest["status"] = "needs_coverage_review"
            manifest["build_error"] = str(exc)
    (args.output_dir / "download_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Saved manifest: {manifest['status']}", flush=True)
    if stopped or failures:
        raise SystemExit(1)


def recover_futures(day, futures, cache, timeout):
    """Recover a missing daily ZIP via verified official contract prices."""
    session = requests.Session()
    session.headers.update(
        {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nseindia.com/report-detail/eq_security"}
    )
    response = session.get("https://www.nseindia.com/report-detail/eq_security", timeout=timeout)
    response.raise_for_status()
    prior = futures[futures.Date < day]
    if prior.empty:
        raise ValueError("Cannot identify the contracts for a missing first session")
    expiries = prior[prior.Date.eq(prior.Date.max())].Expiry
    rows, sources = [], []
    for expiry in expiries:
        if expiry < day:
            continue
        params = {
            "symbol": "NIFTY",
            "from": day.strftime("%d-%m-%Y"),
            "to": day.strftime("%d-%m-%Y"),
            "expiryDate": expiry.strftime("%d-%b-%Y").upper(),
            "instrumentType": "FUTIDX",
            "year": day.year,
        }
        response = session.get(
            "https://www.nseindia.com/api/historicalOR/foCPV", params=params, timeout=timeout
        )
        response.raise_for_status()
        sources.append({"url": response.url, "sha256": hashlib.sha256(response.content).hexdigest()})
        for record in response.json()["data"]:
            if record["FH_SYMBOL"] != "NIFTY" or record["FH_INSTRUMENT"] != "FUTIDX":
                raise ValueError("Unexpected instrument in official history response")
            timestamp = pd.to_datetime(record["FH_TIMESTAMP"], format="%d-%b-%Y")
            if timestamp != day:
                raise ValueError("History response has unexpected session date")
            rows.append(
                {
                    "Date": day,
                    "Expiry": pd.to_datetime(record["FH_EXPIRY_DT"], format="%d-%b-%Y"),
                    "Close": float(record["FH_CLOSING_PRICE"]),
                    "Lot_Size": int(record["FH_MARKET_LOT"]),
                }
            )
    result = pd.DataFrame(rows)
    if len(result) < 2 or (result[["Close", "Lot_Size"]] <= 0).any().any():
        raise ValueError("Official contract-history recovery is incomplete")
    metadata = {
        "date": day.strftime("%Y-%m-%d"),
        "kind": "futures",
        "status": "recovered_official_api",
        "url": "https://www.nseindia.com/api/historicalOR/foCPV",
        "api_responses": sources,
        "rows": len(result),
    }
    target = cache / f"futures_{day:%Y-%m-%d}.csv"
    result.to_csv(target, index=False, lineterminator="\n")
    target.with_suffix(".json").write_text(json.dumps(metadata), encoding="utf-8")
    print(f"Recovered {day.date()} futures from the official history API", flush=True)
    return result, metadata


if __name__ == "__main__":
    main()

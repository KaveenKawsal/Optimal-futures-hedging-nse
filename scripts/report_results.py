"""Regenerate machine-readable results from the actual checked-in dataset."""

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis import run_full_analysis  # noqa: E402
from portfolio import TradingAssumptions, compare_out_of_sample, compare_portfolios  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="nifty_master.csv")
    parser.add_argument("--output", default="results/baseline.json")
    args = parser.parse_args()
    d = pd.read_csv(args.dataset)
    full = run_full_analysis(d)
    assumptions = TradingAssumptions()
    portfolios, _, training_rows = compare_portfolios(d, assumptions=assumptions)
    results = {
        "dataset": args.dataset,
        "sha256": hashlib.sha256(Path(args.dataset).read_bytes()).hexdigest(),
        "rows": len(d),
        "start": d.Date.min(),
        "end": d.Date.max(),
        "missing_values": int(d.isna().sum().sum()),
        "duplicate_dates": int(d.Date.duplicated().sum()),
        "observations_by_year": d.groupby(pd.to_datetime(d.Date).dt.year).size().to_dict(),
        "full_sample_statistical_fit": full["hedge_ratio"],
        "full_sample_effectiveness": {k: v for k, v in full["effectiveness"].items() if k != "series"},
        "common_test_training_rows": training_rows,
        "common_test_statistical_comparison": compare_out_of_sample(d).to_dict("records"),
        "portfolio_initial_spot_capital": 2_500_000,
        "portfolio_assumptions": asdict(assumptions),
        "common_test_portfolios": portfolios.to_dict("records"),
        "limits": [
            "Closing-price marks approximate daily settlement",
            "Index-equivalent spot holding excludes dividends and tracking error",
            "Margin is externally funded and is a scenario, not historical SPAN",
            "Costs are assumptions, not broker quotations",
        ],
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8", newline="\n"
    )
    print(f"Saved {path}: {len(d)} observations")


if __name__ == "__main__":
    main()

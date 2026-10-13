import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from data_cleaning import (
    build_continuous_series,
    build_master,
    build_rollover_schedule,
    load_futures,
    load_spot,
)
from portfolio import compare_portfolios


@pytest.mark.parametrize(
    "folder,result_file",
    [(None, "results/baseline.json"), ("data/2020_2025", "results/history_2020_2025.json")],
)
def test_checked_in_datasets_rebuild_and_ledger_reconciles(folder, result_file):
    if folder:
        master_path = Path(folder) / "master.csv"
        if not master_path.exists():
            pytest.skip("Extended archive download is not available yet")
        manifest = json.loads((Path(folder) / "download_manifest.json").read_text(encoding="utf-8"))
        assert manifest["status"] == "ready"
        assert not manifest["spot_only_dates"] and not manifest["futures_only_dates"]
        spot = load_spot(str(Path(folder) / "spot.csv"))
        futures = load_futures(str(Path(folder) / "futures.csv"))
    else:
        master_path = Path("nifty_master.csv")
        spot = load_spot("nifty_spot.csv")
        futures = load_futures("nifty_futures.csv")
    calendar = pd.DatetimeIndex(sorted(set(spot.Date) | set(futures.Date)))
    rebuilt = build_master(spot, build_continuous_series(futures, build_rollover_schedule(futures, calendar)))
    saved = pd.read_csv(master_path)
    for column in ("Date", "Active_Expiry", "Previous_Date"):
        rebuilt[column] = pd.to_datetime(rebuilt[column])
        saved[column] = pd.to_datetime(saved[column])
    pd.testing.assert_frame_equal(
        rebuilt.reset_index(drop=True),
        saved.reset_index(drop=True),
        check_dtype=False,
        rtol=1e-10,
        atol=1e-12,
    )
    assert not saved.isna().any().any()
    assert not saved.Date.duplicated().any()
    result = json.loads(Path(result_file).read_text(encoding="utf-8"))
    assert result["sha256"] == hashlib.sha256(master_path.read_bytes()).hexdigest()
    comparisons, ledgers, _ = compare_portfolios(saved)
    assert comparisons.Observations.nunique() == 1
    for ledger in ledgers.values():
        np.testing.assert_allclose(ledger.Net_Equity, 2_500_000 + ledger.Net_PnL.cumsum(), rtol=1e-10)

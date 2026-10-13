# Optimal Futures Hedging Using NSE Data

An academic study of how short NIFTY futures can reduce the risk of a NIFTY 50 exposure. The project includes a ten-tab Streamlit dashboard, a statistical hedge estimate, and a separate whole-lot portfolio simulation.

## Quick start

Use **Python 3.12**. From this folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

On Windows, `./start-dashboard.ps1` launches the dashboard using the local environment. The repaired local `.venv` is ready to use. `.venv-old` preserves the previous broken environment and is excluded from Git. Environments are machine-specific: recreate one after cloning.

`requirements.txt` pins the direct runtime dependencies. `requirements-dev.txt` adds the verification tools. `requirements.lock` records the complete installed development environment from this Windows/Python 3.12 validation run.

## What the dashboard does

The ten tabs explain the problem, show the data and quality checks, examine spot/futures relationships, estimate the hedge ratio, compare performance, inspect the worst test days, show the basis, size whole lots, and explain limitations. The sidebar controls dates, investment amount, and illustrative costs and margin assumptions.

The calculator defaults to the lot size on the selected historical dataset row. Its prices are historical defaults, not live quotes. Verify current contract specifications before using different contracts.

## Data and reproducibility

The checked-in 2024 baseline contains **245 return observations**, 2 January through 31 December 2024. It has no missing cells or duplicate dates. Raw NSE archives remain excluded from Git; processed datasets and reproducible download scripts are included.

To rebuild the baseline:

```powershell
.\.venv\Scripts\python.exe data_cleaning.py
.\.venv\Scripts\python.exe analysis.py
.\.venv\Scripts\python.exe scripts/report_results.py
```

The checked-in **2020–2025** study is complete: **1,491 return observations**, 2 January 2020 through 31 December 2025, with zero missing cells, duplicate dates, or unmatched spot/futures sessions. Both datasets are selectable in the dashboard. The extended archive includes special weekend sessions omitted by the original weekday-only baseline fetcher.

To reproduce or resume its download:

```powershell
.\.venv\Scripts\python.exe fetch_history.py --start 2020-01-01 --end 2025-12-31
```

This resumable downloader retains only NIFTY rows, hashes downloaded source responses, includes special weekend sessions, and writes a coverage manifest under `data/2020_2025/`. Failed requests are recorded rather than replaced with estimates. A missing archive is not automatically treated as an independently verified exchange holiday. Review the manifest and calendar alignment before claiming complete coverage. Successful filtered downloads are cached in `.data-cache/`.

The manifest records available archives for every calendar date requested and verifies that the observed spot/futures calendars match. A missing 30 March 2021 futures ZIP was recovered from NSE’s official contract-history API, with response hashes retained. This confirms the observed-source coverage; unavailable archives are not independent proof of exchange holidays. The 2024 baseline remains available separately.

## Two separate methods

### Statistical study

Daily log returns are `ln(P_t/P_(t-1))`. The minimum-variance hedge ratio is:

`h* = Cov(spot returns, futures returns) / Var(futures returns)`

OLS supplies an independent computational cross-check of the same slope. Hedged log-return residuals are `R_S - h* R_F`. Variance reduction is `1 - Var(hedged)/Var(unhedged)`.

The full-sample result is a **hindsight fit**. Exponentiating accumulated residuals is a statistical proxy, not the actual wealth of a self-financing futures portfolio.

All four out-of-sample strategies use identical test dates: no hedge, one-for-one, fixed training h*, and rolling prior-window h*. Evaluation starts after both the first half of the sample and the first 60 returns are available. The fixed ratio is estimated before the test; each rolling ratio uses only the preceding 60 returns. Full-sample h* is excluded from that comparison.

### Whole-lot portfolio simulation

The spot exposure is a fixed number of index-equivalent units bought at the close before the test. Before each evaluated session, futures are sized using the preceding spot value, the preceding close of the contract selected for that session, and its historical lot size.

Daily short-futures cash gain/loss is:

`short units × (previous same-contract close − current close)`

The ledger tracks shares, futures cash flows, turnover, costs, collateral requirements, and net equity. Rolling charges both closing the old contract and opening the new one. Final futures liquidation is also charged. A contract-switch price gap never becomes an artificial trading profit. Drawdown includes starting capital so an initial loss is counted.

The default scenario uses **1 basis point fees + 1 basis point slippage per traded notional**, **12% margin**, and **8% annual margin funding**, all editable. These are illustrative assumptions, not historical broker rates or SPAN margin estimates. Funding accrues over actual calendar days. Margin principal is collateral, not a loss, and is assumed externally funded. Returns are measured against spot portfolio equity, not spot plus external funding capital. Cash-deficit and external-cash estimates are shown separately.

Daily marks use closing prices. This approximates daily settlement; exchange settlement prices, intraday margin calls, forced liquidation, dividends, ETF tracking error, stock-basket costs, and taxes by category are not replicated. The model assumes trades can occur at the preceding closing price and ignores liquidity constraints.

## Expiry and lot-size handling

Rollover occurs on the fifth observed trading session before the **actual expiry in the contract data**. No Thursday/Tuesday rule is imposed, and expiries beyond the available calendar cannot trigger a fabricated roll at year-end. Spot/futures return intervals must match; inconsistent calendars produce an error.

UDiFF files supply each contract's `NewBrdLotQty`. Legacy monthly lot sizes use the following official sources:

- [NSE FAOP/47854, 31 March 2021](https://nsearchives.nseindia.com/content/circulars/FAOP47854.pdf): July 2021 monthly contracts onward changed from 75 to 50 units.
- [NSE FAOP/61415, 2 April 2024](https://nsearchives.nseindia.com/content/circulars/FAOP61415.pdf): non-April NIFTY contracts changed to 25 units from 26 April 2024.
- [NSE NIFTY contract specifications](https://www.nseindia.com/static/products-services/equity-derivatives-nifty50): contract and settlement context. Historical UDiFF lot metadata takes precedence over current specifications.

## Results

The revised rollover timing changes the previous baseline slightly. The rebuilt 2024 full-sample ratio is approximately **0.9867**, with approximately **97.60% statistical variance reduction**, and annualized volatility falls from **14.15% to 2.19%**.

For the common 2024 out-of-sample period (4 July–31 December; 123 observations), statistical variance reduction is approximately **97.10%** for one-for-one, **96.94%** for fixed training h*, and **97.03%** for the rolling estimate. The one-for-one benchmark remains competitive.

These statistical figures must not be substituted for whole-lot after-cost results. Exact dataset hashes, assumptions, statistical metrics, and portfolio outcomes are recorded in `results/baseline.json` and `results/history_2020_2025.json`. Re-run `scripts/report_results.py` whenever data or methodology changes.

To regenerate the extended results:

```powershell
.\.venv\Scripts\python.exe scripts/report_results.py --dataset data/2020_2025/master.csv --output results/history_2020_2025.json
```

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
```

**31 tests pass** in the verified local Python 3.12 environment. Tests cover covariance/OLS agreement, initial-loss drawdown, prior-only estimation, common evaluation dates, historical lot changes, roll returns, entry/exit/roll costs, cash-accounting identities, calendar-day funding, missing sessions, dataset rebuilding and cash reconciliation, source response validation, and dashboard dataset/cost controls. GitHub Actions runs these checks on Python 3.12.

## Files

- `fetch_nse_data.py`: original raw-archive fetcher for the 2024 baseline.
- `fetch_history.py`: resumable 2020–2025 filtered-archive downloader with provenance.
- `data_cleaning.py`: schema normalization, expiry calendar, continuous contracts, and returns.
- `analysis.py`: statistical functions.
- `portfolio.py`: common test periods and the whole-lot cash ledger.
- `app.py`: dashboard.
- `tests/`: calculation and dashboard checks.
- `scripts/report_results.py`: reproducible result generation.
- `FUNDAMENTALS.md`: beginner's guide.

## Scope

This is an educational historical study, not a live execution system. A high in-sample variance reduction does not establish trading profitability or guarantee future protection. Broader history improves the evidence but does not cover all market conditions. GARCH and cointegration remain optional research extensions.

Repository: [sai-chakrith/optimal-future-hedging-NSE](https://github.com/sai-chakrith/optimal-future-hedging-NSE).

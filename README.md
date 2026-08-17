# Optimal Futures Hedging and Risk Reduction Using NSE Data

An empirical Financial Engineering project that evaluates the effectiveness of **NIFTY Index Futures** in hedging **NIFTY 50 spot market exposure**.

The project estimates the **Minimum Variance Optimal Hedge Ratio**, constructs a hedged portfolio, and measures the resulting reduction in risk using daily NSE market data.

---

## 📌 Project Overview

Financial market participants use futures contracts to reduce the risk associated with adverse price movements in an underlying asset.

This project investigates the following question:

> **How effectively can NIFTY Index Futures hedge the price risk of a NIFTY 50 spot market position?**

The analysis estimates an optimal hedge ratio based on the relationship between spot and futures returns and compares the risk of an unhedged position with that of an optimally hedged position.

---

## 🎯 Objectives

The main objectives of this project are to:

- Analyse the relationship between NIFTY 50 spot prices and NIFTY futures prices.
- Calculate daily log returns for both spot and futures series.
- Estimate the Minimum Variance Optimal Hedge Ratio.
- Verify the hedge ratio using Ordinary Least Squares (OLS) regression.
- Construct an optimally hedged portfolio.
- Measure hedging effectiveness through variance reduction.
- Compare volatility before and after hedging.
- Analyse maximum drawdown before and after hedging.
- Study the futures basis and identify periods of contango and backwardation.
- Analyse how the hedge ratio changes over time using a rolling window.

---

## 📊 Dataset

### Instruments

| Instrument | Role |
|---|---|
| NIFTY 50 Index | Spot / Underlying Exposure |
| NIFTY Index Futures | Hedging Instrument |

### Study Period

| Parameter | Value |
|---|---|
| Start Date | 2 January 2024 |
| End Date | 5 July 2024 |
| Frequency | Daily |
| Usable Observations | 124 |

The dataset was cleaned and aligned to retain dates for which both spot and futures observations were available.

---

## 🧮 Methodology

### 1. Daily Log Returns

Daily log returns are calculated as:

$$
R_t = \ln\left(\frac{P_t}{P_{t-1}}\right)
$$

where:

- $P_t$ = Price at time $t$
- $P_{t-1}$ = Price at the previous trading day

The analysis uses:

- $R_S$ = Spot return
- $R_F$ = Futures return

---

### 2. Minimum Variance Optimal Hedge Ratio

The optimal hedge ratio is calculated using:

$$
h^* = \frac{Cov(R_S,R_F)}{Var(R_F)}
$$

where:

- $h^*$ = Minimum Variance Optimal Hedge Ratio
- $Cov(R_S,R_F)$ = Covariance between spot and futures returns
- $Var(R_F)$ = Variance of futures returns

---

### 3. OLS Regression Cross-Check

The hedge ratio is independently verified using:

$$
R_S = \alpha + \beta R_F + \epsilon
$$

The regression coefficient:

$$
\beta \approx h^*
$$

The regression also provides the $R^2$ value, indicating the strength of the relationship between spot and futures returns.

---

### 4. Hedged Portfolio Return

The return of the hedged portfolio is calculated as:

$$
R_H = R_S - h^*R_F
$$

where:

- $R_H$ = Hedged portfolio return
- $R_S$ = Spot return
- $R_F$ = Futures return

---

### 5. Hedging Effectiveness

Hedging effectiveness is measured using variance reduction:

$$
HE = 1 - \frac{Var(R_H)}{Var(R_S)}
$$

A higher value indicates greater reduction in risk.

---

### 6. Basis Analysis

The futures basis is calculated as:

$$
Basis = Futures\ Price - Spot\ Price
$$

- **Positive Basis** → Contango
- **Negative Basis** → Backwardation

The project analyses the mean, standard deviation, minimum and maximum basis, along with the percentage of trading days spent in contango and backwardation.

---

## 📈 Key Results

Based on the analysed sample period:

| Metric | Result |
|---|---:|
| Optimal Hedge Ratio | **0.9500** |
| OLS Hedge Ratio | **0.9500** |
| Spot-Futures Correlation | **0.9808** |
| OLS $R^2$ | **0.9619** |
| Hedging Effectiveness | **96.19%** |
| Unhedged Annualized Volatility | **15.54%** |
| Hedged Annualized Volatility | **3.03%** |
| Mean Basis | **92.50** |
| Days in Contango | **97.58%** |
| Days in Backwardation | **2.42%** |

### Interpretation

The estimated optimal hedge ratio of **0.9500** indicates that the futures position required for minimum-variance hedging was approximately **95% of the equivalent spot exposure**, subject to actual futures contract sizing and notional-value considerations.

The optimally hedged portfolio achieved approximately **96.19% variance reduction** during the analysed sample period.

Annualized volatility decreased from **15.54%** for the unhedged position to **3.03%** after applying the optimal hedge.

---

## 🖥️ Streamlit Dashboard

The project includes an interactive Streamlit dashboard with five sections:

### 1. Overview

- NIFTY Spot vs Futures Price
- Daily Spot vs Futures Returns
- Dataset summary and date filtering

### 2. Descriptive Statistics

- Mean
- Standard Deviation
- Variance
- Minimum
- Maximum
- Skewness
- Kurtosis
- Annualized Volatility

### 3. Optimal Hedge Ratio

- Covariance/Variance Hedge Ratio
- OLS Regression Cross-Check
- Regression $R^2$
- Rolling 60-Day Hedge Ratio

### 4. Hedging Effectiveness

- Unhedged vs Hedged Variance
- Variance Reduction
- Annualized Volatility Comparison
- Maximum Drawdown Comparison
- Cumulative Performance Comparison

### 5. Basis Analysis

- Mean Basis
- Basis Volatility
- Contango vs Backwardation
- Basis Movement Over Time

---

## 📁 Project Structure

```text
optimal-futures-hedging-nse/
│
├── analysis.py              # Core financial analysis functions
├── app.py                   # Streamlit dashboard
├── data_cleaning.py         # Data cleaning and continuous futures construction
├── fetch_nse_data.py        # NSE data collection
│
├── nifty_spot.csv           # Processed NIFTY spot data
├── nifty_futures.csv        # Processed NIFTY futures data
├── nifty_master.csv         # Final analysis dataset
│
├── requirements.txt         # Project dependencies
├── .gitignore
└── README.md
```

---

## ⚙️ Installation

### 1. Clone the Repository

```bash
git clone https://github.com/KaveenKawsal/Optimal-futures-hedging-nse.git
```

### 2. Move into the Project Directory

```bash
cd Optimal-futures-hedging-nse
```

### 3. Create a Virtual Environment

#### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

#### Windows

```bash
python -m venv .venv
.venv\Scripts\activate
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## ▶️ Running the Project

### Step 1: Fetch NSE Data

```bash
python3 fetch_nse_data.py
```

### Step 2: Clean and Prepare the Dataset

```bash
python3 data_cleaning.py
```

This generates the final dataset:

```text
nifty_master.csv
```

### Step 3: Run Financial Analysis

```bash
python3 analysis.py
```

This calculates:

- Descriptive statistics
- Spot-futures relationship
- Optimal hedge ratio
- OLS cross-check
- Hedging effectiveness
- Volatility reduction
- Maximum drawdown

### Step 4: Launch the Dashboard

```bash
streamlit run app.py
```

The Streamlit dashboard will open in your browser.

---

## 🔍 Data Validation

The final dataset was subjected to basic internal consistency checks, including:

- Missing value checks
- Duplicate date checks
- Spot and futures date alignment
- Extreme return inspection
- Spot-futures return difference analysis
- Basis behaviour analysis
- Inspection of unusual spot-futures divergences

The final master dataset contains **124 usable observations** with no missing values or duplicate dates.

An isolated divergence between spot and futures returns was observed on **18 January 2024**. The observation was retained because the validation checks did not establish it as a data error.

---

## ⚠️ Limitations

This study has several limitations:

- The analysis covers approximately six months of market data rather than multiple years.
- Results are specific to the selected sample period.
- The optimal hedge ratio may vary over time.
- Annualized volatility and maximum drawdown estimates may be sensitive to the relatively limited sample size.
- Actual hedging in practice requires consideration of futures contract size, transaction costs, margin requirements, liquidity and rollover costs.
- The estimated hedge ratio should not be interpreted as a universal or permanent NIFTY hedge ratio.

For this reason, the results should be interpreted as an **empirical evaluation of hedging performance during the selected sample period**.

---

## 🛠️ Technologies Used

- **Python**
- **Pandas**
- **NumPy**
- **Streamlit**
- **Plotly**

---

## 📚 Academic Purpose

This project was developed as a **Financial Engineering empirical study** to demonstrate the application of futures contracts for portfolio risk reduction using historical market data.

The project focuses on:

- Financial data processing
- Futures hedging
- Minimum variance hedge estimation
- Regression analysis
- Risk measurement
- Interactive financial visualization

---

## 📄 Disclaimer

This project is intended solely for **academic and research purposes**.

The results are based on historical data from a specific sample period and do not constitute financial, investment, trading, or hedging advice.

---

## 👤 Author

**Kaveen Kawsal**

B.Tech Artificial Intelligence and Data Science

GitHub: [KaveenKawsal](https://github.com/KaveenKawsal)
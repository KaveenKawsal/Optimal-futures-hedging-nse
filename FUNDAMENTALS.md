# Fundamentals of Futures Hedging

### A Beginner's Guide to the NIFTY Optimal Hedge Ratio Project

---

## How to Read This Guide

This document is written for someone who has **never studied finance before**.

It is split into five parts:

| Part | What it covers | Read this if... |
|---|---|---|
| **Part 1** | The basic ideas — markets, prices, risk | You don't know what "hedging" even means |
| **Part 2** | The statistics you need | You've heard of mean/variance but want a refresher |
| **Part 3** | The core math — the hedge ratio itself | You want to understand *why* the formula works |
| **Part 4** | How the project turns data into results | You want to understand the code/pipeline |
| **Part 5** | Reading and trusting the results | You want to know what the numbers actually mean |

Each part builds on the one before it. If you're in a hurry, read the **boxed formulas** and the **"In plain English"** callouts — they carry the core meaning even if you skip the derivations.

---

# PART 1 — The Basic Ideas

## 1.1 What problem is this project solving?

Imagine you own ₹10,00,000 worth of stocks that move roughly in line with the Indian stock market. You believe in these stocks long-term, so you don't want to sell them. But you're nervous the market might drop over the next few weeks.

**The question this project answers:**

> Without selling your shares, how much of a "counter-bet" (using futures contracts) should you place, so that if the market falls, your losses are minimized?

That "how much" is a number called the **hedge ratio**, and finding its optimal value is the entire point of this project.

## 1.2 Some vocabulary, explained simply

| Term | Simple meaning |
|---|---|
| **Asset** | Anything with monetary value — a stock, gold, an index, a currency |
| **Index** | A single number that summarizes the price movement of many stocks combined |
| **NIFTY 50** | India's most-watched index — the average performance of 50 large NSE-listed companies |
| **Spot price** | The price of something *right now*, for immediate ownership |
| **Derivative** | A contract whose value is *based on* another asset (it "derives" its value from it) |
| **Futures contract** | A derivative where two parties agree today on a price for something to be settled later |

**In plain English:** the NIFTY 50 index tells you "how is the market doing today," and NIFTY futures are a bet on "how will the market be doing at a future date" — and because both are tied to the same underlying market, they tend to move together.

## 1.3 Spot price vs. futures price

We give these two prices short symbols so we can use them in formulas later:

```
S(t)  =  Spot price at time t
F(t)  =  Futures price at time t
```

They are usually close to each other, but rarely identical. For example, on a given day:

- Spot price: **22,000**
- Futures price: **22,100**

The ₹100 gap exists because the futures price accounts for the cost of holding the position until a future date (financing costs, expected dividends, market expectations, and short-term supply/demand).

## 1.4 The "basis": measuring the gap

We define:

```
Basis(t) = F(t) − S(t)
```

- **Basis > 0** → Futures priced *above* spot → called **Contango**
- **Basis < 0** → Futures priced *below* spot → called **Backwardation**
- **Basis = 0** → Prices are equal

**Why bother tracking this?** Because a hedge isn't just about spot and futures moving together — it's also about how *stable* that gap is. If the gap swings around unpredictably, your hedge becomes less reliable. This unpredictability is called **basis risk**, and it's one of the reasons a hedge is never perfect.

## 1.5 What is hedging, really?

> **Hedging is about reducing uncertainty — not about maximizing profit.**

If you own shares that move with the market (a **long spot position**), and you're worried about a fall, the standard defensive move is to **short** (bet against) futures contracts on the same index.

| Position | Wins when price... |
|---|---|
| **Long** (you own it) | ...goes up |
| **Short** (you've bet against it) | ...goes down |

**In plain English:** if the market drops, your shares lose value — but your short futures bet gains value. The gain on one side is designed to offset the loss on the other.

## 1.6 Putting it into one equation

If you hold a spot position and hedge it with a short futures position, your combined ("hedged") return each day is:

```
R_H = R_S − h × R_F
```

Where:

- `R_H` = your hedged portfolio's return
- `R_S` = your spot (share) position's return
- `R_F` = the futures position's return
- `h`   = the **hedge ratio** — how much futures exposure you take on, per unit of spot exposure

If `h` is too small, you're under-hedged (still exposed to a lot of risk). If `h` is too large, you're over-hedged (exposed to risk from the futures side instead). **The whole project is about finding the value of `h` that gets this balance exactly right.**

## 1.7 Why a hedge is never perfect

A "perfect" hedge would require spot and futures to move in exact lockstep every single day. In reality they don't, because of:

- Differences in how spot and futures react to news
- Changing basis
- Contract expiry and rollover effects
- Liquidity differences

So the realistic goal isn't zero risk — it's **as little risk as mathematically possible**:

```
Goal:  minimize  Var(R_H)     (NOT necessarily make it zero)
```

---

# PART 2 — The Statistics You Need

## 2.1 Why we use *returns*, not raw prices

A price of "20,200" tells you almost nothing on its own. What matters is the **percentage change** from the previous day, because that's comparable across time and across assets.

### Simple return

```
R(t) = [P(t) − P(t−1)] / P(t−1)
```

### Log return (what this project actually uses)

```
r(t) = ln( P(t) / P(t−1) )
```

**Why log returns instead of simple returns?**

1. **Scale independence** — a 100-point move means something different at index level 10,000 vs. 25,000; log returns express *relative* size properly.
2. **They add up cleanly across time** — the log return over two days equals the sum of the log returns of each individual day. Simple returns don't have this convenient property.
3. **They're the right input for covariance-based formulas** — which is exactly what the hedge ratio needs (see Part 3).

## 2.2 The describing statistics, one at a time

Before any hedging math happens, the project first *describes* the data. Each statistic answers a different question:

| Statistic | Question it answers |
|---|---|
| **Mean** | On an average day, what's the typical return? |
| **Variance / Std. Deviation** | How much do returns swing around that average? |
| **Annualized volatility** | How risky is this on a yearly time-scale? |
| **Min / Max** | What were the most extreme single days? |
| **Skewness** | Are big moves more often up or down? |
| **Kurtosis** | Are extreme days more common than a "normal" bell curve would suggest? |

### Mean return
```
Mean = (1/n) × Σ Rᵢ
```
Just the plain average of daily returns. It tells you about typical performance — but the project's goal isn't to maximize this. It's about controlling *risk*, which brings us to variance.

### Variance and standard deviation
```
Variance     = (1/(n−1)) × Σ (Rᵢ − Mean)²
Std. Dev.(σ) = √Variance
```
Squaring the deviations stops positive and negative swings from cancelling out. Standard deviation is easier to interpret because it's back in the same units as the returns themselves (e.g., "about 1% per day").

### Annualized volatility
Daily volatility is hard to compare with "yearly risk," so we scale it up assuming ~252 trading days a year:

```
Annual Volatility = Daily Volatility × √252
```

*(This works because variance roughly scales with time, so standard deviation scales with the square root of time.)*

### Skewness and kurtosis
- **Skewness** tells you if losses or gains tend to be more extreme. Negative skew = nastier downside surprises.
- **Kurtosis** tells you if extreme days happen *more often* than a standard bell-curve would predict — which is common in real financial markets.

## 2.3 Covariance: do two things move together?

```
Cov(R_S, R_F) = (1/(n−1)) × Σ (R_Sᵢ − Mean_S)(R_Fᵢ − Mean_F)
```

- **Positive covariance** → spot and futures tend to rise and fall together
- **Negative covariance** → they tend to move in opposite directions
- **Near-zero covariance** → little relationship

## 2.4 Correlation: covariance, standardized

Covariance's problem is that its size depends on the units involved, making it hard to interpret on its own. Correlation fixes this by scaling it into a range of −1 to +1:

```
Correlation = Cov(R_S, R_F) / (σ_S × σ_F)
```

| Value | Meaning |
|---|---|
| ≈ +1 | Move together, strongly |
| ≈ 0 | Little linear relationship |
| ≈ −1 | Move in opposite directions, strongly |

**Why this matters for hedging:** a hedge only works well when spot and futures are *reliably* related. High correlation is a good sign — but on its own it doesn't tell you the *right amount* of futures to use. For that, we need the next section.

---

# PART 3 — The Core Math: Finding the Optimal Hedge Ratio

This is the heart of the project. Everything in Parts 1 and 2 exists to set this part up.

## 3.1 Restating the goal

We want to choose the hedge ratio `h` that makes the hedged portfolio's variance as small as possible:

```
Minimize:  Var(R_S − h × R_F)     over all possible values of h
```

## 3.2 Deriving the formula (step by step)

Start by expanding the variance using standard variance rules:

```
Var(R_S − h·R_F) = Var(R_S) + h² · Var(R_F) − 2h · Cov(R_S, R_F)
```

To find the minimum, take the derivative with respect to `h` and set it to zero (this is just calculus's standard trick for finding the bottom of a curve):

```
d/dh [ Var(R_S) + h²·Var(R_F) − 2h·Cov(R_S,R_F) ] = 0

→  2h·Var(R_F) − 2·Cov(R_S,R_F) = 0

→  h·Var(R_F) = Cov(R_S,R_F)
```

Solving for `h` gives the final result:

```
┌─────────────────────────────────────────┐
│                                           │
│      h* = Cov(R_S, R_F) / Var(R_F)       │
│                                           │
└─────────────────────────────────────────┘
```

This is the **Minimum Variance Optimal Hedge Ratio**.

**In plain English:** it asks two questions and combines the answers —
1. *How much do spot and futures move together?* (the covariance, on top)
2. *How jumpy is the futures contract on its own?* (the variance, on the bottom)

If futures are very volatile relative to how well they track spot, you need *less* of them in your hedge. If they track spot closely and aren't excessively jumpy, you can use *more* of them.

## 3.3 Reading the result

| If h* is... | It means... |
|---|---|
| `h* = 1` | A 1-for-1 hedge is statistically optimal |
| `h* < 1` | Use proportionally *less* futures exposure than a naive 1:1 hedge |
| `h* > 1` | Use proportionally *more* futures exposure than a naive 1:1 hedge |

## 3.4 Why not just always use h = 1?

A "naive" hedge just assumes spot and futures move identically every day (`h = 1`), giving `R_H = R_S − R_F`. This is rarely exactly true. The data-driven `h*` instead reflects the *actual historical relationship*, which is why it typically produces a smaller hedged variance than the naive assumption.

## 3.5 Cross-checking with regression (OLS)

As a sanity check, the project also runs an **Ordinary Least Squares (OLS)** regression:

```
R_S = α + β·R_F + ε
```

- `α` (alpha) — the estimated spot return when futures return is zero
- `β` (beta) — how sensitive spot returns are to futures returns
- `ε` (epsilon) — the leftover, unexplained part of each day's return

OLS finds `α` and `β` by minimizing the sum of squared errors between the actual and predicted spot returns.

**The neat result:** mathematically,

```
β = Cov(R_S, R_F) / Var(R_F)   =   h*
```

Beta from the regression and the optimal hedge ratio from Part 3.2 are *the same formula*. This gives the project a built-in cross-check — if the two numbers come out different, something in the calculation is wrong.

### R-squared: how good is the fit?
```
R² = 1 − (Sum of Squared Residuals / Total Sum of Squares)
```
If `R² = 0.96`, it means about 96% of the daily variation in spot returns is explained by the fitted relationship with futures returns. It's a measure of *how good the relationship is* — not a hedge ratio itself, and shouldn't be confused with one.

---

# PART 4 — Turning Raw Data Into a Result

## 4.1 The full pipeline, at a glance

```
NSE Historical Data
        │
        ▼
Collect raw spot + raw futures data
        │
        ▼
Clean & validate (remove duplicates, fix dates, handle holidays)
        │
        ▼
Build a continuous futures series (handle contract expiry/rollover)
        │
        ▼
Align spot and futures by date (inner join)
        │
        ▼
Compute log returns
        │
        ▼
Descriptive statistics → Covariance & Correlation
        │
        ▼
Compute h* (optimal hedge ratio)  +  OLS cross-check
        │
        ▼
Build the hedged portfolio:  R_H = R_S − h*·R_F
        │
        ▼
Measure hedging effectiveness, volatility change, drawdown, basis
        │
        ▼
Rolling hedge ratio (does h* change over time?)
        │
        ▼
Interpret results
```

## 4.2 Why futures need a "continuous series"

Futures contracts **expire** — a January contract stops trading and a February contract takes over, and so on. You can't just follow one contract forever, so the project stitches contracts together into one continuous series so returns can be computed across the whole time period without artificial jumps at expiry dates.

### The rollover rule
This project switches from the expiring contract to the next one **5 trading days before expiry**:

- **Too late (waiting until expiry):** risks the practical complications of trading right at settlement.
- **Too early:** unnecessarily moves away from the most actively-traded, most representative contract.
- **5 days beforehand:** a reasonable, consistent middle ground — a methodology choice, not a universal rule.

## 4.3 Why the two datasets are joined with an "inner join"

To compute covariance, we need *matched pairs* — a spot return and a futures return for the *same day*. An inner join keeps only the dates that exist in **both** datasets:

**Spot**
| Date | Spot |
|---|---:|
| Jan 1 | 100 |
| Jan 2 | 101 |
| Jan 3 | 99 |

**Futures**
| Date | Futures |
|---|---:|
| Jan 1 | 102 |
| Jan 3 | 100 |
| Jan 4 | 103 |

**Result (inner join)**
| Date | Spot | Futures |
|---|---:|---:|
| Jan 1 | 100 | 102 |
| Jan 3 | 99 | 100 |

Jan 2 and Jan 4 are dropped because they're missing from one side.

**Why not just fill in the missing values instead?** Artificially inventing prices for missing days would distort the returns and covariance calculations, and could quietly bias the hedge ratio. Using only genuinely matched observations is the safer, more honest approach.

---

# PART 5 — Reading and Trusting the Results

## 5.1 A step-by-step way to interpret any run of this project

1. **Check correlation first** — do spot and futures actually move together? If not, hedging with futures won't help much.
2. **Compute h\*** — how much futures exposure minimizes historical variance?
3. **Verify with OLS** — does `β ≈ h*`? Check `R²` to see how strong the relationship is.
4. **Build the hedge** — compute `R_H = R_S − h*·R_F`.
5. **Compare variances** — is `Var(R_H)` meaningfully smaller than `Var(R_S)`?
6. **Compare annualized volatility** — how does the risk look on a yearly basis, before vs. after hedging?
7. **Compare maximum drawdown** — did the worst historical losing streak get smaller?
8. **Check the basis** — is the market mostly in contango or backwardation? Large or unstable basis swings are a warning sign for basis risk.

## 5.2 Measuring hedging effectiveness

```
Hedging Effectiveness (HE) = 1 − [ Var(R_H) / Var(R_S) ]
```

**Worked example:**
```
Var(R_S) = 0.0001
Var(R_H) = 0.000004

HE = 1 − (0.000004 / 0.0001) = 0.96  →  96%
```

This means the hedge reduced return variance by 96% over the analyzed period.

**Why measure effectiveness by variance instead of just profit?** Because a hedge can reduce *both* gains and losses (that's the nature of an offsetting position) — so looking at profit alone doesn't tell you whether risk was actually reduced. Variance reduction is the metric that actually matches what the hedge was designed to do.

## 5.3 Maximum drawdown

```
Drawdown(t) = [Cumulative Value(t) / Running Peak(t)] − 1
Max Drawdown = the most negative Drawdown(t) observed
```

This answers: *"At the worst point, how far below its previous high did the portfolio fall?"* It captures something variance doesn't — the *severity of a sustained losing streak*, not just day-to-day jumpiness.

## 5.4 Rolling hedge ratio: does h* stay constant?

Instead of computing one hedge ratio for the whole sample, we can recompute it in a moving 60-day window:

```
h*(t) = Cov(R_S, R_F) over the last 60 days  /  Var(R_F) over the last 60 days
```

**Why 60 days?** It's roughly 3 months of trading (~20–21 trading days/month) — long enough to avoid excessive noise, short enough to react to changing market conditions. It's a reasonable balance, not a universally "correct" number.

If the rolling `h*(t)` line is fairly stable, that supports using one fixed hedge ratio. If it swings a lot, it's a signal that the spot–futures relationship isn't constant over time.

## 5.5 Example results and how to read them

A sample run of this project might report:

| Metric | Value | What it means |
|---|---|---|
| Optimal hedge ratio (h\*) | 0.95 | Use ~95% of a 1:1 futures hedge |
| Correlation | 0.98 | Very strong spot–futures relationship |
| R² (OLS) | 0.96 | ~96% of spot return variation explained by futures |
| Hedging effectiveness | 96% | Variance cut by ~96% in-sample |
| Annualized volatility, unhedged | 15.5% | Risk before hedging |
| Annualized volatility, hedged | 3.0% | Risk after hedging |

**Important caveat:** all of these numbers are specific to the historical sample used. They describe *what happened*, not a guarantee of *what will happen*. A hedge ratio that worked well in the past isn't promised to work equally well going forward.

## 5.6 Limitations — read this before drawing big conclusions

- **Limited sample period** — a few months of data won't capture every kind of market condition (crashes, rallies, sideways markets).
- **Historical ≠ future** — `h*` is estimated from the past; there's no guarantee it holds going forward.
- **Constant-hedge assumption** — the main result uses one ratio for the whole period, even though the rolling analysis shows this can drift.
- **Costs are assumptions** — the portfolio ledger includes configurable fees, slippage, rollover costs, and margin funding. These are scenarios; taxes by category and actual broker/exchange charges are not replicated.
- **No margin modeling** — futures require margin; this project's return-based analysis doesn't simulate the cash-flow/margin side of actually running the position.
- **Contract sizing not modeled** — turning `h*` into an actual whole number of futures contracts requires knowing contract multipliers and current notional values (see 5.7).

## 5.7 From a ratio to an actual trade

`h*` is a ratio in *return space*. Turning it into "how many futures contracts do I actually buy or sell" requires a further step:

```
Number of Contracts ≈ h* × (Value of Spot Position / Value of One Futures Contract)
```

This also needs to account for integer contract constraints (you can't trade half a contract) and the current contract specifications on the exchange — details this project's statistical analysis doesn't cover, but any real-world implementation would need to.

---

# Quick Reference: The Whole Project in One Page

**The setup:**
```
You hold a spot position with return R_S.
You hedge it with a futures position, weighted by h, with return R_F.
Hedged return:  R_H = R_S − h·R_F
```

**The optimization:**
```
Find h that minimizes Var(R_H)
```

**The solution:**
```
h* = Cov(R_S, R_F) / Var(R_F)     (also equals the OLS regression slope, β)
```

**The evaluation:**
```
Hedging Effectiveness = 1 − [ Var(R_H) / Var(R_S) ]
```

**The logical flow:**
```
Market Data → Returns → Spot-Futures Relationship
→ Optimal Hedge Ratio → Hedged Portfolio → Risk Reduction
```

---

# Glossary

| Term | Meaning |
|---|---|
| Asset | Something with economic value |
| Spot price | Current market price for immediate ownership |
| Futures price | Agreed price for a contract settled in the future |
| Derivative | Instrument whose value depends on another asset |
| Log return | `ln(P_t / P_(t-1))` — the standard return measure used in this project |
| Variance | How spread out returns are around their average |
| Standard deviation | Square root of variance; same units as the return |
| Volatility | General term for how much returns fluctuate |
| Covariance | Measure of whether two return series move together |
| Correlation | Covariance scaled to a range of −1 to +1 |
| Hedge | A position taken to reduce the risk of another position |
| Hedge ratio (h) | How much hedging instrument to use per unit of exposure |
| Minimum variance hedge | The hedge ratio that minimizes hedged portfolio variance |
| OLS | Ordinary Least Squares — the regression method used as a cross-check |
| Alpha (α) | Regression intercept |
| Beta (β) | Regression slope; equals h* in this context |
| R² | Proportion of variance in spot returns explained by the regression |
| Hedging effectiveness | Percentage reduction in variance from hedging |
| Basis | Futures price minus spot price |
| Contango | Futures priced above spot |
| Backwardation | Futures priced below spot |
| Drawdown | Decline from a previous cumulative peak |
| Maximum drawdown | The single largest peak-to-trough decline observed |
| Rollover | Switching from an expiring futures contract to the next one |
| Continuous futures series | A stitched-together futures price series spanning multiple contract expiries |


## Updated portfolio accounting and validation

The log-return equations above describe the statistical study. A weighted difference of log returns is not an exact futures portfolio return. The dashboard now uses a separate cash ledger for rupee outcomes: fixed index-equivalent spot units plus historical whole futures lots, cash-marked daily using price differences. Costs cover entry, resizing, both rollover legs, and final exit. Margin is externally funded collateral; only funding expense reduces equity. Calendar days count for funding. Closing prices approximate exchange settlement prices.

Strategies are compared over identical out-of-sample dates. Fixed h* is fitted before the test period; the rolling h* uses only earlier returns. The worst-day tab uses this prior-fitted portfolio ledger. Starting capital is included in drawdown. Contract expiries and UDiFF lot sizes come from the actual archive rather than current contract rules.

See README.md and generated results files for current numerical results and assumptions. Any illustrative numbers earlier in this guide are examples, not a fresh backtest.

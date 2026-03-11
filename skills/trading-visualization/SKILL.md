---
name: trading-visualization
description: Professional trading charts including candlesticks, equity curves, drawdowns, correlation heatmaps, and return distributions
---

# Trading Visualization

Visualization is the primary interface between a trader and their data. Charts reveal patterns that tables and numbers cannot: breakdowns in strategy, regime transitions, clustering of losses, and the shape of risk. A well-designed chart communicates more in a glance than a page of statistics.

**Three uses of trading charts:**

1. **Pattern recognition** — Spot structural changes in price, volume, and momentum that quantitative filters miss.
2. **Strategy evaluation** — Equity curves, drawdown plots, and return distributions expose whether a strategy is robust or curve-fit.
3. **Reporting** — Communicate performance to stakeholders, journals, or your future self with publication-quality visuals.

---

## Chart Types Covered

| Chart Type | Purpose | Library |
|------------|---------|---------|
| Candlestick | OHLCV price action with overlays | mplfinance |
| Equity curve | Portfolio value over time | matplotlib |
| Drawdown | Underwater equity plot | matplotlib |
| Return distribution | Histogram + normal fit | matplotlib |
| Correlation heatmap | Cross-asset correlation matrix | matplotlib / seaborn |
| Trade markers | Entry/exit points on price chart | mplfinance / matplotlib |
| Indicator panels | RSI, MACD below price chart | mplfinance |
| Position timeline | When positions were held | matplotlib |

---

## Libraries

### mplfinance

Best for candlestick charts. Built on matplotlib with finance-specific defaults.

```bash
uv pip install mplfinance
```

```python
import mplfinance as mpf

# Basic candlestick from a DataFrame with DatetimeIndex
# Columns: Open, High, Low, Close, Volume
mpf.plot(df, type="candle", volume=True, style="charles")
```

Key features:
- Native OHLCV support — pass a DataFrame directly
- Built-in volume bars
- `addplot` for overlays (moving averages, Bollinger Bands)
- Custom styles via `mpf.make_mpf_style()`

### matplotlib

General purpose, most flexible. Use when you need full control over layout.

```bash
uv pip install matplotlib
```

```python
import matplotlib.pyplot as plt

fig, axes = plt.subplots(2, 1, figsize=(14, 8), height_ratios=[3, 1],
                         sharex=True)
axes[0].plot(dates, equity, color="#00ff88")
axes[1].fill_between(dates, drawdown, 0, color="#ff4444", alpha=0.5)
```

### plotly

Interactive charts rendered as HTML. Best for exploration and dashboards.

```bash
uv pip install plotly
```

```python
import plotly.graph_objects as go

fig = go.Figure(data=[go.Candlestick(
    x=df.index, open=df["Open"], high=df["High"],
    low=df["Low"], close=df["Close"]
)])
fig.update_layout(template="plotly_dark")
fig.write_html("chart.html")
```

---

## Styling: Dark Theme Default

Trading terminals use dark backgrounds by default. All charts in this skill follow that convention.

### Quick dark theme setup

```python
import matplotlib.pyplot as plt

plt.style.use("dark_background")
plt.rcParams.update({
    "figure.facecolor": "#1a1a2e",
    "axes.facecolor": "#1a1a2e",
    "axes.edgecolor": "#333333",
    "grid.color": "#333333",
    "grid.alpha": 0.4,
    "text.color": "#e0e0e0",
    "xtick.color": "#aaaaaa",
    "ytick.color": "#aaaaaa",
})
```

### Trading color scheme

| Element | Color | Hex |
|---------|-------|-----|
| Bullish / profit | Green | `#00ff88` |
| Bearish / loss | Red | `#ff4444` |
| Neutral / info | Blue | `#4488ff` |
| Warning | Amber | `#ffaa00` |
| MA short | Orange | `#ff6600` |
| MA long | Blue | `#3399ff` |
| MA signal | Yellow | `#ffcc00` |

See `references/styling_guide.md` for complete typography, layout ratios, and export settings.

---

## Chart Composition: Multi-Panel Layout

Most trading charts need multiple synchronized panels — price on top, volume in the middle, indicators at the bottom.

### Stacked panels with shared x-axis

```python
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

fig = plt.figure(figsize=(14, 10))
gs = gridspec.GridSpec(3, 1, height_ratios=[3, 1, 1], hspace=0.05)

ax_price = fig.add_subplot(gs[0])
ax_volume = fig.add_subplot(gs[1], sharex=ax_price)
ax_rsi = fig.add_subplot(gs[2], sharex=ax_price)

# Hide x-tick labels on upper panels
ax_price.tick_params(labelbottom=False)
ax_volume.tick_params(labelbottom=False)
```

### Panel height ratios

| Layout | Ratios | Use Case |
|--------|--------|----------|
| Price + Volume | `[3, 1]` | Simple OHLCV chart |
| Price + Volume + Indicator | `[3, 1, 1]` | Standard analysis view |
| Equity + Drawdown | `[2, 1]` | Performance review |
| Price + RSI + MACD | `[3, 1, 1]` | Full indicator stack |

---

## Candlestick Charts with Overlays

```python
import mplfinance as mpf
import pandas as pd

# df: DataFrame with DatetimeIndex, columns Open/High/Low/Close/Volume
ema20 = df["Close"].ewm(span=20).mean()
ema50 = df["Close"].ewm(span=50).mean()

ap = [
    mpf.make_addplot(ema20, color="#ff6600", width=1.2),
    mpf.make_addplot(ema50, color="#3399ff", width=1.2),
]

style = mpf.make_mpf_style(
    base_mpf_style="nightclouds",
    marketcolors=mpf.make_marketcolors(
        up="#00ff88", down="#ff4444",
        wick={"up": "#00ff88", "down": "#ff4444"},
        edge={"up": "#00ff88", "down": "#ff4444"},
        volume={"up": "#00ff88", "down": "#ff4444"},
    ),
    facecolor="#1a1a2e", figcolor="#1a1a2e",
    gridcolor="#333333", gridstyle="--",
)

mpf.plot(df, type="candle", style=style, addplot=ap,
         volume=True, figsize=(14, 8),
         title="Token / SOL — 15m", savefig="candles.png")
```

---

## Equity Curve with Drawdown Panel

```python
import numpy as np
import matplotlib.pyplot as plt

def plot_equity_drawdown(equity: pd.Series, title: str = "Portfolio") -> plt.Figure:
    """Plot equity curve with drawdown panel below."""
    peak = equity.cummax()
    drawdown = (equity - peak) / peak

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8),
                                    height_ratios=[2, 1], sharex=True)
    ax1.plot(equity.index, equity, color="#00ff88", linewidth=1.5)
    ax1.plot(equity.index, peak, color="#555555", linewidth=0.8,
             linestyle="--", label="Peak")
    ax1.set_title(title, fontsize=14, fontweight="bold", color="white")
    ax1.set_ylabel("Portfolio Value", fontsize=11)
    ax1.legend(loc="upper left")
    ax1.grid(True, alpha=0.3)

    ax2.fill_between(equity.index, drawdown, 0, color="#ff4444", alpha=0.5)
    ax2.set_ylabel("Drawdown", fontsize=11)
    ax2.set_xlabel("Date", fontsize=11)
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()
    return fig
```

---

## Return Distribution

```python
from scipy import stats

def plot_return_distribution(returns: pd.Series) -> plt.Figure:
    """Histogram of returns with normal fit and risk metrics."""
    fig, ax = plt.subplots(figsize=(10, 6))

    ax.hist(returns, bins=50, density=True, alpha=0.7,
            color="#4488ff", edgecolor="#333333")

    # Normal fit overlay
    mu, sigma = returns.mean(), returns.std()
    x = np.linspace(returns.min(), returns.max(), 200)
    ax.plot(x, stats.norm.pdf(x, mu, sigma), color="#ffaa00",
            linewidth=2, label=f"Normal(μ={mu:.4f}, σ={sigma:.4f})")

    # VaR line
    var_95 = returns.quantile(0.05)
    ax.axvline(var_95, color="#ff4444", linestyle="--",
               label=f"VaR 95%: {var_95:.4f}")

    ax.set_title("Return Distribution", fontsize=14, fontweight="bold")
    ax.set_xlabel("Return", fontsize=11)
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig
```

---

## Correlation Heatmap

```python
def plot_correlation_heatmap(returns_df: pd.DataFrame) -> plt.Figure:
    """Correlation matrix heatmap with annotations."""
    corr = returns_df.corr()
    fig, ax = plt.subplots(figsize=(10, 8))
    im = ax.imshow(corr, cmap="RdYlGn", vmin=-1, vmax=1, aspect="auto")

    ax.set_xticks(range(len(corr.columns)))
    ax.set_yticks(range(len(corr.columns)))
    ax.set_xticklabels(corr.columns, rotation=45, ha="right")
    ax.set_yticklabels(corr.columns)

    for i in range(len(corr)):
        for j in range(len(corr)):
            ax.text(j, i, f"{corr.iloc[i, j]:.2f}",
                    ha="center", va="center", fontsize=9,
                    color="black" if abs(corr.iloc[i, j]) < 0.5 else "white")

    fig.colorbar(im, ax=ax, shrink=0.8)
    ax.set_title("Correlation Matrix", fontsize=14, fontweight="bold")
    fig.tight_layout()
    return fig
```

---

## Trade Markers on Price Chart

```python
def plot_trades_on_price(
    price: pd.Series,
    entries: pd.DataFrame,  # columns: date, price, side
    exits: pd.DataFrame,    # columns: date, price, pnl
) -> plt.Figure:
    """Price chart with entry/exit markers."""
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(price.index, price, color="#aaaaaa", linewidth=1)

    # Entry markers
    buy_mask = entries["side"] == "long"
    ax.scatter(entries.loc[buy_mask, "date"], entries.loc[buy_mask, "price"],
               marker="^", color="#00ff88", s=100, zorder=5, label="Buy")
    ax.scatter(entries.loc[~buy_mask, "date"], entries.loc[~buy_mask, "price"],
               marker="v", color="#ff4444", s=100, zorder=5, label="Short")

    # Exit markers
    win_mask = exits["pnl"] > 0
    ax.scatter(exits.loc[win_mask, "date"], exits.loc[win_mask, "price"],
               marker="x", color="#00ff88", s=80, zorder=5)
    ax.scatter(exits.loc[~win_mask, "date"], exits.loc[~win_mask, "price"],
               marker="x", color="#ff4444", s=80, zorder=5)

    ax.set_title("Trades on Price", fontsize=14, fontweight="bold")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig
```

---

## Output Formats

| Format | Method | Use Case |
|--------|--------|----------|
| PNG | `fig.savefig("chart.png", dpi=150)` | Sharing, embedding |
| SVG | `fig.savefig("chart.svg")` | Editing, scaling |
| HTML | `fig.write_html("chart.html")` (plotly) | Interactive exploration |
| Inline | `plt.show()` | Jupyter notebooks |

### Saving with dark background

```python
fig.savefig("chart.png", dpi=150, facecolor=fig.get_facecolor(),
            edgecolor="none", bbox_inches="tight")
```

---

## Integration with Other Skills

| Skill | Integration |
|-------|-------------|
| `pandas-ta` | Compute indicators, pass to addplot overlays |
| `vectorbt` | Extract equity curve and trade list for visualization |
| `portfolio-analytics` | Plot Sharpe, drawdown, and return metrics |
| `risk-management` | Visualize position limits and exposure over time |
| `position-sizing` | Chart position size vs account equity over time |
| `regime-detection` | Color background by detected market regime |
| `correlation-analysis` | Generate correlation heatmaps from return data |

---

## Files

### References
- `references/chart_recipes.md` — Complete code recipes for six common chart types
- `references/styling_guide.md` — Dark theme setup, colors, typography, layout, and export settings

### Scripts
- `scripts/chart_generator.py` — Generate four chart types from synthetic data (candlestick, equity, returns, trades)
- `scripts/performance_report.py` — Multi-chart performance report with summary statistics

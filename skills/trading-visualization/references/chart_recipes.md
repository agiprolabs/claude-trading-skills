# Chart Recipes

Copy-paste-ready recipes for six common trading chart types with dark theme styling.

## Recipe 1: Candlestick with Moving Averages

```python
import pandas as pd
import mplfinance as mpf

def candlestick_with_ma(df: pd.DataFrame, short: int = 20, long: int = 50,
                        save_path: str = "candles.png") -> None:
    """Candlestick chart with EMA overlays and volume bars."""
    ema_short = df["Close"].ewm(span=short).mean()
    ema_long = df["Close"].ewm(span=long).mean()

    ap = [
        mpf.make_addplot(ema_short, color="#ff6600", width=1.2,
                         label=f"EMA {short}"),
        mpf.make_addplot(ema_long, color="#3399ff", width=1.2,
                         label=f"EMA {long}"),
    ]

    mc = mpf.make_marketcolors(
        up="#00ff88", down="#ff4444",
        wick={"up": "#00ff88", "down": "#ff4444"},
        edge={"up": "#00ff88", "down": "#ff4444"},
        volume={"up": "#00ff88", "down": "#ff4444"},
    )
    style = mpf.make_mpf_style(
        base_mpf_style="nightclouds", marketcolors=mc,
        facecolor="#1a1a2e", figcolor="#1a1a2e",
        gridcolor="#333333", gridstyle="--",
    )

    mpf.plot(df, type="candle", style=style, addplot=ap,
             volume=True, figsize=(14, 8),
             title="\nCandlestick with EMAs",
             savefig=dict(fname=save_path, dpi=150, facecolor="#1a1a2e"))
```

---

## Recipe 2: Equity Curve with Drawdown

```python
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def equity_with_drawdown(equity: pd.Series,
                         save_path: str = "equity.png") -> plt.Figure:
    """Two-panel chart: equity on top, drawdown filled area below."""
    plt.style.use("dark_background")
    peak = equity.cummax()
    dd = (equity - peak) / peak

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8),
                                    height_ratios=[2, 1], sharex=True)
    fig.patch.set_facecolor("#1a1a2e")
    for ax in (ax1, ax2):
        ax.set_facecolor("#1a1a2e")

    ax1.plot(equity.index, equity, color="#00ff88", linewidth=1.5,
             label="Equity")
    ax1.plot(equity.index, peak, color="#555555", linewidth=0.8,
             linestyle="--", label="Peak")
    ax1.set_ylabel("Portfolio Value", fontsize=11)
    ax1.set_title("Equity Curve", fontsize=14, fontweight="bold")
    ax1.legend(loc="upper left")
    ax1.grid(True, alpha=0.3, color="#333333")

    ax2.fill_between(equity.index, dd, 0, color="#ff4444", alpha=0.5)
    ax2.plot(equity.index, dd, color="#ff4444", linewidth=0.8)
    ax2.set_ylabel("Drawdown", fontsize=11)
    ax2.set_xlabel("Date", fontsize=11)
    ax2.grid(True, alpha=0.3, color="#333333")

    fig.tight_layout()
    fig.savefig(save_path, dpi=150, facecolor="#1a1a2e",
                edgecolor="none", bbox_inches="tight")
    return fig
```

---

## Recipe 3: Multi-Indicator Panel (Price + RSI + MACD)

```python
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

def multi_indicator_panel(df: pd.DataFrame,
                          save_path: str = "indicators.png") -> plt.Figure:
    """Three-panel chart: price with MAs, RSI, and MACD."""
    plt.style.use("dark_background")
    close = df["Close"]

    # Compute indicators
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9).mean()
    macd_hist = macd_line - signal_line

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    fig = plt.figure(figsize=(14, 10))
    fig.patch.set_facecolor("#1a1a2e")
    gs = gridspec.GridSpec(3, 1, height_ratios=[3, 1, 1], hspace=0.05)

    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax3 = fig.add_subplot(gs[2], sharex=ax1)
    for ax in (ax1, ax2, ax3):
        ax.set_facecolor("#1a1a2e")
        ax.grid(True, alpha=0.3, color="#333333")

    # Price panel
    ax1.plot(close.index, close, color="#e0e0e0", linewidth=1.2)
    ax1.plot(close.index, close.rolling(20).mean(), color="#ff6600",
             linewidth=1, label="SMA 20")
    ax1.set_ylabel("Price", fontsize=11)
    ax1.legend(loc="upper left", fontsize=9)
    ax1.tick_params(labelbottom=False)

    # RSI panel
    ax2.plot(rsi.index, rsi, color="#4488ff", linewidth=1)
    ax2.axhline(70, color="#ff4444", linewidth=0.7, linestyle="--")
    ax2.axhline(30, color="#00ff88", linewidth=0.7, linestyle="--")
    ax2.set_ylabel("RSI", fontsize=11)
    ax2.set_ylim(0, 100)
    ax2.tick_params(labelbottom=False)

    # MACD panel
    colors = ["#00ff88" if v >= 0 else "#ff4444" for v in macd_hist]
    ax3.bar(close.index, macd_hist, color=colors, alpha=0.6, width=0.8)
    ax3.plot(close.index, macd_line, color="#4488ff", linewidth=1)
    ax3.plot(close.index, signal_line, color="#ffaa00", linewidth=1)
    ax3.set_ylabel("MACD", fontsize=11)
    ax3.set_xlabel("Date", fontsize=11)

    fig.savefig(save_path, dpi=150, facecolor="#1a1a2e",
                edgecolor="none", bbox_inches="tight")
    return fig
```

---

## Recipe 4: Correlation Heatmap

```python
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def correlation_heatmap(returns_df: pd.DataFrame,
                        save_path: str = "corr.png") -> plt.Figure:
    """Annotated heatmap with diverging red-white-green scale."""
    plt.style.use("dark_background")
    corr = returns_df.corr()
    n = len(corr)

    fig, ax = plt.subplots(figsize=(max(8, n * 1.2), max(6, n)))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")

    im = ax.imshow(corr.values, cmap="RdYlGn", vmin=-1, vmax=1,
                   aspect="auto")
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(corr.columns, rotation=45, ha="right", fontsize=10)
    ax.set_yticklabels(corr.columns, fontsize=10)

    for i in range(n):
        for j in range(n):
            val = corr.iloc[i, j]
            color = "black" if abs(val) < 0.5 else "white"
            ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                    fontsize=9, color=color)

    fig.colorbar(im, ax=ax, shrink=0.8, label="Correlation")
    ax.set_title("Asset Correlation Matrix", fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(save_path, dpi=150, facecolor="#1a1a2e",
                edgecolor="none", bbox_inches="tight")
    return fig
```

---

## Recipe 5: Return Distribution with VaR/CVaR

```python
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats

def return_distribution(returns: pd.Series,
                        save_path: str = "returns_dist.png") -> plt.Figure:
    """Histogram with normal fit, VaR, and CVaR lines."""
    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")

    ax.hist(returns, bins=50, density=True, alpha=0.7,
            color="#4488ff", edgecolor="#222222")

    mu, sigma = returns.mean(), returns.std()
    x = np.linspace(returns.min(), returns.max(), 200)
    ax.plot(x, stats.norm.pdf(x, mu, sigma), color="#ffaa00",
            linewidth=2, label=f"Normal (μ={mu:.4f}, σ={sigma:.4f})")

    var_95 = float(returns.quantile(0.05))
    cvar_95 = float(returns[returns <= var_95].mean())
    ax.axvline(var_95, color="#ff4444", linestyle="--", linewidth=1.5,
               label=f"VaR 95%: {var_95:.4f}")
    ax.axvline(cvar_95, color="#ff6600", linestyle=":", linewidth=1.5,
               label=f"CVaR 95%: {cvar_95:.4f}")

    ax.set_title("Return Distribution", fontsize=14, fontweight="bold")
    ax.set_xlabel("Return", fontsize=11)
    ax.set_ylabel("Density", fontsize=11)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, color="#333333")
    fig.tight_layout()
    fig.savefig(save_path, dpi=150, facecolor="#1a1a2e",
                edgecolor="none", bbox_inches="tight")
    return fig
```

---

## Recipe 6: Trade Performance Scatter

```python
import pandas as pd
import matplotlib.pyplot as plt

def trade_scatter(trades: pd.DataFrame,
                  save_path: str = "trade_scatter.png") -> plt.Figure:
    """Scatter plot: return vs holding period, colored by win/loss."""
    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(10, 7))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")

    wins = trades[trades["return_pct"] >= 0]
    losses = trades[trades["return_pct"] < 0]

    ax.scatter(wins["hold_hours"], wins["return_pct"],
               s=wins["size_usd"] / 10, color="#00ff88", alpha=0.6,
               label=f"Wins ({len(wins)})")
    ax.scatter(losses["hold_hours"], losses["return_pct"],
               s=losses["size_usd"].abs() / 10, color="#ff4444", alpha=0.6,
               label=f"Losses ({len(losses)})")

    ax.axhline(0, color="#555555", linewidth=0.8)
    ax.set_xlabel("Holding Period (hours)", fontsize=11)
    ax.set_ylabel("Return %", fontsize=11)
    ax.set_title("Trade Performance", fontsize=14, fontweight="bold")
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3, color="#333333")
    fig.tight_layout()
    fig.savefig(save_path, dpi=150, facecolor="#1a1a2e",
                edgecolor="none", bbox_inches="tight")
    return fig
```

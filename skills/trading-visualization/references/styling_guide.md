# Styling Guide

Complete reference for dark theme trading chart aesthetics: colors, typography, layout ratios, and export settings.

---

## Dark Theme Setup

### Method 1: Style sheet + rcParams override

```python
import matplotlib.pyplot as plt

plt.style.use("dark_background")
plt.rcParams.update({
    "figure.facecolor": "#1a1a2e",
    "axes.facecolor": "#1a1a2e",
    "axes.edgecolor": "#333333",
    "axes.labelcolor": "#e0e0e0",
    "axes.titleweight": "bold",
    "grid.color": "#333333",
    "grid.alpha": 0.4,
    "grid.linestyle": "--",
    "text.color": "#e0e0e0",
    "xtick.color": "#aaaaaa",
    "ytick.color": "#aaaaaa",
    "legend.facecolor": "#1a1a2e",
    "legend.edgecolor": "#333333",
    "figure.figsize": [14, 8],
    "savefig.facecolor": "#1a1a2e",
    "savefig.edgecolor": "none",
    "savefig.dpi": 150,
})
```

### Method 2: Per-figure styling (no global mutation)

```python
fig, ax = plt.subplots(figsize=(14, 8))
fig.patch.set_facecolor("#1a1a2e")
ax.set_facecolor("#1a1a2e")
ax.spines["bottom"].set_color("#333333")
ax.spines["left"].set_color("#333333")
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.tick_params(colors="#aaaaaa")
ax.grid(True, alpha=0.3, color="#333333", linestyle="--")
```

### Method 3: mplfinance custom style

```python
import mplfinance as mpf

mc = mpf.make_marketcolors(
    up="#00ff88", down="#ff4444",
    wick={"up": "#00ff88", "down": "#ff4444"},
    edge={"up": "#00ff88", "down": "#ff4444"},
    volume={"up": "#00ff88", "down": "#ff4444"},
)
dark_style = mpf.make_mpf_style(
    base_mpf_style="nightclouds",
    marketcolors=mc,
    facecolor="#1a1a2e",
    figcolor="#1a1a2e",
    gridcolor="#333333",
    gridstyle="--",
    y_on_right=True,
)
```

---

## Color Palette

### Primary trading colors

| Role | Name | Hex | RGB |
|------|------|-----|-----|
| Bullish / Profit | Green | `#00ff88` | (0, 255, 136) |
| Bearish / Loss | Red | `#ff4444` | (255, 68, 68) |
| Neutral / Info | Blue | `#4488ff` | (68, 136, 255) |
| Warning / Caution | Amber | `#ffaa00` | (255, 170, 0) |
| Background | Dark navy | `#1a1a2e` | (26, 26, 46) |
| Grid / Border | Dark gray | `#333333` | (51, 51, 51) |
| Text primary | Light gray | `#e0e0e0` | (224, 224, 224) |
| Text secondary | Mid gray | `#aaaaaa` | (170, 170, 170) |
| Muted element | Dim gray | `#555555` | (85, 85, 85) |

### Moving average colors

| Line | Color | Hex |
|------|-------|-----|
| MA short (10-20) | Orange | `#ff6600` |
| MA medium (50) | Blue | `#3399ff` |
| MA long (100-200) | Yellow | `#ffcc00` |

### Multi-series palette (for 5+ overlapping lines)

```python
SERIES_COLORS = [
    "#00ff88",  # green
    "#4488ff",  # blue
    "#ff6600",  # orange
    "#ffcc00",  # yellow
    "#cc44ff",  # purple
    "#ff4488",  # pink
    "#00cccc",  # teal
    "#ff8844",  # coral
]
```

### Alternative background: GitHub dark

Use `#0d1117` for a slightly cooler tone matching GitHub's dark mode.

---

## Typography

### Font sizes

| Element | Size | Weight | Color |
|---------|------|--------|-------|
| Chart title | 14pt | Bold | `#e0e0e0` |
| Axis label | 11pt | Normal | `#e0e0e0` |
| Tick label | 9pt | Normal | `#aaaaaa` |
| Legend text | 9-10pt | Normal | `#e0e0e0` |
| Annotation | 10pt | Normal | `#e0e0e0` |
| Stat box text | 10pt | Monospace | `#e0e0e0` |

### Applying fonts

```python
ax.set_title("Price Chart", fontsize=14, fontweight="bold", color="#e0e0e0")
ax.set_xlabel("Date", fontsize=11, color="#e0e0e0")
ax.set_ylabel("Price (SOL)", fontsize=11, color="#e0e0e0")
ax.tick_params(axis="both", labelsize=9, colors="#aaaaaa")
ax.legend(fontsize=9, facecolor="#1a1a2e", edgecolor="#333333")
```

### Stat box (performance summary on chart)

```python
stats_text = (
    f"Return: {total_return:.1%}\n"
    f"Sharpe: {sharpe:.2f}\n"
    f"Max DD: {max_dd:.1%}"
)
ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
        fontsize=10, fontfamily="monospace", color="#e0e0e0",
        verticalalignment="top",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#222233",
                  edgecolor="#333333", alpha=0.9))
```

---

## Layout Principles

### Figure sizes

| Chart Type | Size (inches) | Aspect |
|------------|---------------|--------|
| Full analysis (multi-panel) | `(14, 10)` | Wide |
| Standard chart | `(14, 8)` | Wide |
| Simple plot | `(10, 6)` | Standard |
| Heatmap (square) | `(10, 8)` | Near-square |
| Dashboard tile | `(7, 5)` | Compact |

### Multi-panel height ratios

| Layout | Ratios | Use |
|--------|--------|-----|
| Price + Volume | `[3, 1]` | Basic OHLCV |
| Equity + Drawdown | `[2, 1]` | Performance |
| Price + Vol + Indicator | `[3, 1, 1]` | Full analysis |
| Price + RSI + MACD | `[3, 1, 1]` | Indicator stack |
| 4-panel | `[3, 1, 1, 1]` | Deep analysis |

### Spacing

```python
# Option 1: tight_layout (simple)
fig.tight_layout()

# Option 2: constrained_layout (better for complex)
fig, axes = plt.subplots(3, 1, figsize=(14, 10),
                          constrained_layout=True)

# Option 3: GridSpec with hspace
gs = gridspec.GridSpec(3, 1, height_ratios=[3, 1, 1], hspace=0.05)
```

Use `hspace=0.05` for shared-axis panels (price + volume) to make them look connected. Use `hspace=0.15` or `tight_layout()` when panels are independent.

---

## Saving Charts

### Standard save

```python
fig.savefig("chart.png", dpi=150,
            facecolor=fig.get_facecolor(),
            edgecolor="none",
            bbox_inches="tight")
```

### DPI guidelines

| Use | DPI |
|-----|-----|
| Screen / sharing | 150 |
| Presentation | 200 |
| Publication / print | 300 |

### Format comparison

| Format | Size | Quality | Editable | Use |
|--------|------|---------|----------|-----|
| PNG | Medium | Raster | No | Default for sharing |
| SVG | Small | Vector | Yes | Editing, scaling |
| PDF | Medium | Vector | Partial | Reports, papers |
| HTML | Large | Interactive | N/A | Plotly dashboards |

### Transparent background (for embedding)

```python
fig.savefig("chart.png", dpi=150, transparent=True,
            bbox_inches="tight")
```

### Plotly dark template

```python
import plotly.io as pio

pio.templates["trading_dark"] = go.layout.Template(
    layout=dict(
        paper_bgcolor="#1a1a2e",
        plot_bgcolor="#1a1a2e",
        font=dict(color="#e0e0e0"),
        xaxis=dict(gridcolor="#333333"),
        yaxis=dict(gridcolor="#333333"),
    )
)
pio.templates.default = "trading_dark"
```

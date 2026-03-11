#!/usr/bin/env python3
"""Keyword-based sentiment analyzer for crypto social media text.

Scores text using curated bullish/bearish word lists without any ML model
or external dependencies. Includes a demo mode with 20 synthetic crypto
social media posts showing sentiment analysis in action.

Usage:
    python scripts/keyword_sentiment.py                # Demo with 20 synthetic posts
    python scripts/keyword_sentiment.py --demo         # Same as above (explicit)
    python scripts/keyword_sentiment.py --text "SOL is going to moon, super bullish"

Dependencies:
    None (stdlib only)
"""

import argparse
import math
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional


# ── Keyword Dictionaries ───────────────────────────────────────────

BULLISH_KEYWORDS: dict[str, int] = {
    # Strong bullish (weight 3)
    "moonshot": 3, "parabolic": 3, "generational": 3,
    # Moderate bullish (weight 2)
    "moon": 2, "bullish": 2, "breakout": 2, "accumulate": 2,
    "undervalued": 2, "rally": 2, "surge": 2, "soar": 2,
    "adoption": 2, "partnership": 2, "institutional": 2,
    "recovery": 2, "reversal": 2, "pumping": 2,
    # Mild bullish (weight 1)
    "buy": 1, "long": 1, "gem": 1, "rocket": 1, "ath": 1,
    "hodl": 1, "alpha": 1, "dip": 1, "support": 1,
    "bottom": 1, "green": 1, "gains": 1, "profit": 1,
    "lambo": 1, "diamond": 1, "strong": 1, "growth": 1,
    "upgrade": 1, "launch": 1, "listing": 1, "explosive": 1,
    "promising": 1, "opportunity": 1, "underrated": 1,
}

BEARISH_KEYWORDS: dict[str, int] = {
    # Strong bearish (weight 3)
    "scam": 3, "rug": 3, "fraud": 3, "ponzi": 3, "worthless": 3,
    "hack": 3, "exploit": 3, "insolvent": 3, "bankrupt": 3,
    # Moderate bearish (weight 2)
    "dump": 2, "bearish": 2, "crash": 2, "collapse": 2,
    "liquidation": 2, "capitulation": 2, "bagholding": 2,
    "bubble": 2, "warning": 2, "overvalued": 2, "rugpull": 2,
    "dumping": 2,
    # Mild bearish (weight 1)
    "sell": 1, "short": 1, "dead": 1, "rekt": 1, "exit": 1,
    "resistance": 1, "top": 1, "overbought": 1, "red": 1,
    "loss": 1, "falling": 1, "decline": 1, "weak": 1,
    "fear": 1, "risk": 1, "delay": 1, "concern": 1,
}

# Negation words that flip the sentiment of the next keyword
NEGATION_WORDS: set[str] = {
    "not", "no", "never", "dont", "doesn't", "isn't", "wasn't",
    "won't", "can't", "couldn't", "shouldn't", "wouldn't", "neither",
    "hardly", "barely", "without",
}


# ── Data Classes ────────────────────────────────────────────────────


@dataclass
class PostScore:
    """Sentiment score for a single post."""

    text: str
    score: float  # -1.0 to +1.0
    label: str  # "bullish", "bearish", "neutral"
    bullish_words: list[str]
    bearish_words: list[str]
    confidence: float  # 0.0 to 1.0 based on keyword density


@dataclass
class AggregateResult:
    """Aggregated sentiment across multiple posts."""

    total_posts: int
    bullish_count: int
    bearish_count: int
    neutral_count: int
    average_score: float
    median_score: float
    score_std: float
    top_bullish_words: list[tuple[str, int]]
    top_bearish_words: list[tuple[str, int]]
    sentiment_distribution: dict[str, float]


# ── Scoring Functions ───────────────────────────────────────────────


def tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase words, removing punctuation.

    Args:
        text: Raw input text.

    Returns:
        List of lowercase word tokens.
    """
    cleaned = re.sub(r"[^\w\s$#@]", " ", text.lower())
    # Handle cashtags: $SOL -> sol
    cleaned = cleaned.replace("$", "")
    return cleaned.split()


def score_text(
    text: str,
    bullish: Optional[dict[str, int]] = None,
    bearish: Optional[dict[str, int]] = None,
    use_negation: bool = True,
) -> PostScore:
    """Score a text string for crypto sentiment.

    Uses keyword matching with optional negation detection.
    Negation flips the sentiment of the next keyword found.

    Args:
        text: The text to analyze.
        bullish: Bullish keyword dict (word -> weight). Defaults to built-in.
        bearish: Bearish keyword dict (word -> weight). Defaults to built-in.
        use_negation: Whether to apply negation detection.

    Returns:
        PostScore with score, label, matched words, and confidence.
    """
    bull_dict = bullish or BULLISH_KEYWORDS
    bear_dict = bearish or BEARISH_KEYWORDS

    words = tokenize(text)
    bull_score = 0
    bear_score = 0
    bull_words: list[str] = []
    bear_words: list[str] = []

    negated = False
    for word in words:
        if use_negation and word in NEGATION_WORDS:
            negated = True
            continue

        is_bull = word in bull_dict
        is_bear = word in bear_dict

        if is_bull:
            weight = bull_dict[word]
            if negated:
                bear_score += weight
                bear_words.append(f"~{word}")  # ~ prefix = negated
            else:
                bull_score += weight
                bull_words.append(word)
            negated = False
        elif is_bear:
            weight = bear_dict[word]
            if negated:
                bull_score += weight
                bull_words.append(f"~{word}")
            else:
                bear_score += weight
                bear_words.append(word)
            negated = False
        else:
            # Non-keyword resets negation after 1 intervening word
            # (e.g., "not very bullish" should still negate)
            pass

    total_weight = bull_score + bear_score
    if total_weight == 0:
        score = 0.0
        label = "neutral"
        confidence = 0.0
    else:
        score = (bull_score - bear_score) / total_weight
        keyword_density = len(bull_words + bear_words) / max(len(words), 1)
        confidence = min(1.0, keyword_density * 5)  # 20% density = full confidence

        if score > 0.1:
            label = "bullish"
        elif score < -0.1:
            label = "bearish"
        else:
            label = "neutral"

    return PostScore(
        text=text,
        score=round(score, 3),
        label=label,
        bullish_words=bull_words,
        bearish_words=bear_words,
        confidence=round(confidence, 3),
    )


def aggregate_scores(posts: list[PostScore]) -> AggregateResult:
    """Aggregate sentiment scores across multiple posts.

    Args:
        posts: List of PostScore objects.

    Returns:
        AggregateResult with counts, averages, and word frequencies.
    """
    if not posts:
        return AggregateResult(
            total_posts=0, bullish_count=0, bearish_count=0, neutral_count=0,
            average_score=0.0, median_score=0.0, score_std=0.0,
            top_bullish_words=[], top_bearish_words=[],
            sentiment_distribution={},
        )

    scores = [p.score for p in posts]
    bullish_count = sum(1 for p in posts if p.label == "bullish")
    bearish_count = sum(1 for p in posts if p.label == "bearish")
    neutral_count = sum(1 for p in posts if p.label == "neutral")

    avg = sum(scores) / len(scores)
    sorted_scores = sorted(scores)
    n = len(sorted_scores)
    median = (
        sorted_scores[n // 2]
        if n % 2 == 1
        else (sorted_scores[n // 2 - 1] + sorted_scores[n // 2]) / 2.0
    )
    variance = sum((s - avg) ** 2 for s in scores) / len(scores)
    std = math.sqrt(variance)

    # Word frequency
    all_bull: Counter[str] = Counter()
    all_bear: Counter[str] = Counter()
    for p in posts:
        for w in p.bullish_words:
            all_bull[w.lstrip("~")] += 1
        for w in p.bearish_words:
            all_bear[w.lstrip("~")] += 1

    total = len(posts)
    distribution = {
        "bullish": round(bullish_count / total * 100, 1),
        "neutral": round(neutral_count / total * 100, 1),
        "bearish": round(bearish_count / total * 100, 1),
    }

    return AggregateResult(
        total_posts=total,
        bullish_count=bullish_count,
        bearish_count=bearish_count,
        neutral_count=neutral_count,
        average_score=round(avg, 3),
        median_score=round(median, 3),
        score_std=round(std, 3),
        top_bullish_words=all_bull.most_common(10),
        top_bearish_words=all_bear.most_common(10),
        sentiment_distribution=distribution,
    )


# ── Display ─────────────────────────────────────────────────────────


def display_post_score(post: PostScore, index: int) -> None:
    """Display a single post's sentiment analysis.

    Args:
        post: The scored post.
        index: Post number for display.
    """
    indicator = {
        "bullish": "[+]",
        "bearish": "[-]",
        "neutral": "[=]",
    }.get(post.label, "[?]")

    # Truncate text for display
    display_text = post.text if len(post.text) <= 80 else post.text[:77] + "..."

    print(f"\n  {indicator} Post {index}: {display_text}")
    print(f"      Score: {post.score:>+.3f}  |  Label: {post.label}  |  Confidence: {post.confidence:.1%}")
    if post.bullish_words:
        print(f"      Bullish words: {', '.join(post.bullish_words)}")
    if post.bearish_words:
        print(f"      Bearish words: {', '.join(post.bearish_words)}")


def display_aggregate(agg: AggregateResult) -> None:
    """Display aggregated sentiment results.

    Args:
        agg: AggregateResult to display.
    """
    print("\n" + "=" * 60)
    print("  AGGREGATE SENTIMENT ANALYSIS")
    print("=" * 60)

    print(f"\n  Total Posts Analyzed: {agg.total_posts}")
    print(f"\n  --- Distribution ---")

    # Visual bar chart
    bar_width = 40
    for label in ["bullish", "neutral", "bearish"]:
        pct = agg.sentiment_distribution.get(label, 0)
        bar_len = int(pct / 100 * bar_width)
        bar = "#" * bar_len + "." * (bar_width - bar_len)
        count = {"bullish": agg.bullish_count, "neutral": agg.neutral_count,
                 "bearish": agg.bearish_count}[label]
        print(f"  {label:>8}: [{bar}] {pct:5.1f}% ({count})")

    print(f"\n  --- Score Statistics ---")
    print(f"  Average Score:  {agg.average_score:>+.3f}")
    print(f"  Median Score:   {agg.median_score:>+.3f}")
    print(f"  Std Deviation:  {agg.score_std:>.3f}")

    # Overall label
    if agg.average_score > 0.1:
        overall = "BULLISH"
    elif agg.average_score < -0.1:
        overall = "BEARISH"
    else:
        overall = "NEUTRAL"
    print(f"  Overall:        {overall}")

    print(f"\n  --- Top Bullish Words ---")
    if agg.top_bullish_words:
        for word, count in agg.top_bullish_words[:7]:
            print(f"    {word:<20} x{count}")
    else:
        print("    (none)")

    print(f"\n  --- Top Bearish Words ---")
    if agg.top_bearish_words:
        for word, count in agg.top_bearish_words[:7]:
            print(f"    {word:<20} x{count}")
    else:
        print("    (none)")

    print("\n" + "=" * 60)
    print("  NOTE: This is analytical information only, not financial advice.")
    print("=" * 60 + "\n")


# ── Demo Mode ───────────────────────────────────────────────────────

DEMO_POSTS: list[str] = [
    # Bullish posts
    "SOL is going parabolic! This breakout is massive, accumulate before the moon!",
    "$SOL partnership with Visa is bullish af, institutional adoption incoming",
    "Just bought the dip on Solana. This gem is so undervalued right now. Diamond hands hodl!",
    "SOL rally looking strong, support held perfectly. Green candles everywhere",
    "Solana TPS hitting new ATH, this is bullish for the ecosystem growth",
    "Massive gains on my SOL long position, this pump is just getting started",
    "New DeFi launch on Solana looks promising, real opportunity here",
    # Bearish posts
    "Another Solana outage? This chain is dead, total scam. Selling everything.",
    "$SOL is dumping hard, this crash could get worse. Overvalued garbage",
    "Warning: SOL looks like a classic bubble, bearish divergence on the 4h chart",
    "Rugpull on another Solana memecoin, this ecosystem is full of fraud and exploits",
    "Liquidation cascade incoming for SOL longs. Overbought and at resistance.",
    "SOL is weak, declining volume, capitulation hasnt even started yet",
    # Neutral / mixed posts
    "Solana TVL is at 4.2B, interesting to see how it compares to Ethereum",
    "Just deployed my first smart contract on Solana. The developer experience is smooth.",
    "SOL trading at $150, volume is average. Waiting for a clear direction.",
    "Not bullish on SOL short term but long term the technology is solid",
    "Comparing Solana vs Avalanche transaction costs for my research paper",
    "The new Solana phone looks cool but not sure how it affects the token price",
    "Attending Solana Breakpoint conference next week, should be informative",
]


def run_demo() -> None:
    """Run demo mode with 20 synthetic crypto social media posts."""
    print("\n" + "=" * 60)
    print("  KEYWORD SENTIMENT ANALYZER — DEMO MODE")
    print("  Analyzing 20 synthetic crypto social media posts")
    print("=" * 60)

    scored_posts: list[PostScore] = []
    for i, text in enumerate(DEMO_POSTS, 1):
        post_score = score_text(text)
        scored_posts.append(post_score)
        display_post_score(post_score, i)

    agg = aggregate_scores(scored_posts)
    display_aggregate(agg)


# ── Single Text Mode ───────────────────────────────────────────────


def analyze_single(text: str) -> None:
    """Analyze a single text input.

    Args:
        text: The text to analyze.
    """
    print("\n" + "=" * 60)
    print("  KEYWORD SENTIMENT ANALYZER — SINGLE TEXT")
    print("=" * 60)

    result = score_text(text)
    display_post_score(result, 1)

    print("\n" + "=" * 60)
    print("  NOTE: This is analytical information only, not financial advice.")
    print("=" * 60 + "\n")


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Entry point: parse arguments and run analyzer."""
    parser = argparse.ArgumentParser(
        description="Keyword-based crypto sentiment analyzer"
    )
    parser.add_argument(
        "--text",
        type=str,
        default=None,
        help="Single text to analyze",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run demo mode with 20 synthetic posts (default if no --text)",
    )
    args = parser.parse_args()

    if args.text:
        analyze_single(args.text)
    else:
        run_demo()


if __name__ == "__main__":
    main()

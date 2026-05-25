"""Unit tests for the ticker-mention extractor used by stock sentiment.

We don't hit the network here. The interesting bit is the matcher: it has to
catch real S&P 500 mentions while resisting common false positives.
"""

from __future__ import annotations

from app.data.stock_sentiment import (
    _company_aliases,
    build_matchers,
    match_tickers_in_text,
)


def test_company_aliases_strips_corporate_suffixes() -> None:
    assert _company_aliases("Apple Inc.") == ["Apple"]
    assert _company_aliases("Microsoft Corporation") == ["Microsoft"]
    # Two-word company picks up the head word too.
    assert "Verizon" in _company_aliases("Verizon Communications Inc")
    # Single-word fully-qualified name still survives.
    assert _company_aliases("Tesla, Inc.") == ["Tesla"]


def test_company_aliases_drops_blacklisted_short_names() -> None:
    # "Target Corp" -> "Target" is in the blacklist (too generic).
    assert _company_aliases("Target Corp") == []
    # Three-letter cores are also dropped (would over-match).
    assert _company_aliases("Co Co") == []


def test_matcher_finds_uppercase_ticker_with_word_boundary() -> None:
    matchers = build_matchers({"AAPL": "Apple Inc.", "MSFT": "Microsoft Corp"})
    assert match_tickers_in_text("Shares of AAPL rallied today.", matchers) == ["AAPL"]
    assert match_tickers_in_text("$AAPL hit a 52-week high.", matchers) == ["AAPL"]


def test_matcher_does_not_fire_on_lowercase_ticker_lookalike() -> None:
    """``\\bAAPL\\b`` is case-sensitive — a sentence about apples shouldn't
    score as an Apple mention."""
    matchers = build_matchers({"AAPL": "Apple Inc.", "MSFT": "Microsoft Corp"})
    text = "We aapl that fruit on every shelf."  # lower-case 'aapl'
    # The company name 'Apple' isn't in the text either.
    assert match_tickers_in_text(text, matchers) == []


def test_matcher_finds_company_name_case_insensitive() -> None:
    matchers = build_matchers({"AAPL": "Apple Inc.", "MSFT": "Microsoft Corp"})
    assert match_tickers_in_text("apple unveiled a new chip.", matchers) == ["AAPL"]
    assert "MSFT" in match_tickers_in_text("Microsoft beat earnings.", matchers)


def test_matcher_attributes_to_multiple_tickers_in_one_headline() -> None:
    matchers = build_matchers({"AAPL": "Apple Inc.", "MSFT": "Microsoft Corp"})
    hits = match_tickers_in_text(
        "Apple and Microsoft both announced AI chips today.", matchers
    )
    assert set(hits) == {"AAPL", "MSFT"}


def test_matcher_returns_empty_for_unrelated_text() -> None:
    matchers = build_matchers({"AAPL": "Apple Inc.", "MSFT": "Microsoft Corp"})
    assert match_tickers_in_text("Crude oil prices rallied on OPEC supply cuts.", matchers) == []


def test_matcher_handles_non_ascii_punctuation() -> None:
    matchers = build_matchers({"AAPL": "Apple Inc."})
    assert match_tickers_in_text("Apple\u2014the Cupertino giant\u2014beat earnings.", matchers) == ["AAPL"]

from __future__ import annotations

import json

from fx_monitor.ai.visual_review_schema import (
    VISUAL_REVIEW_OUTPUT_SCHEMA,
    VisualReview,
    parse_visual_review,
    visual_review_schema_as_dict,
)


def test_visual_review_schema_unknown_safe():
    review = VisualReview(
        provider="openai",
        verdict="UNKNOWN",
        readability="UNKNOWN",
        language="UNKNOWN",
        royal_road_clarity="UNKNOWN",
        line_visibility="UNKNOWN",
        safety_clarity="UNKNOWN",
    )
    assert review.verdict == "UNKNOWN"
    assert review.used_for_ready is False
    assert review.used_for_notification is False
    assert review.used_for_trading is False


def test_visual_review_schema_top_level_required():
    required = set(VISUAL_REVIEW_OUTPUT_SCHEMA["required"])
    assert {
        "schema_version",
        "verdict",
        "readability",
        "language",
        "royal_road_clarity",
        "line_visibility",
        "safety_clarity",
        "problems",
        "required_fixes",
        "summary_ja",
    } <= required


def test_parse_visual_review_valid_pass():
    payload = {
        "schema_version": "visual_review_v1",
        "verdict": "PASS",
        "readability": "GOOD",
        "language": "JA",
        "royal_road_clarity": "GOOD",
        "line_visibility": "GOOD",
        "safety_clarity": "GOOD",
        "problems": [],
        "required_fixes": [],
        "summary_ja": "見やすい画面",
    }
    review = parse_visual_review("openai", payload)
    assert review.verdict == "PASS"
    assert review.language == "JA"
    assert review.used_for_ready is False


def test_parse_visual_review_bad_json_returns_unknown():
    review = parse_visual_review("claude", "not json")
    assert review.verdict == "UNKNOWN"
    assert any("invalid JSON" in p for p in review.problems)


def test_parse_visual_review_schema_violation_returns_unknown():
    bad = {
        "schema_version": "visual_review_v1",
        "verdict": "PASS",
        "readability": "WEIRD",
        "language": "JA",
        "royal_road_clarity": "GOOD",
        "line_visibility": "GOOD",
        "safety_clarity": "GOOD",
        "problems": [],
        "required_fixes": [],
        "summary_ja": "x",
    }
    review = parse_visual_review("openai", bad)
    assert review.verdict == "UNKNOWN"


def test_visual_review_schema_dict_is_independent_copy():
    a = visual_review_schema_as_dict()
    b = visual_review_schema_as_dict()
    a["title"] = "MUTATED"
    assert b["title"] != "MUTATED"
    assert json.dumps(b)  # round-trips

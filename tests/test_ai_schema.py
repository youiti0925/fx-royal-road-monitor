from __future__ import annotations

from copy import deepcopy

from fx_monitor.ai.mock_reviewer import (
    mock_ready_review,
    mock_unknown_review,
    mock_wait_retest_review,
)
from fx_monitor.ai.schema import (
    P0_STEP_KEYS,
    REQUIRED_STEP_KEYS,
    REVIEW_OUTPUT_SCHEMA,
    parse_review,
)


def make_valid_review_payload(verdict: str = "PASS", bias: str = "long") -> dict:
    if verdict == "PASS":
        return deepcopy(mock_ready_review(bias=bias))
    if verdict == "WAIT":
        return deepcopy(mock_wait_retest_review(bias=bias))
    return deepcopy(mock_unknown_review())


def test_schema_has_required_top_level_fields():
    required = set(REVIEW_OUTPUT_SCHEMA["required"])
    assert {
        "verdict",
        "bias",
        "confidence",
        "reasons",
        "steps",
        "line_review",
        "wave_review",
        "entry_review",
        "risk_review",
        "disagreement_with_system",
    } <= required


def test_schema_step_enum_matches_required_keys():
    item_schema = REVIEW_OUTPUT_SCHEMA["properties"]["steps"]["items"]
    assert set(item_schema["properties"]["key"]["enum"]) == set(REQUIRED_STEP_KEYS)


def test_p0_step_keys_subset_of_required():
    assert set(P0_STEP_KEYS) <= set(REQUIRED_STEP_KEYS)


def test_parse_valid_ready_review_passes():
    review = parse_review("openai", make_valid_review_payload("PASS", "long"))
    assert review.verdict == "PASS"
    assert review.bias == "long"
    assert {s.key for s in review.steps} == set(REQUIRED_STEP_KEYS)
    assert all(s.status == "PASS" for s in review.steps if s.key in P0_STEP_KEYS)


def test_parse_valid_wait_review_passes():
    review = parse_review("claude", make_valid_review_payload("WAIT", "long"))
    assert review.verdict == "WAIT"
    assert review.entry_review is not None


def test_parse_bad_json_returns_unknown():
    r = parse_review("claude", "not json at all")
    assert r.verdict == "UNKNOWN"
    assert r.bias == "none"
    assert any("invalid JSON" in s for s in r.reasons)


def test_parse_schema_violation_returns_unknown():
    payload = make_valid_review_payload("PASS")
    payload["bias"] = "sideways"  # not in enum
    r = parse_review("openai", payload)
    assert r.verdict == "UNKNOWN"


def test_parse_confidence_out_of_range_returns_unknown():
    payload = make_valid_review_payload("PASS")
    payload["confidence"] = 1.5
    r = parse_review("openai", payload)
    assert r.verdict == "UNKNOWN"


def test_parse_review_requires_all_steps_for_pass():
    payload = make_valid_review_payload("PASS")
    payload["steps"] = []
    review = parse_review("openai", payload)
    assert review.verdict == "UNKNOWN"
    assert any("steps" in r for r in review.reasons)


def test_parse_review_pass_missing_some_required_step_keys_becomes_unknown():
    payload = make_valid_review_payload("PASS")
    payload["steps"] = [s for s in payload["steps"] if s["key"] != "rr"]
    review = parse_review("openai", payload)
    assert review.verdict == "UNKNOWN"


def test_pass_with_missing_confirmation_becomes_unknown():
    payload = make_valid_review_payload("PASS")
    for step in payload["steps"]:
        if step["key"] == "confirmation_candle":
            step["status"] = "WAIT"
    review = parse_review("openai", payload)
    assert review.verdict == "UNKNOWN"


def test_pass_with_event_block_becomes_unknown():
    payload = make_valid_review_payload("PASS")
    for step in payload["steps"]:
        if step["key"] == "event":
            step["status"] = "BLOCK"
    review = parse_review("claude", payload)
    assert review.verdict == "UNKNOWN"


def test_pass_with_rr_warn_becomes_unknown():
    payload = make_valid_review_payload("PASS")
    for step in payload["steps"]:
        if step["key"] == "rr":
            step["status"] = "WARN"
    review = parse_review("claude", payload)
    assert review.verdict == "UNKNOWN"


def test_pass_with_any_p0_not_pass_becomes_unknown():
    for k in P0_STEP_KEYS:
        payload = make_valid_review_payload("PASS")
        for step in payload["steps"]:
            if step["key"] == k:
                step["status"] = "WARN"
        r = parse_review("openai", payload)
        assert r.verdict == "UNKNOWN", f"P0 step {k}=WARN should force UNKNOWN"

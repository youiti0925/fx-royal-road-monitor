from __future__ import annotations

from fx_monitor.ai.schema import REVIEW_OUTPUT_SCHEMA, parse_review


def test_schema_has_required_fields():
    required = set(REVIEW_OUTPUT_SCHEMA["required"])
    assert {"verdict", "bias", "confidence", "reasons"} <= required


def test_parse_valid_response():
    raw = (
        '{"verdict":"PASS","bias":"long","confidence":0.7,'
        '"reasons":["aligned"],"disagreements":[],"missing":[]}'
    )
    r = parse_review("openai", raw)
    assert r.verdict == "PASS"
    assert r.bias == "long"
    assert 0.0 <= r.confidence <= 1.0
    assert r.provider == "openai"


def test_parse_bad_json_returns_unknown():
    r = parse_review("claude", "not json at all")
    assert r.verdict == "UNKNOWN"
    assert r.bias == "none"
    assert any("Invalid JSON" in s for s in r.reasons)


def test_parse_schema_violation_returns_unknown():
    # bias="sideways" is not allowed by the schema / model.
    bad = '{"verdict":"PASS","bias":"sideways","confidence":0.5,"reasons":[]}'
    r = parse_review("openai", bad)
    assert r.verdict == "UNKNOWN"


def test_parse_confidence_out_of_range_returns_unknown():
    bad = '{"verdict":"PASS","bias":"long","confidence":1.5,"reasons":[]}'
    r = parse_review("openai", bad)
    assert r.verdict == "UNKNOWN"

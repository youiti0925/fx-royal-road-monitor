from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from fx_monitor.analysis.rich_draft_compare import (
    SCHEMA_VERSION,
    compare_rich_draft_to_reference,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _draft() -> dict:
    return _load("sample_rich_draft.json")


def _ref() -> dict:
    return _load("sample_reference_payload.json")


def test_compare_safety_flags_are_pinned():
    result = compare_rich_draft_to_reference(draft=_draft(), reference=_ref())
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["offline_analysis_only"] is True
    assert result["used_for_ready"] is False
    assert result["used_for_notification"] is False


def test_compare_pattern_match_treats_possible_x_as_x():
    result = compare_rich_draft_to_reference(draft=_draft(), reference=_ref())
    # draft pattern_kind = "possible_double_top",
    # reference pattern_kind = "double_top" -> treated as match.
    assert result["scores"]["pattern_match"] == 1.0


def test_compare_wave_line_presence_full_when_both_have_all_three_roles():
    result = compare_rich_draft_to_reference(draft=_draft(), reference=_ref())
    assert result["scores"]["wave_line_presence"] == 1.0
    assert result["counts"]["draft_wave_lines"] == 3
    assert result["counts"]["ref_wave_lines"] == 3
    # Price gaps are tiny but > 0 (draft 1.1000 vs ref 1.1001).
    assert "entry_confirmation_line" in result["wave_price_gaps"]


def test_compare_structural_line_presence_and_anchor_matches():
    result = compare_rich_draft_to_reference(draft=_draft(), reference=_ref())
    assert result["scores"]["structural_line_presence"] == 1.0
    # All four anchor_parts sets line up between fixtures.
    assert result["counts"]["structural_anchor_matches"] == 4


def test_compare_sr_presence_capped_to_one():
    result = compare_rich_draft_to_reference(draft=_draft(), reference=_ref())
    # 1 draft zone vs 2 reference zones -> 0.5
    assert result["scores"]["sr_presence"] == 0.5


def test_compare_trendline_presence():
    result = compare_rich_draft_to_reference(draft=_draft(), reference=_ref())
    # 1 draft trendline vs 1 ref trendline -> 1.0
    assert result["scores"]["trendline_presence"] == 1.0


def test_compare_missing_when_draft_lacks_a_wave_role():
    draft = _draft()
    draft["wave_derived_lines_draft"] = [
        line
        for line in draft["wave_derived_lines_draft"]
        if line["role"] != "stop_candidate"
    ]
    result = compare_rich_draft_to_reference(draft=draft, reference=_ref())
    assert result["scores"]["wave_line_presence"] < 1.0
    assert any(m == "wave_line:stop_candidate" for m in result["missing"])


def test_compare_pattern_mismatch_recorded():
    draft = _draft()
    draft["pattern_levels_draft"]["pattern_kind"] = "possible_double_bottom"
    result = compare_rich_draft_to_reference(draft=draft, reference=_ref())
    assert result["scores"]["pattern_match"] == 0.0
    assert any(m.startswith("pattern_kind:") for m in result["mismatches"])


def test_compare_does_not_emit_ready_or_notification_signal():
    """The compare result must never contain anything that could be
    mistaken for a READY decision or a notification dispatch.

    We can't simply ban the substring "READY" because the safety flag
    name ``used_for_ready`` legitimately contains it. Instead we ban
    the specific JSON fragments that *would* indicate an actionable
    READY / dispatch / notification.
    """
    result = compare_rich_draft_to_reference(draft=_draft(), reference=_ref())

    assert result["offline_analysis_only"] is True
    assert result["used_for_ready"] is False
    assert result["used_for_notification"] is False

    serialized = json.dumps(result).upper()

    forbidden_fragments = [
        '"VERDICT": "READY"',
        '"DECISION": "READY"',
        '"LEVEL": "READY"',
        '"SHOULD_DISPATCH": TRUE',
        '"DISPATCH": TRUE',
        '"NOTIFY": TRUE',
        '"NOTIFICATION": TRUE',
        '"USED_FOR_READY": TRUE',
        '"USED_FOR_NOTIFICATION": TRUE',
    ]

    for fragment in forbidden_fragments:
        assert fragment not in serialized, (
            f"compare report must not contain {fragment!r}"
        )


def test_compare_rejects_non_dict_input():
    with pytest.raises(TypeError):
        compare_rich_draft_to_reference(draft=[1, 2, 3], reference={})  # type: ignore[arg-type]


def test_compare_handles_empty_inputs_without_crash():
    result = compare_rich_draft_to_reference(draft={}, reference={})
    assert result["scores"]["pattern_match"] == 0.0
    assert result["scores"]["wave_line_presence"] == 0.0
    assert result["scores"]["structural_line_presence"] == 0.0
    assert "draft_pattern_levels_missing" in result["warnings"]
    assert "reference_pattern_levels_missing" in result["warnings"]


def test_compare_cli_writes_json_and_prints_summary(tmp_path):
    out = tmp_path / "rich_draft_compare.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fx_monitor.app.rich_draft_compare",
            "--draft",
            str(FIXTURES / "sample_rich_draft.json"),
            "--reference",
            str(FIXTURES / "sample_reference_payload.json"),
            "--out",
            str(out),
        ],
        text=True,
        capture_output=True,
        check=True,
    )

    assert "Rich draft compare:" in result.stdout
    assert "pattern=1.00" in result.stdout
    assert "Compare report:" in result.stdout
    assert "offline_analysis_only=True" in result.stdout
    assert "used_for_ready=False" in result.stdout

    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["used_for_ready"] is False
    assert data["used_for_notification"] is False

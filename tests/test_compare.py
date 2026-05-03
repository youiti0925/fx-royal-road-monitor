from __future__ import annotations

from fx_monitor.core.compare import compare
from fx_monitor.core.models import DisagreementWithSystem, ReviewResult


def _r(
    provider: str,
    verdict: str,
    bias: str = "none",
    conf: float = 0.5,
    disagreements: list[str] | None = None,
    has_dis: bool = False,
) -> ReviewResult:
    return ReviewResult(
        provider=provider,
        verdict=verdict,
        bias=bias,
        confidence=conf,
        disagreements=disagreements or [],
        disagreement_with_system=DisagreementWithSystem(
            has_disagreement=has_dis,
            severity="HIGH" if has_dis else "NONE",
            reason_ja="" if not has_dis else "system says READY but chart weak",
        ),
    )


def test_agree_pass_when_both_pass_same_bias():
    out = compare(_r("openai", "PASS", "long"), _r("claude", "PASS", "long"))
    assert out.result == "AGREE_PASS"
    assert out.bias == "long"


def test_disagree_when_pass_pass_but_bias_differs():
    out = compare(_r("openai", "PASS", "long"), _r("claude", "PASS", "short"))
    assert out.result == "DISAGREE"


def test_agree_pass_blocked_when_bias_none():
    out = compare(_r("openai", "PASS", "none"), _r("claude", "PASS", "none"))
    assert out.result == "DISAGREE"


def test_agree_hold_when_both_wait():
    out = compare(_r("openai", "WAIT"), _r("claude", "WAIT"))
    assert out.result == "AGREE_HOLD"


def test_disagree_when_verdicts_differ():
    out = compare(_r("openai", "PASS", "long"), _r("claude", "WARN", "long"))
    assert out.result == "DISAGREE"


def test_insufficient_when_one_unknown():
    out = compare(_r("openai", "UNKNOWN"), _r("claude", "PASS", "long"))
    assert out.result == "INSUFFICIENT"


def test_insufficient_when_one_missing():
    out = compare(None, _r("claude", "PASS", "long"))
    assert out.result == "INSUFFICIENT"


def test_disagreements_field_blocks_agree_pass():
    o = _r("openai", "PASS", "long", disagreements=["chart evidence weak"])
    c = _r("claude", "PASS", "long")
    out = compare(o, c)
    assert out.result == "DISAGREE"


def test_disagreement_with_system_block_blocks_agree_pass():
    o = _r("openai", "PASS", "long")
    c = _r("claude", "PASS", "long", has_dis=True)
    out = compare(o, c)
    assert out.result == "DISAGREE"
    assert any("disagreement_with_system" in n for n in out.notes)

from __future__ import annotations

import json

from fx_monitor.logging import append_review_log


def test_append_review_log_writes_jsonl(tmp_path):
    path = tmp_path / "logs" / "review.jsonl"
    append_review_log(
        path=path,
        record={
            "mode": "draft_ai_review",
            "symbol": "EURUSD=X",
            "decision": "SUPPRESSED",
        },
    )

    assert path.exists()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["mode"] == "draft_ai_review"
    assert data["symbol"] == "EURUSD=X"
    assert data["decision"] == "SUPPRESSED"
    assert "logged_at_utc" in data


def test_append_review_log_appends_multiple_lines(tmp_path):
    path = tmp_path / "review.jsonl"
    append_review_log(path=path, record={"i": 1})
    append_review_log(path=path, record={"i": 2})
    append_review_log(path=path, record={"i": 3})

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert [json.loads(line)["i"] for line in lines] == [1, 2, 3]


def test_append_review_log_creates_parent_dirs(tmp_path):
    path = tmp_path / "deep" / "nested" / "logs" / "r.jsonl"
    append_review_log(path=path, record={"mode": "draft_ai_review"})
    assert path.exists()

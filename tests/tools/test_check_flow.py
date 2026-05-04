from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from fx_monitor.tools.check_finalise import finalise_check
from fx_monitor.tools.check_prepare import prepare_check
from fx_monitor.live.candle import Candle


@pytest.fixture(autouse=True)
def _isolate_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FX_MONITOR_ROOT", str(tmp_path))


def _candles(n: int = 70) -> list[Candle]:
    return [
        Candle(
            t=datetime(2026, 5, 4, 10, 0, tzinfo=timezone.utc) + timedelta(minutes=5 * i),
            o=1.10 + 0.0005 * i,
            h=1.105 + 0.0005 * i,
            l=1.095 + 0.0005 * i,
            c=1.10 + 0.0005 * i,
            v=100.0,
        )
        for i in range(n)
    ]


def test_prepare_creates_pending_and_prompt_files():
    info = prepare_check(symbol="EURUSD=X", timeframe="M5", candles=_candles())
    pending = Path(info["pending_path"])
    prompt = Path(info["prompt_path"])
    assert pending.exists()
    assert prompt.exists()
    assert info["entry_id"]
    assert info["retrieved_count"] == 0  # cold-start corpus

    payload = json.loads(pending.read_text(encoding="utf-8"))
    assert payload["entry_id"] == info["entry_id"]
    assert payload["symbol"] == "EURUSD=X"
    assert "market_pack" in payload


def test_prepare_rejects_short_history():
    with pytest.raises(ValueError):
        prepare_check(symbol="EURUSD=X", timeframe="M5", candles=_candles(10))


def test_finalise_stores_corpus_entry_and_removes_pending():
    info = prepare_check(symbol="EURUSD=X", timeframe="M5", candles=_candles())
    spec_json = json.dumps(
        {
            "schema_version": "ai_decision_screen_spec_v1",
            "provider": "claude",
            "observation_only": True,
            "used_for_ready": False,
            "used_for_notification": False,
            "used_for_trading": False,
            "symbol": "EURUSD=X",
            "timeframe": "M5",
            "side": "SELL",
            "final_status": "WAIT_BREAKOUT",
            "summary_ja": "test",
            "lines": [],
            "points": [],
            "zones": [],
            "procedure_steps": [],
        }
    )
    result = finalise_check(entry_id=info["entry_id"], spec_json=spec_json)
    assert result["final_status"] == "WAIT_BREAKOUT"
    assert result["validation_ok"] is True
    assert result["corpus_size"] == 1
    assert not Path(info["pending_path"]).exists()


def test_finalise_downgrades_when_validation_fails():
    info = prepare_check(symbol="EURUSD=X", timeframe="M5", candles=_candles())
    # Spec with a wildly out-of-range line price -> Layer 3 error.
    spec_json = json.dumps(
        {
            "schema_version": "ai_decision_screen_spec_v1",
            "provider": "claude",
            "observation_only": True,
            "used_for_ready": False,
            "used_for_notification": False,
            "used_for_trading": False,
            "symbol": "EURUSD=X",
            "timeframe": "M5",
            "side": "SELL",
            "final_status": "WAIT_BREAKOUT",
            "summary_ja": "test",
            "lines": [
                {
                    "id": "L1",
                    "label": "WNL",
                    "kind": "neckline",
                    "role": "entry_trigger",
                    "price": 99.0,  # nowhere near reality
                }
            ],
            "points": [],
            "zones": [],
            "procedure_steps": [],
        }
    )
    result = finalise_check(entry_id=info["entry_id"], spec_json=spec_json)
    assert result["downgraded"] is True
    assert result["final_status"] == "UNKNOWN"
    assert any(
        i["code"] == "line_out_of_range" for i in result["validation_issues"]
    )


def test_finalise_raises_on_unknown_entry_id():
    with pytest.raises(FileNotFoundError):
        finalise_check(entry_id="does-not-exist", spec_json="{}")

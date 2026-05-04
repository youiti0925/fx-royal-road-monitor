from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from fx_monitor.offline.progress_state import ProgressState


def _start_end():
    return (
        datetime(2026, 2, 1, tzinfo=timezone.utc),
        datetime(2026, 5, 1, tzinfo=timezone.utc),
    )


def test_init_when_file_missing(tmp_path: Path):
    start, end = _start_end()
    p = tmp_path / "progress.json"
    state = ProgressState.load_or_init(
        p, symbol="EURUSD=X", timeframe="M5", start_utc=start, end_utc=end
    )
    assert state.processed_indices == []
    assert state.errors == []


def test_save_and_reload(tmp_path: Path):
    start, end = _start_end()
    p = tmp_path / "progress.json"
    s1 = ProgressState.load_or_init(
        p, symbol="EURUSD=X", timeframe="M5", start_utc=start, end_utc=end
    )
    s1.mark_done(10)
    s1.mark_done(11)
    s1.mark_error(12, "boom")
    s1.session_finalise(2)
    s1.save(p)

    s2 = ProgressState.load_or_init(
        p, symbol="EURUSD=X", timeframe="M5", start_utc=start, end_utc=end
    )
    assert s2.processed_indices == [10, 11]
    assert len(s2.errors) == 1
    assert s2.errors[0].index == 12
    assert s2.last_session_processed_count == 2


def test_mismatch_in_job_params_raises(tmp_path: Path):
    start, end = _start_end()
    p = tmp_path / "progress.json"
    s1 = ProgressState.load_or_init(
        p, symbol="EURUSD=X", timeframe="M5", start_utc=start, end_utc=end
    )
    s1.save(p)
    with pytest.raises(ValueError):
        ProgressState.load_or_init(
            p,
            symbol="GBPUSD=X",  # different symbol
            timeframe="M5",
            start_utc=start,
            end_utc=end,
        )


def test_mark_done_is_idempotent(tmp_path: Path):
    start, end = _start_end()
    p = tmp_path / "progress.json"
    s = ProgressState.load_or_init(
        p, symbol="EURUSD=X", timeframe="M5", start_utc=start, end_utc=end
    )
    s.mark_done(5)
    s.mark_done(5)
    assert s.processed_indices == [5]
    assert s.is_done(5)

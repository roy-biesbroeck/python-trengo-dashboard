"""Regression tests for the history-wipe bug.

Root cause: `_save_snapshot` used a non-atomic `open(path, 'w')` (truncate) with
no locking. Two concurrent /api/dashboard requests could truncate the file while
another thread read it, whose `_load_history` then silently returned [] and
clobbered all history. See conversation 2026-08-04.
"""
import json
import os
import threading

import pytest

import app as app_module


@pytest.fixture
def hist_file(tmp_path, monkeypatch):
    f = tmp_path / "history.json"
    monkeypatch.setattr(app_module, "HISTORY_FILE", str(f))
    return f


def _seed(hist_file, n, total=100):
    entries = [{"ts": f"2026-08-04T00:{i:02d}:00", "open": total - 40,
                "assigned": 40, "total": total} for i in range(n)]
    hist_file.write_text(json.dumps(entries), encoding="utf-8")
    return entries


def test_concurrent_snapshots_never_lose_data(hist_file):
    """8 threads x 50 non-spike appends must all survive — no wipe, no lost updates."""
    _seed(hist_file, 5, total=100)

    def worker():
        for _ in range(50):
            app_module._save_snapshot(60, 40)  # total=100 -> never a spike

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    saved = json.loads(hist_file.read_text(encoding="utf-8"))
    assert len(saved) == 5 + 8 * 50  # every append kept, nothing clobbered


def test_load_history_preserves_corrupt_file(hist_file):
    """A corrupt file must be set aside, not silently dropped and overwritten."""
    hist_file.write_text("{ this is not json", encoding="utf-8")

    result = app_module._load_history()

    assert result == []
    assert os.path.exists(str(hist_file) + ".corrupt")
    assert (hist_file.parent / "history.json.corrupt").read_text(
        encoding="utf-8") == "{ this is not json"


def test_save_snapshot_persists_closed_count(hist_file):
    """The closed count is stored per snapshot so the Gesloten line has real
    persisted history instead of being re-derived from a 90-day live scrape."""
    app_module._save_snapshot(60, 40, closed_count=7)
    saved = json.loads(hist_file.read_text(encoding="utf-8"))
    assert saved[-1]["closed"] == 7
    assert saved[-1]["total"] == 100


def test_save_is_atomic_leaves_no_partial_file(hist_file):
    """After a save, the dir holds only the final file (+backup) — no stray temp."""
    _seed(hist_file, 3, total=100)
    app_module._save_snapshot(60, 40)

    names = sorted(p.name for p in hist_file.parent.iterdir())
    # history.json plus at most a .bak; never a leftover .tmp
    assert "history.json" in names
    assert not any(n.endswith(".tmp") for n in names)

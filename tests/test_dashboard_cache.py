"""Server-side polling: the scheduler drives Trengo fetches + history, clients
read a cache. A page view must not trigger its own Trengo scrape or history write.
"""
import json
from unittest.mock import patch

import pytest

import app as app_module


FAKE = {
    "summary": {"total": 100, "new": 60, "assigned": 40, "new_today": 5},
    "teams": [], "users": [], "age_buckets": [], "last_updated": "2026-08-04T09:00:00",
}


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "HISTORY_FILE", str(tmp_path / "history.json"))
    app_module._dashboard_cache["data"] = None
    app_module._dashboard_cache["fetched_at"] = None
    yield
    app_module._dashboard_cache["data"] = None
    app_module._dashboard_cache["fetched_at"] = None


def test_refresh_populates_cache_and_writes_one_history_point(tmp_path):
    with patch.object(app_module, "TrengoClient") as mock:
        mock.return_value.get_dashboard_data.return_value = FAKE
        app_module._refresh_dashboard()

    assert app_module._dashboard_cache["data"] == FAKE
    saved = json.loads((tmp_path / "history.json").read_text(encoding="utf-8"))
    assert len(saved) == 1
    assert saved[0]["total"] == 100


def test_dashboard_route_serves_cache_without_refetching():
    client = app_module.app.test_client()
    with patch.object(app_module, "TrengoClient") as mock:
        mock.return_value.get_dashboard_data.return_value = FAKE
        r1 = client.get("/api/dashboard")   # cold -> one fetch warms cache
        r2 = client.get("/api/dashboard")   # warm -> served from cache
        r3 = client.get("/api/dashboard")
        assert r1.get_json()["summary"]["total"] == 100
        assert r2.get_json() == r1.get_json()
        assert mock.return_value.get_dashboard_data.call_count == 1  # not per-view


def test_force_refresh_refetches():
    client = app_module.app.test_client()
    with patch.object(app_module, "TrengoClient") as mock:
        mock.return_value.get_dashboard_data.return_value = FAKE
        client.get("/api/dashboard")            # warm (fetch #1)
        client.get("/api/dashboard?refresh=1")  # force (fetch #2)
        assert mock.return_value.get_dashboard_data.call_count == 2

"""/api/closed must be served from a warm cache with a dedup lock, like
/api/dashboard. Its Trengo scrape is heavy, so a cold page view or a burst of
concurrent viewers must never each launch their own scrape.
"""
import threading
import time
from unittest.mock import patch

import pytest

import app as app_module


@pytest.fixture(autouse=True)
def reset_closed_cache():
    app_module._closed_cache["data"] = None
    app_module._closed_cache["fetched_at"] = None
    yield
    app_module._closed_cache["data"] = None
    app_module._closed_cache["fetched_at"] = None


def test_closed_route_serves_cache_without_refetching():
    client = app_module.app.test_client()
    with patch.object(app_module, "TrengoClient") as mock:
        mock.return_value.get_closed_tickets.return_value = []
        client.get("/api/closed")   # cold -> one scrape warms cache
        client.get("/api/closed")   # warm -> served from cache
        client.get("/api/closed")
        assert mock.return_value.get_closed_tickets.call_count == 1


def test_concurrent_cold_closed_share_one_fetch():
    def slow_scrape():
        time.sleep(0.25)  # long enough for the threads to overlap
        return []

    with patch.object(app_module, "TrengoClient") as mock:
        mock.return_value.get_closed_tickets.side_effect = slow_scrape
        threads = [threading.Thread(target=app_module._get_closed_data)
                   for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert mock.return_value.get_closed_tickets.call_count == 1

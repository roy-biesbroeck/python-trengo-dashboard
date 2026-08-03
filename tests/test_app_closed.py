from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import app as app_module


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _reset_cache():
    app_module._closed_cache["data"] = None
    app_module._closed_cache["fetched_at"] = None


def test_created_today_closed_counts_same_day_tickets():
    """Tickets created AND closed today must be counted separately.

    They disappear from the open-ticket list, so summary.new_today misses them.
    Without this count the 'netto gesloten' badge overstates the queue drop.
    """
    now = datetime.now().astimezone()
    yesterday = now - timedelta(days=1)

    tickets = [
        # created today, closed today -> counts
        {"created_at": _iso(now - timedelta(hours=2)), "closed_at": _iso(now - timedelta(hours=1))},
        # created yesterday, closed today -> does not count
        {"created_at": _iso(yesterday), "closed_at": _iso(now - timedelta(hours=3))},
    ]

    _reset_cache()
    with patch.object(app_module, "TrengoClient") as mock_client:
        mock_client.return_value.get_closed_tickets.return_value = tickets
        data = app_module._get_closed_data()
    _reset_cache()

    assert data["closed_today"] == 2
    assert data["created_today_closed"] == 1

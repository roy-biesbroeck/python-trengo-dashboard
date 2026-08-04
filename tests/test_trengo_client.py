import pytest
from unittest.mock import patch, MagicMock
from trengo_client import TrengoClient


@pytest.fixture
def client():
    with patch.dict("os.environ", {"TRENGO_API_TOKEN": "test-token"}):
        return TrengoClient()


def test_close_ticket_success(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()

    with patch("trengo_client.requests.post", return_value=mock_resp) as mock_post:
        result = client.close_ticket(12345)

    assert result is True
    mock_post.assert_called_once_with(
        "https://app.trengo.com/api/v2/tickets/12345/close",
        headers=client.headers,
        json={},
        timeout=15,
    )


def test_close_ticket_failure(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.raise_for_status.side_effect = Exception("Bad Request")

    with patch("trengo_client.requests.post", return_value=mock_resp):
        result = client.close_ticket(99999)

    assert result is False


def test_get_ticket_messages(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [
            {"id": 1, "body": "Mijn kassa doet het niet", "type": "INBOUND"},
            {"id": 2, "body": "We kijken ernaar", "type": "OUTBOUND"},
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("requests.get", return_value=mock_response) as mock_get:
        messages = client.get_ticket_messages(999)

    assert len(messages) == 2
    assert messages[0]["body"] == "Mijn kassa doet het niet"
    mock_get.assert_called_once()
    assert "999" in mock_get.call_args[0][0]


def test_get_ticket_labels(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [
            {"id": 101, "name": "Route Kust", "color": "#ffce54"},
            {"id": 102, "name": "Support - Kassa", "color": "#5d9cec"},
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("requests.get", return_value=mock_response) as mock_get:
        labels = client.get_ticket_labels(999)

    assert len(labels) == 2
    assert labels[0]["name"] == "Route Kust"


def test_attach_label(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    with patch("requests.post", return_value=mock_response) as mock_post:
        result = client.attach_label(999, 101)

    assert result is True
    mock_post.assert_called_once()


def test_attach_label_failure(client):
    with patch("requests.post", side_effect=Exception("API error")):
        result = client.attach_label(999, 101)

    assert result is False


def test_get_labels(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [
            {"id": 101, "name": "Route Kust"},
            {"id": 102, "name": "RMA"},
        ],
        "links": {},
    }
    mock_response.raise_for_status = MagicMock()

    with patch("requests.get", return_value=mock_response):
        labels = client.get_labels()

    assert len(labels) == 2
    assert labels[1]["name"] == "RMA"


def test_get_closed_tickets_filters_server_side_by_updated_at():
    """get_closed_tickets must send updated_at_gt so Trengo only returns tickets
    updated within the retention window, instead of scraping all closed tickets
    ever. Closing is an update (closed_at <= updated_at), so a ticket closed
    within 90 days is guaranteed to fall inside this window — no recent close is
    missed. The client-side 90-day filter still trims the extras."""
    from datetime import datetime, timezone
    from trengo_client import parse_datetime

    fake = [
        {"id": 1, "status": "CLOSED", "closed_at": "2020-01-01T00:00:00Z"},  # old -> trimmed
        {"id": 2, "status": "CLOSED", "closed_at": None},                    # missing -> skipped
    ]
    with patch.object(TrengoClient, "_get_paginated", return_value=fake) as mock_get:
        with patch("trengo_client.os.getenv", return_value="dummy-token"):
            result = TrengoClient().get_closed_tickets()

    mock_get.assert_called_once()
    endpoint, params = mock_get.call_args.args
    assert endpoint == "tickets"
    assert params["status"] == "CLOSED"
    cutoff = parse_datetime(params["updated_at_gt"])
    assert cutoff is not None
    age_days = (datetime.now(timezone.utc) - cutoff).total_seconds() / 86400
    assert 90 <= age_days <= 100  # ~92-day window (retention + buffer)
    assert [t["id"] for t in result] == []  # old ticket still trimmed client-side


def test_get_all_closed_tickets_returns_every_closed_ticket_without_date_filter():
    """get_all_closed_tickets must not apply the 90-day filter."""
    fake_tickets = [
        {"id": 1, "status": "CLOSED", "closed_at": "2020-01-01T00:00:00Z"},  # very old
        {"id": 2, "status": "CLOSED", "closed_at": "2026-04-01T00:00:00Z"},  # recent
        {"id": 3, "status": "CLOSED", "closed_at": None},                     # missing
    ]
    with patch.object(TrengoClient, "_get_paginated", return_value=fake_tickets) as mock_get:
        with patch("trengo_client.os.getenv", return_value="dummy-token"):
            client = TrengoClient()
            result = client.get_all_closed_tickets()
    assert [t["id"] for t in result] == [1, 2, 3]
    mock_get.assert_called_once_with("tickets", {"status": "CLOSED"})

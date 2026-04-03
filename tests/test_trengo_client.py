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

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

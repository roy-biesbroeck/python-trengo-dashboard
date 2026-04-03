import pytest
from customer_matcher import CustomerMatcher


@pytest.fixture
def matcher():
    cache = {
        "100": {"customer_name": "La Porte Dór", "label_counts": {"Route Kust": 5}},
        "200": {"customer_name": "Restaurant De Haven", "label_counts": {"Route Hulst": 3}},
        "300": {"customer_name": "Frituur het Pleintje", "label_counts": {"Route Kust": 2}},
        "400": {"customer_name": "Bakkerij Janssen", "label_counts": {"Route Kanaalzone": 7}},
        "500": {"customer_name": "Lizzy Sluis", "label_counts": {"Route Kust": 4}},
    }
    return CustomerMatcher(cache)


class TestCustomerMatcher:
    def test_exact_match(self, matcher):
        result = matcher.find("La Porte Dór")
        assert result is not None
        assert result["contact_id"] == "100"
        assert result["customer_name"] == "La Porte Dór"

    def test_case_insensitive_match(self, matcher):
        result = matcher.find("la porte dór")
        assert result is not None
        assert result["contact_id"] == "100"

    def test_accent_insensitive_match(self, matcher):
        result = matcher.find("La Porte Dor")
        assert result is not None
        assert result["contact_id"] == "100"

    def test_close_match(self, matcher):
        result = matcher.find("La Porte d'Or")
        assert result is not None
        assert result["contact_id"] == "100"

    def test_no_match_returns_none(self, matcher):
        result = matcher.find("Totaal Onbekende Klant BV")
        assert result is None

    def test_low_similarity_returns_none(self, matcher):
        result = matcher.find("XYZ")
        assert result is None

    def test_returns_label_counts(self, matcher):
        result = matcher.find("Bakkerij Janssen")
        assert result["label_counts"] == {"Route Kanaalzone": 7}

    def test_empty_query(self, matcher):
        assert matcher.find("") is None
        assert matcher.find(None) is None

    def test_partial_name_match(self, matcher):
        result = matcher.find("Lizzy Sluis")
        assert result is not None
        assert result["contact_id"] == "500"

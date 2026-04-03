import pytest
from label_config import (
    LABELS,
    MANUAL_ONLY_LABELS,
    ROUTE_LABELS,
    SUGGESTABLE_LABELS,
    get_label_id,
    get_label_name,
    get_label_definitions_prompt,
)


def test_labels_is_dict_with_entries():
    assert isinstance(LABELS, dict)
    assert len(LABELS) >= 30


def test_manual_only_labels_excluded_from_suggestable():
    for label_name in MANUAL_ONLY_LABELS:
        assert label_name not in SUGGESTABLE_LABELS


def test_route_labels_are_subset_of_suggestable():
    for label_name in ROUTE_LABELS:
        assert label_name in SUGGESTABLE_LABELS


def test_get_label_id_known():
    assert get_label_id("Route Kust") == 1578209


def test_get_label_id_unknown():
    assert get_label_id("Niet bestaand label") is None


def test_get_label_name_known():
    assert get_label_name(1578209) == "Route Kust"


def test_get_label_name_unknown():
    assert get_label_name(999999) is None


def test_get_label_definitions_prompt_contains_labels():
    prompt = get_label_definitions_prompt()
    assert "Route Kust" in prompt
    assert "Reparatie @BA" in prompt
    assert "MANUAL ONLY" not in prompt


def test_suggestable_labels_has_descriptions():
    for name, info in SUGGESTABLE_LABELS.items():
        assert "description" in info, f"{name} missing description"
        assert len(info["description"]) > 5, f"{name} has empty description"

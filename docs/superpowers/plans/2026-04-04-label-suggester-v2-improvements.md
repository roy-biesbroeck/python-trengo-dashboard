# Label Suggester v2 Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the label suggester accurate for internal tickets (Jos/Carl/Staf creating tickets for customers) and capture label history even when labels are removed before ticket closure.

**Architecture:** Three improvements: (1) Internal contacts blacklist so the system knows when to extract the real customer name via GPT, (2) Label history parsing from ticket message events ("Label X toegevoegd/verwijderd") instead of reading current labels, (3) Fuzzy customer name matching to connect GPT-extracted names to known customer histories.

**Tech Stack:** Python/Flask, OpenAI SDK (gpt-4o-mini), Trengo REST API, difflib (stdlib — fuzzy matching)

**Spec:** `docs/superpowers/specs/2026-04-04-label-suggester-v2-improvements.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `label_config.py` | Add INTERNAL_CONTACTS set |
| Create | `label_history_parser.py` | Parse label events from ticket messages |
| Create | `customer_matcher.py` | Fuzzy customer name → contact_id lookup |
| Create | `tests/test_label_history_parser.py` | Tests for label event parsing |
| Create | `tests/test_customer_matcher.py` | Tests for fuzzy matching |
| Modify | `label_suggester.py` | Update scan, classify, and history functions to use new modules |
| Modify | `harvest_history.py` | Use label event parsing instead of current labels, exclude internal contacts |
| Modify | `tests/test_label_suggester.py` | Add tests for internal ticket flow |
| Modify | `tests/test_harvest_history.py` | Update tests for new harvest behavior |

---

## Task 1: Internal Contacts Configuration

**Files:**
- Modify: `label_config.py`
- Modify: `tests/test_label_config.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_label_config.py`:

```python
from label_config import INTERNAL_CONTACTS, is_internal_contact


def test_internal_contacts_is_set():
    assert isinstance(INTERNAL_CONTACTS, set)
    assert "Jos Biesbroeck" in INTERNAL_CONTACTS
    assert "support@biesbroeck.eu" in INTERNAL_CONTACTS
    assert "HeyTom" in INTERNAL_CONTACTS


def test_is_internal_contact_by_name():
    assert is_internal_contact(name="Jos Biesbroeck") is True
    assert is_internal_contact(name="Restaurant De Haven") is False


def test_is_internal_contact_case_insensitive():
    assert is_internal_contact(name="jos biesbroeck") is True
    assert is_internal_contact(name="JOS BIESBROECK") is True


def test_is_internal_contact_by_email():
    assert is_internal_contact(name="support@biesbroeck.eu") is True
    assert is_internal_contact(name="info@unitouch.eu") is True
    assert is_internal_contact(name="klant@example.com") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_label_config.py::test_internal_contacts_is_set -v`
Expected: FAIL — INTERNAL_CONTACTS not found

- [ ] **Step 3: Add INTERNAL_CONTACTS and is_internal_contact to label_config.py**

Add at the end of `label_config.py`:

```python
# Internal team contacts — their tickets are created on behalf of customers.
# Skip their contact history for Layer 1; use GPT to extract the real customer.
INTERNAL_CONTACTS = {
    "Jos Biesbroeck",
    "Carl van Dorsselaer",
    "Staf Biesbroeck",
    "Michael Grguric",
    "Roy Ernst",
    "Ludwig",
    "Martine",
    "support@biesbroeck.eu",
    "info@unitouch.eu",
    "HeyTom",
    "Sales -Martens Afrekensystemen",
    "Biesbroeck Automation",
}

# Lowercase set for fast case-insensitive lookup
_INTERNAL_CONTACTS_LOWER = {name.lower() for name in INTERNAL_CONTACTS}


def is_internal_contact(name: str = "") -> bool:
    """Check if a contact name belongs to an internal team member."""
    if not name:
        return False
    return name.lower().strip() in _INTERNAL_CONTACTS_LOWER
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_label_config.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add label_config.py tests/test_label_config.py
git commit -m "feat: add internal contacts blacklist to label config

Team members who create tickets on behalf of customers are now
identified so the system can extract the real customer name."
```

---

## Task 2: Label History Parser

**Files:**
- Create: `label_history_parser.py`
- Create: `tests/test_label_history_parser.py`

New module that parses "Label X toegevoegd/verwijderd" events from ticket messages.

- [ ] **Step 1: Write failing tests**

Create `tests/test_label_history_parser.py`:

```python
import pytest
from label_history_parser import parse_label_events, get_effective_labels


class TestParseLabelEvents:
    def test_parses_added_event(self):
        messages = [
            {"body": "Label Route Kust toegevoegd door Roy Ernst op 03-04-2026, 08:37", "type": "SYSTEM"},
        ]
        events = parse_label_events(messages)
        assert len(events) == 1
        assert events[0]["label"] == "Route Kust"
        assert events[0]["action"] == "added"

    def test_parses_removed_event(self):
        messages = [
            {"body": "Label Route Kust verwijderd door Ziggy op 03-04-2026, 15:00", "type": "SYSTEM"},
        ]
        events = parse_label_events(messages)
        assert len(events) == 1
        assert events[0]["label"] == "Route Kust"
        assert events[0]["action"] == "removed"

    def test_parses_multiple_events(self):
        messages = [
            {"body": "Hallo, mijn kassa doet het niet", "type": "INBOUND"},
            {"body": "Label Support - Kassa toegevoegd door Roy Ernst op 03-04-2026, 08:37", "type": "SYSTEM"},
            {"body": "Label Route Kust toegevoegd door Roy Ernst op 03-04-2026, 08:37", "type": "SYSTEM"},
            {"body": "We kijken ernaar", "type": "OUTBOUND"},
            {"body": "Label Route Jos toegevoegd door Jos Biesbroeck op 03-04-2026, 09:25", "type": "SYSTEM"},
        ]
        events = parse_label_events(messages)
        assert len(events) == 3
        labels = [e["label"] for e in events]
        assert "Support - Kassa" in labels
        assert "Route Kust" in labels
        assert "Route Jos" in labels

    def test_ignores_non_label_messages(self):
        messages = [
            {"body": "Hallo, mijn kassa doet het niet", "type": "INBOUND"},
            {"body": "We kijken ernaar", "type": "OUTBOUND"},
            {"body": "Automatisch toegewezen aan Team Support", "type": "SYSTEM"},
        ]
        events = parse_label_events(messages)
        assert events == []

    def test_handles_none_body(self):
        messages = [
            {"body": None, "type": "SYSTEM"},
            {},
        ]
        events = parse_label_events(messages)
        assert events == []


class TestGetEffectiveLabels:
    def test_added_only(self):
        messages = [
            {"body": "Label Route Kust toegevoegd door Roy op 01-04-2026, 10:00", "type": "SYSTEM"},
            {"body": "Label Support - Kassa toegevoegd door Roy op 01-04-2026, 10:01", "type": "SYSTEM"},
        ]
        labels = get_effective_labels(messages)
        assert labels == {"Route Kust", "Support - Kassa"}

    def test_added_then_removed(self):
        messages = [
            {"body": "Label Route Hulst toegevoegd door Roy op 01-04-2026, 10:00", "type": "SYSTEM"},
            {"body": "Label Route Hulst verwijderd door Roy op 01-04-2026, 10:05", "type": "SYSTEM"},
            {"body": "Label Route Kust toegevoegd door Roy op 01-04-2026, 10:06", "type": "SYSTEM"},
        ]
        labels = get_effective_labels(messages)
        assert "Route Hulst" not in labels  # corrected
        assert "Route Kust" in labels

    def test_removed_without_add_ignored(self):
        messages = [
            {"body": "Label Urgent verwijderd door Ziggy op 01-04-2026, 15:00", "type": "SYSTEM"},
        ]
        labels = get_effective_labels(messages)
        assert labels == set()

    def test_label_removed_and_re_added(self):
        messages = [
            {"body": "Label Route Kust toegevoegd door Roy op 01-04-2026, 10:00", "type": "SYSTEM"},
            {"body": "Label Route Kust verwijderd door Ziggy op 01-04-2026, 15:00", "type": "SYSTEM"},
            {"body": "Label Route Kust toegevoegd door Roy op 02-04-2026, 09:00", "type": "SYSTEM"},
        ]
        labels = get_effective_labels(messages)
        assert "Route Kust" in labels  # re-added, so it counts

    def test_ziggy_removes_all_labels_before_closing(self):
        """Real scenario: labels applied during work, all removed before close."""
        messages = [
            {"body": "Label Route Kust toegevoegd door Roy op 01-04-2026, 10:00", "type": "SYSTEM"},
            {"body": "Label Support - Kassa toegevoegd door Roy op 01-04-2026, 10:01", "type": "SYSTEM"},
            {"body": "Label Route Kust verwijderd door Ziggy op 03-04-2026, 16:00", "type": "SYSTEM"},
            {"body": "Label Support - Kassa verwijderd door Ziggy op 03-04-2026, 16:00", "type": "SYSTEM"},
        ]
        labels = get_effective_labels(messages)
        # Conservative approach: added minus removed = empty
        assert labels == set()

    def test_ziggy_removes_all_but_labels_were_there(self):
        """Use get_ever_applied_labels for the 'count everything that was ever added' approach."""
        from label_history_parser import get_ever_applied_labels
        messages = [
            {"body": "Label Route Kust toegevoegd door Roy op 01-04-2026, 10:00", "type": "SYSTEM"},
            {"body": "Label Support - Kassa toegevoegd door Roy op 01-04-2026, 10:01", "type": "SYSTEM"},
            {"body": "Label Route Kust verwijderd door Ziggy op 03-04-2026, 16:00", "type": "SYSTEM"},
            {"body": "Label Support - Kassa verwijderd door Ziggy op 03-04-2026, 16:00", "type": "SYSTEM"},
        ]
        labels = get_ever_applied_labels(messages)
        assert "Route Kust" in labels
        assert "Support - Kassa" in labels
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_label_history_parser.py -v`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Create label_history_parser.py**

```python
"""Parse label add/remove events from Trengo ticket messages.

Trengo records label changes as system messages in the ticket feed:
  "Label Route Kust toegevoegd door Roy Ernst op 03-04-2026, 08:37"
  "Label Route Kust verwijderd door Ziggy op 03-04-2026, 15:00"

This module extracts those events to reconstruct the true label history,
even when labels are removed before a ticket is closed.
"""

import re
from typing import Dict, List, Set

# Match "Label <name> toegevoegd door <person> op <date>"
_LABEL_ADDED = re.compile(r"^Label (.+?) toegevoegd door .+ op .+$")
# Match "Label <name> verwijderd door <person> op <date>"
_LABEL_REMOVED = re.compile(r"^Label (.+?) verwijderd door .+ op .+$")


def parse_label_events(messages: List[Dict]) -> List[Dict]:
    """Parse label add/remove events from ticket messages.

    Returns list of dicts: [{"label": str, "action": "added"|"removed"}]
    """
    events = []
    for msg in messages:
        body = msg.get("body") or ""
        body = body.strip()
        if not body:
            continue

        match_add = _LABEL_ADDED.match(body)
        if match_add:
            events.append({"label": match_add.group(1), "action": "added"})
            continue

        match_remove = _LABEL_REMOVED.match(body)
        if match_remove:
            events.append({"label": match_remove.group(1), "action": "removed"})

    return events


def get_effective_labels(messages: List[Dict]) -> Set[str]:
    """Get labels that are effectively applied (added minus removed).

    Conservative approach: if a label was added then removed, it does NOT count.
    If it was added, removed, then re-added, it DOES count.
    """
    events = parse_label_events(messages)
    added = set()
    removed = set()

    for event in events:
        label = event["label"]
        if event["action"] == "added":
            added.add(label)
            removed.discard(label)  # re-adding clears previous removal
        elif event["action"] == "removed":
            removed.add(label)

    return added - removed


def get_ever_applied_labels(messages: List[Dict]) -> Set[str]:
    """Get ALL labels that were ever added, regardless of removal.

    Use this for the harvest to capture labels even when team members
    remove them before closing. Less conservative than get_effective_labels.
    """
    events = parse_label_events(messages)
    return {e["label"] for e in events if e["action"] == "added"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_label_history_parser.py -v`
Expected: All 11 tests PASS

- [ ] **Step 5: Commit**

```bash
git add label_history_parser.py tests/test_label_history_parser.py
git commit -m "feat: add label history parser for ticket message events

Parses 'Label X toegevoegd/verwijderd' events from Trengo messages.
Two modes: effective labels (added - removed) and ever-applied labels."
```

---

## Task 3: Customer Name Fuzzy Matcher

**Files:**
- Create: `customer_matcher.py`
- Create: `tests/test_customer_matcher.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_customer_matcher.py`:

```python
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
        """Lizzy Sluis should match even if Jos writes just 'Lizzy Sluis'."""
        result = matcher.find("Lizzy Sluis")
        assert result is not None
        assert result["contact_id"] == "500"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_customer_matcher.py -v`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Create customer_matcher.py**

```python
"""Fuzzy customer name matching for the label suggester.

When an internal team member creates a ticket, GPT extracts the real
customer name from the message. This module matches that name against
known customers in the history cache.
"""

import unicodedata
from difflib import SequenceMatcher
from typing import Dict, Optional


def _normalize(text: str) -> str:
    """Normalize text for comparison: lowercase, strip accents, remove punctuation."""
    if not text:
        return ""
    # Lowercase
    text = text.lower().strip()
    # Remove accents (é → e, ó → o, etc.)
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    # Remove common punctuation
    text = text.replace("'", "").replace("`", "").replace("'", "").replace("-", " ")
    return text


class CustomerMatcher:
    """Match customer names against the history cache using fuzzy matching."""

    SIMILARITY_THRESHOLD = 0.75

    def __init__(self, cache: Dict):
        """Initialize with customer history cache dict.

        cache format: {"contact_id": {"customer_name": str, "label_counts": dict, ...}}
        """
        self._entries = []
        for contact_id, data in cache.items():
            name = data.get("customer_name", "")
            if name and name != "Onbekend":
                self._entries.append({
                    "contact_id": contact_id,
                    "customer_name": name,
                    "normalized": _normalize(name),
                    "label_counts": data.get("label_counts", {}),
                })

    def find(self, query: str) -> Optional[Dict]:
        """Find the best matching customer for a query name.

        Returns dict with contact_id, customer_name, label_counts, similarity.
        Returns None if no match above threshold.
        """
        if not query:
            return None

        query_norm = _normalize(query)
        if not query_norm:
            return None

        best_match = None
        best_score = 0

        for entry in self._entries:
            # Exact normalized match
            if query_norm == entry["normalized"]:
                return {
                    "contact_id": entry["contact_id"],
                    "customer_name": entry["customer_name"],
                    "label_counts": entry["label_counts"],
                    "similarity": 1.0,
                }

            # Fuzzy match
            score = SequenceMatcher(None, query_norm, entry["normalized"]).ratio()
            if score > best_score:
                best_score = score
                best_match = entry

        if best_match and best_score >= self.SIMILARITY_THRESHOLD:
            return {
                "contact_id": best_match["contact_id"],
                "customer_name": best_match["customer_name"],
                "label_counts": best_match["label_counts"],
                "similarity": round(best_score, 2),
            }

        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_customer_matcher.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add customer_matcher.py tests/test_customer_matcher.py
git commit -m "feat: add fuzzy customer name matcher

Matches GPT-extracted customer names against the history cache.
Handles accents, case differences, and minor spelling variations."
```

---

## Task 4: Update GPT Prompt for Internal Tickets

**Files:**
- Modify: `label_suggester.py`
- Modify: `tests/test_label_suggester.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_label_suggester.py`:

```python
from label_suggester import _build_classification_prompt, _build_internal_classification_prompt


class TestBuildInternalClassificationPrompt:
    def test_includes_internal_instruction(self):
        prompt = _build_internal_classification_prompt(
            "Kassa kapot", "La Porte Dór\n\nKassa start niet meer op",
            creator_name="Jos Biesbroeck",
        )
        assert "interne collega" in prompt
        assert "Jos Biesbroeck" in prompt
        assert "klantnaam" in prompt.lower() or "Klantnaam" in prompt

    def test_includes_label_definitions(self):
        prompt = _build_internal_classification_prompt(
            "Test", "Test bericht", creator_name="Jos",
        )
        assert "Route Kust" in prompt
        assert "Support - Kassa" in prompt

    def test_requests_extracted_customer(self):
        prompt = _build_internal_classification_prompt(
            "Test", "Test", creator_name="Jos",
        )
        assert "extracted_customer" in prompt

    def test_normal_prompt_unchanged(self):
        prompt = _build_classification_prompt("Test", "Test bericht")
        assert "interne collega" not in prompt
        assert "extracted_customer" not in prompt


class TestClassifyInternalTicket:
    def test_returns_extracted_customer_from_gpt(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "extracted_customer": "La Porte Dór",
            "suggestions": [
                {"label": "Support - Kassa", "confidence": 88, "reason": "Kassa probleem"},
            ]
        })

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("label_suggester._get_openai_client", return_value=mock_client):
            result = classify_ticket_content(
                "Kassa kapot",
                "La Porte Dór\n\nKassa start niet meer op",
                internal_creator="Jos Biesbroeck",
            )

        assert result["extracted_customer"] == "La Porte Dór"
        assert len(result["suggestions"]) == 1
        assert result["suggestions"][0]["label"] == "Support - Kassa"

    def test_normal_ticket_returns_no_extracted_customer(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "suggestions": [
                {"label": "Support - Kassa", "confidence": 90, "reason": "Kassa"},
            ]
        })

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("label_suggester._get_openai_client", return_value=mock_client):
            result = classify_ticket_content("Kassa kapot", "Mijn kassa doet het niet")

        assert result["extracted_customer"] is None
        assert len(result["suggestions"]) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_label_suggester.py::TestBuildInternalClassificationPrompt -v`
Expected: FAIL — function doesn't exist

- [ ] **Step 3: Add internal classification prompt and update classify_ticket_content**

Add import at top of `label_suggester.py`:

```python
from label_config import is_internal_contact
```

Add new function after `_build_classification_prompt`:

```python
def _build_internal_classification_prompt(subject: str, message: str, creator_name: str) -> str:
    """Build GPT prompt for tickets created by internal team members."""
    label_defs = get_label_definitions_prompt()
    return f"""Je bent een ticket-classifier voor een Nederlands IT/kassa support bedrijf.

BELANGRIJK: Dit ticket is aangemaakt door een interne collega ({creator_name})
namens een klant. De echte klantnaam staat meestal op de eerste regel(s) van
het bericht, vóór de eigenlijke beschrijving.

Stap 1: Identificeer de echte klantnaam uit het bericht.
Stap 2: Bepaal welke label(s) van toepassing zijn.

Beschikbare labels:
{label_defs}

Regels:
- Kies ALLEEN uit de bovenstaande labels, verzin nooit nieuwe labels
- Geef per suggestie een confidence score van 0-100
- Een ticket kan meerdere labels hebben
- Antwoord ALLEEN in JSON formaat

Antwoord formaat:
{{"extracted_customer": "Klantnaam uit het bericht", "suggestions": [{{"label": "Labelnaam", "confidence": 85, "reason": "Korte uitleg"}}]}}

Ticket onderwerp: {subject}
Ticket bericht: {message}"""
```

Modify `classify_ticket_content` — change signature and implementation. Replace the existing function entirely:

```python
def classify_ticket_content(subject: str, message: str, internal_creator: str = None) -> Dict:
    """Classify ticket content using GPT-4o-mini.

    For internal tickets, also extracts the real customer name.

    Returns dict: {"extracted_customer": str|None, "suggestions": [{"label", "confidence", "reason"}]}
    """
    try:
        client = _get_openai_client()

        if internal_creator:
            prompt = _build_internal_classification_prompt(subject, message, internal_creator)
        else:
            prompt = _build_classification_prompt(subject, message)

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500,
        )

        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            raw = raw.rsplit("```", 1)[0]

        data = json.loads(raw)
        suggestions = data.get("suggestions", [])

        valid = []
        for s in suggestions:
            if s.get("label") in SUGGESTABLE_LABELS:
                valid.append({
                    "label": s["label"],
                    "confidence": int(s.get("confidence", 0)),
                    "reason": s.get("reason", ""),
                })

        extracted_customer = data.get("extracted_customer") if internal_creator else None

        return {
            "extracted_customer": extracted_customer,
            "suggestions": valid,
        }

    except json.JSONDecodeError:
        logger.warning(f"Ongeldige JSON van GPT voor ticket: {subject}")
        return {"extracted_customer": None, "suggestions": []}
    except Exception as e:
        logger.error(f"GPT classificatie fout: {e}")
        return {"extracted_customer": None, "suggestions": []}
```

- [ ] **Step 4: Update existing tests for new return format**

The existing `TestClassifyTicketContent` tests call `classify_ticket_content` and expect a list. Update them to access `result["suggestions"]` instead. For each existing test in `TestClassifyTicketContent`, change:

```python
# Old:
result = classify_ticket_content(...)
assert len(result) == 2
assert result[0]["label"] == "Support - Kassa"

# New:
result = classify_ticket_content(...)
assert len(result["suggestions"]) == 2
assert result["suggestions"][0]["label"] == "Support - Kassa"
```

Apply this pattern to all 4 existing tests in `TestClassifyTicketContent`:
- `test_returns_suggestions_from_gpt`: `result` → `result["suggestions"]`
- `test_returns_empty_on_api_error`: `result` → `result["suggestions"]`
- `test_returns_empty_on_malformed_response`: `result` → `result["suggestions"]`
- `test_filters_out_unknown_labels`: `result` → `result["suggestions"]`

Also update `TestScanForSuggestions` — the mock for `classify_ticket_content` now needs to return the new dict format. Change the mock return values:

```python
# Old:
mock_gpt_result = [
    {"label": "Support - Kassa", "confidence": 90, "reason": "Kassa probleem"},
]
with patch("label_suggester.classify_ticket_content", return_value=mock_gpt_result):

# New:
mock_gpt_result = {
    "extracted_customer": None,
    "suggestions": [
        {"label": "Support - Kassa", "confidence": 90, "reason": "Kassa probleem"},
    ],
}
with patch("label_suggester.classify_ticket_content", return_value=mock_gpt_result):
```

Apply to all 3 tests in `TestScanForSuggestions`.

- [ ] **Step 5: Update scan_for_suggestions to use new return format**

In `scan_for_suggestions()` in `label_suggester.py`, find the line:

```python
content_suggestions = classify_ticket_content(subject, message_text)
```

Replace with:

```python
# Detect internal ticket
creator_name = contact.get("name", "")
internal_creator = creator_name if is_internal_contact(name=creator_name) else None

# Layer 2: Content classification
classification = classify_ticket_content(subject, message_text, internal_creator=internal_creator)
content_suggestions = classification["suggestions"]
extracted_customer = classification.get("extracted_customer")
```

- [ ] **Step 6: Run ALL tests**

Run: `pytest -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add label_suggester.py tests/test_label_suggester.py
git commit -m "feat: add internal ticket GPT prompt with customer extraction

Internal tickets get a modified prompt that asks GPT to identify the
real customer name. Return format now includes extracted_customer."
```

---

## Task 5: Wire Customer Matcher into Scan Orchestrator

**Files:**
- Modify: `label_suggester.py`
- Modify: `tests/test_label_suggester.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_label_suggester.py`:

```python
class TestScanInternalTicket:
    def test_internal_ticket_uses_extracted_customer_history(self, clean_data_files):
        """When Jos creates a ticket for La Porte Dór, use La Porte Dór's route history."""
        mock_client = MagicMock()
        mock_client.get_tickets.side_effect = lambda s: [
            {
                "id": 701, "subject": "Kassa kapot", "status": "OPEN",
                "created_at": "2026-04-03T10:00:00+00:00",
                "contact": {"id": 999, "name": "Jos Biesbroeck"},
                "labels": [],
            },
        ] if s == "OPEN" else []
        mock_client.get_ticket_messages.return_value = [
            {"body": "La Porte Dór\n\nKassa start niet op", "type": "INBOUND"},
        ]

        mock_gpt_result = {
            "extracted_customer": "La Porte Dór",
            "suggestions": [
                {"label": "Support - Kassa", "confidence": 90, "reason": "Kassa probleem"},
            ],
        }

        # Mock the customer history cache with La Porte Dór's route
        mock_cache = {
            "100": {
                "customer_name": "La Porte Dór",
                "label_counts": {"Route Kust": 8},
                "ticket_count": 10,
            },
        }

        with patch("label_suggester.classify_ticket_content", return_value=mock_gpt_result), \
             patch("label_suggester._load_history_cache", return_value=mock_cache), \
             patch("label_suggester._save_history_cache"):
            result = scan_for_suggestions(client=mock_client, threshold=70)

        assert result["suggested"] == 1
        queue = get_suggestion_queue()
        assert len(queue) == 1

        suggestions = queue[0]["suggestions"]
        labels = [s["label"] for s in suggestions]
        assert "Route Kust" in labels  # from La Porte Dór's history
        assert "Support - Kassa" in labels  # from content

    def test_internal_ticket_unknown_customer_still_suggests(self, clean_data_files):
        """New customer from Jos — no history, but content suggestions still work."""
        mock_client = MagicMock()
        mock_client.get_tickets.side_effect = lambda s: [
            {
                "id": 702, "subject": "Overname", "status": "OPEN",
                "created_at": "2026-04-03T10:00:00+00:00",
                "contact": {"id": 999, "name": "Jos Biesbroeck"},
                "labels": [],
            },
        ] if s == "OPEN" else []
        mock_client.get_ticket_messages.return_value = [
            {"body": "Nieuw Restaurant Zeeland\n\nOvername per 1 juni", "type": "INBOUND"},
        ]

        mock_gpt_result = {
            "extracted_customer": "Nieuw Restaurant Zeeland",
            "suggestions": [
                {"label": "Bestelling", "confidence": 75, "reason": "Overname"},
            ],
        }

        with patch("label_suggester.classify_ticket_content", return_value=mock_gpt_result), \
             patch("label_suggester._load_history_cache", return_value={}), \
             patch("label_suggester._save_history_cache"):
            result = scan_for_suggestions(client=mock_client, threshold=70)

        assert result["suggested"] == 1
        queue = get_suggestion_queue()
        suggestions = queue[0]["suggestions"]
        assert any(s["label"] == "Bestelling" for s in suggestions)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_label_suggester.py::TestScanInternalTicket -v`
Expected: FAIL

- [ ] **Step 3: Update scan_for_suggestions to use CustomerMatcher**

Add import at top of `label_suggester.py`:

```python
from customer_matcher import CustomerMatcher
```

In `scan_for_suggestions()`, replace the customer history lookup section. Find this block:

```python
# Layer 1: Customer history
customer_history = {}
if contact_id:
    customer_history = get_customer_label_history(client, contact_id)
```

Replace with:

```python
# Layer 1: Customer history
customer_history = {}
if internal_creator and extracted_customer:
    # Internal ticket: look up the real customer's history
    cache = _load_history_cache()
    matcher = CustomerMatcher(cache)
    match = matcher.find(extracted_customer)
    if match:
        customer_history = match["label_counts"]
        logger.info(
            f"Interne ticket #{ticket_id}: klant '{extracted_customer}' "
            f"gematcht met '{match['customer_name']}' ({match['similarity']:.0%})"
        )
elif contact_id:
    customer_history = get_customer_label_history(client, contact_id)
```

Also update the `add_to_queue` call to include the extracted customer info. Find:

```python
if suggestions:
    add_to_queue({
        "ticket_id": ticket_id,
        "ticket_subject": subject,
        "customer_name": customer_name,
        "contact_id": contact_id,
        "message_preview": message_text[:200],
        "suggestions": suggestions,
    })
```

Replace with:

```python
if suggestions:
    queue_entry = {
        "ticket_id": ticket_id,
        "ticket_subject": subject,
        "customer_name": extracted_customer or customer_name,
        "contact_id": contact_id,
        "message_preview": message_text[:200],
        "suggestions": suggestions,
    }
    if internal_creator:
        queue_entry["internal_creator"] = internal_creator
        queue_entry["extracted_customer"] = extracted_customer
    add_to_queue(queue_entry)
```

- [ ] **Step 4: Run ALL tests**

Run: `pytest -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add label_suggester.py tests/test_label_suggester.py
git commit -m "feat: wire customer matcher into scan for internal tickets

Internal tickets now extract customer name via GPT, fuzzy match against
known customers, and use their route history for suggestions."
```

---

## Task 6: Update Harvest to Use Label Event Parsing

**Files:**
- Modify: `harvest_history.py`
- Modify: `tests/test_harvest_history.py`

- [ ] **Step 1: Write failing tests**

Replace tests in `tests/test_harvest_history.py` to test the new behavior:

```python
import pytest
import json
from unittest.mock import patch, MagicMock
from harvest_history import harvest_customer_history, _group_tickets_by_contact


def _ticket(id, contact_id, labels=None, closed_at="2026-03-15T10:00:00+00:00",
            contact_name=None, messages=None):
    t = {
        "id": id,
        "contact_id": contact_id,
        "contact": {"id": contact_id, "name": contact_name or f"Klant {contact_id}"},
        "closed_at": closed_at,
    }
    if labels:
        t["labels"] = [{"name": name} for name in labels]
    return t


def _label_messages(label_events):
    """Build fake messages list from label add/remove events."""
    msgs = []
    for label, action in label_events:
        if action == "added":
            msgs.append({"body": f"Label {label} toegevoegd door Test op 01-04-2026, 10:00", "type": "SYSTEM"})
        elif action == "removed":
            msgs.append({"body": f"Label {label} verwijderd door Test op 01-04-2026, 15:00", "type": "SYSTEM"})
    return msgs


class TestGroupTicketsByContact:
    def test_groups_correctly(self):
        tickets = [
            _ticket(1, 100), _ticket(2, 100), _ticket(3, 200), _ticket(4, 100),
        ]
        groups = _group_tickets_by_contact(tickets)
        assert len(groups) == 2
        assert len(groups[100]) == 3
        assert len(groups[200]) == 1

    def test_skips_tickets_without_contact(self):
        tickets = [
            {"id": 1, "contact_id": None, "contact": None},
            _ticket(2, 100),
        ]
        groups = _group_tickets_by_contact(tickets)
        assert len(groups) == 1


class TestHarvestWithLabelEvents:
    def test_uses_message_events_for_labels(self, tmp_path):
        cache_file = str(tmp_path / "cache.json")

        mock_client = MagicMock()
        mock_client.get_closed_tickets.return_value = [
            _ticket(1, 100, contact_name="Restaurant De Haven"),
            _ticket(2, 100, contact_name="Restaurant De Haven"),
        ]
        mock_client.get_ticket_messages.side_effect = lambda tid: {
            1: _label_messages([("Route Kust", "added"), ("Support - Kassa", "added")]),
            2: _label_messages([("Route Kust", "added")]),
        }[tid]

        result = harvest_customer_history(client=mock_client, cache_file=cache_file)

        with open(cache_file) as f:
            cache = json.load(f)

        assert cache["100"]["label_counts"]["Route Kust"] == 2
        assert cache["100"]["label_counts"]["Support - Kassa"] == 1

    def test_captures_labels_removed_before_closing(self, tmp_path):
        cache_file = str(tmp_path / "cache.json")

        mock_client = MagicMock()
        mock_client.get_closed_tickets.return_value = [
            _ticket(1, 100, contact_name="Test Klant"),
        ]
        # Label was added then removed before closing
        mock_client.get_ticket_messages.return_value = _label_messages([
            ("Route Kust", "added"),
            ("Route Kust", "removed"),
        ])

        result = harvest_customer_history(client=mock_client, cache_file=cache_file)

        with open(cache_file) as f:
            cache = json.load(f)

        # Using get_ever_applied_labels: Route Kust was added so it counts
        assert cache["100"]["label_counts"]["Route Kust"] == 1

    def test_excludes_internal_contacts(self, tmp_path):
        cache_file = str(tmp_path / "cache.json")

        mock_client = MagicMock()
        mock_client.get_closed_tickets.return_value = [
            _ticket(1, 100, contact_name="Restaurant De Haven"),
            _ticket(2, 999, contact_name="Jos Biesbroeck"),  # internal
        ]
        mock_client.get_ticket_messages.side_effect = lambda tid: {
            1: _label_messages([("Route Kust", "added")]),
            2: _label_messages([("Route Hulst", "added"), ("Bestelling", "added")]),
        }[tid]

        result = harvest_customer_history(client=mock_client, cache_file=cache_file)

        with open(cache_file) as f:
            cache = json.load(f)

        assert "100" in cache  # real customer
        assert "999" not in cache  # internal contact excluded

    def test_excludes_manual_only_labels(self, tmp_path):
        cache_file = str(tmp_path / "cache.json")

        mock_client = MagicMock()
        mock_client.get_closed_tickets.return_value = [
            _ticket(1, 100, contact_name="Test"),
        ]
        mock_client.get_ticket_messages.return_value = _label_messages([
            ("Route Kust", "added"),
            ("Route Jos", "added"),  # MANUAL_ONLY
        ])

        harvest_customer_history(client=mock_client, cache_file=cache_file)

        with open(cache_file) as f:
            cache = json.load(f)

        assert "Route Kust" in cache["100"]["label_counts"]
        assert "Route Jos" not in cache["100"]["label_counts"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_harvest_history.py -v`
Expected: FAIL — harvest still uses old approach

- [ ] **Step 3: Rewrite harvest_history.py to use label event parsing**

```python
"""One-time harvest of historical customer label data.

Fetches closed tickets from Trengo, parses label events from ticket
messages, groups by customer, counts labels, and saves to cache.

Usage:
    python harvest_history.py
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Dict, List

from trengo_client import TrengoClient
from label_config import MANUAL_ONLY_LABELS, is_internal_contact
from label_history_parser import get_ever_applied_labels

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DEFAULT_CACHE_FILE = os.path.join(DATA_DIR, "customer_label_history.json")


def _get_contact_id(ticket: Dict):
    contact_id = ticket.get("contact_id")
    if contact_id:
        return contact_id
    contact = ticket.get("contact")
    if isinstance(contact, dict):
        return contact.get("id")
    return None


def _get_contact_name(ticket: Dict) -> str:
    contact = ticket.get("contact")
    if isinstance(contact, dict):
        return contact.get("name", "Onbekend")
    return "Onbekend"


def _group_tickets_by_contact(tickets: List[Dict]) -> Dict[int, List[Dict]]:
    groups: Dict[int, List[Dict]] = {}
    for ticket in tickets:
        contact_id = _get_contact_id(ticket)
        if not contact_id:
            continue
        if contact_id not in groups:
            groups[contact_id] = []
        groups[contact_id].append(ticket)
    return groups


def harvest_customer_history(
    client: TrengoClient = None,
    cache_file: str = None,
) -> Dict:
    if client is None:
        client = TrengoClient()
    if cache_file is None:
        cache_file = DEFAULT_CACHE_FILE

    os.makedirs(os.path.dirname(cache_file), exist_ok=True)

    print("Ophalen gesloten tickets van Trengo...")
    closed_tickets = client.get_closed_tickets()
    print(f"  {len(closed_tickets)} gesloten tickets opgehaald")

    # Fetch messages for each ticket to parse label events
    total = len(closed_tickets)
    print(f"  Berichten ophalen voor {total} tickets (5 parallel)...")
    done = 0

    def fetch_messages(ticket):
        return ticket["id"], client.get_ticket_messages(ticket["id"])

    ticket_messages: Dict[int, list] = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(fetch_messages, t): t for t in closed_tickets}
        for future in as_completed(futures):
            tid, messages = future.result()
            ticket_messages[tid] = messages
            done += 1
            if done % 100 == 0:
                print(f"    {done}/{total} verwerkt...")

    # Parse label events from messages
    print("  Label events parsen...")
    ticket_labels: Dict[int, set] = {}
    for ticket in closed_tickets:
        tid = ticket["id"]
        messages = ticket_messages.get(tid, [])
        labels = get_ever_applied_labels(messages)
        # Filter out MANUAL_ONLY labels
        labels = {l for l in labels if l not in MANUAL_ONLY_LABELS}
        ticket_labels[tid] = labels

    # Group by contact, exclude internal contacts
    groups = _group_tickets_by_contact(closed_tickets)
    print(f"  {len(groups)} unieke contacten gevonden")

    cache: Dict = {}
    internal_skipped = 0
    for contact_id, tickets in groups.items():
        # Check if this is an internal contact
        contact_name = _get_contact_name(tickets[0])
        if is_internal_contact(name=contact_name):
            internal_skipped += 1
            continue

        # Count labels from parsed events
        label_counts: Dict[str, int] = {}
        for ticket in tickets:
            for label in ticket_labels.get(ticket["id"], set()):
                label_counts[label] = label_counts.get(label, 0) + 1

        if label_counts:
            cache[str(contact_id)] = {
                "customer_name": contact_name,
                "label_counts": label_counts,
                "ticket_count": len(tickets),
                "cached_at": datetime.now(timezone.utc).isoformat(),
            }

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    result = {
        "customers_processed": len(groups),
        "customers_with_labels": len(cache),
        "internal_skipped": internal_skipped,
        "tickets_processed": len(closed_tickets),
        "cache_file": cache_file,
    }

    print(f"\nKlaar!")
    print(f"  {result['customers_processed']} contacten verwerkt")
    print(f"  {result['internal_skipped']} interne contacten overgeslagen")
    print(f"  {result['customers_with_labels']} klanten met labels opgeslagen")
    print(f"  Cache opgeslagen in {cache_file}")

    return result


if __name__ == "__main__":
    harvest_customer_history()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_harvest_history.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add harvest_history.py tests/test_harvest_history.py
git commit -m "feat: harvest uses label event parsing and excludes internal contacts

Parses 'Label X toegevoegd/verwijderd' from ticket messages instead of
reading current labels. Captures labels even when removed before closing.
Internal contacts (Jos, Carl, etc.) excluded from customer history."
```

---

## Task 7: Update /tagger UI for Internal Tickets

**Files:**
- Modify: `static/tagger.js`

- [ ] **Step 1: Update renderQueue to show extracted customer info**

In `static/tagger.js`, update the ticket card rendering. Find the line that renders customer name and replace the card template:

In the `renderQueue` function, change the ticket card HTML to show the internal creator info:

```javascript
function renderQueue(queue) {
    loadingEl.style.display = 'none';
    if (!queue || queue.length === 0) {
        queueEl.innerHTML = '';
        emptyEl.style.display = 'block';
        return;
    }
    emptyEl.style.display = 'none';
    queueEl.innerHTML = queue.map(function(ticket) {
        var customerLine = escapeHtml(ticket.customer_name);
        if (ticket.internal_creator) {
            customerLine = escapeHtml(ticket.customer_name) +
                ' <span class="internal-badge">via ' + escapeHtml(ticket.internal_creator) + '</span>';
        }
        return '<div class="ticket-card" id="ticket-' + ticket.ticket_id + '">' +
            '<div class="ticket-header"><div>' +
            '<span class="ticket-id">#' + ticket.ticket_id + '</span>' +
            '<div class="ticket-subject">' + escapeHtml(ticket.ticket_subject) + '</div>' +
            '<div class="ticket-customer">' + customerLine + '</div>' +
            '</div></div>' +
            (ticket.message_preview ? '<div class="ticket-preview">' + escapeHtml(ticket.message_preview) + '</div>' : '') +
            '<div class="suggestions">' +
            ticket.suggestions.map(function(s) { return renderSuggestion(ticket.ticket_id, s); }).join('') +
            '</div></div>';
    }).join('');
}
```

- [ ] **Step 2: Add CSS for internal badge**

Add to `static/tagger.css`:

```css
.internal-badge {
    font-size: 12px;
    color: #8b5cf6;
    background: #f5f3ff;
    padding: 2px 8px;
    border-radius: 8px;
    margin-left: 6px;
    font-weight: 500;
}
```

- [ ] **Step 3: Commit**

```bash
git add static/tagger.js static/tagger.css
git commit -m "feat: show internal creator info on tagger page

Internal tickets show 'via Jos Biesbroeck' badge next to the
extracted customer name for transparency."
```

---

## Task 8: Update Cache Refresh to Use Label Events

**Files:**
- Modify: `label_suggester.py`

- [ ] **Step 1: Update refresh_customer_cache**

In `label_suggester.py`, add import at top:

```python
from label_history_parser import get_ever_applied_labels
```

Replace the existing `refresh_customer_cache` function:

```python
def refresh_customer_cache(client: TrengoClient = None) -> Dict:
    """Re-scan closed tickets and update the customer label history cache.

    Uses label event parsing from ticket messages for accuracy.
    Excludes internal contacts.
    """
    if client is None:
        client = TrengoClient()

    try:
        closed_tickets = client.get_closed_tickets()
    except Exception as e:
        logger.error(f"Cache refresh fout: {e}")
        return {"error": str(e), "customers_updated": 0}

    # Parse label events from messages
    ticket_labels: Dict[int, set] = {}
    for ticket in closed_tickets:
        tid = ticket["id"]
        try:
            messages = client.get_ticket_messages(tid)
            labels = get_ever_applied_labels(messages)
            labels = {l for l in labels if l not in MANUAL_ONLY_LABELS}
            ticket_labels[tid] = labels
        except Exception:
            ticket_labels[tid] = set()

    # Group by contact, exclude internal
    groups: Dict[int, List[Dict]] = {}
    for ticket in closed_tickets:
        contact_id = _get_contact_id(ticket)
        if not contact_id:
            continue
        contact_name = (ticket.get("contact") or {}).get("name", "")
        if is_internal_contact(name=contact_name):
            continue
        if contact_id not in groups:
            groups[contact_id] = []
        groups[contact_id].append(ticket)

    cache = _load_history_cache()
    updated = 0
    for contact_id, tickets in groups.items():
        label_counts: Dict[str, int] = {}
        for ticket in tickets:
            for label in ticket_labels.get(ticket["id"], set()):
                label_counts[label] = label_counts.get(label, 0) + 1

        if label_counts:
            contact_name = (tickets[0].get("contact") or {}).get("name", "Onbekend")
            cache[str(contact_id)] = {
                "customer_name": contact_name,
                "label_counts": label_counts,
                "ticket_count": len(tickets),
                "cached_at": datetime.now(timezone.utc).isoformat(),
            }
            updated += 1

    _save_history_cache(cache)

    logger.info(f"Cache vernieuwd: {updated} klanten bijgewerkt uit {len(closed_tickets)} tickets")
    return {"customers_updated": updated, "tickets_scanned": len(closed_tickets)}
```

- [ ] **Step 2: Run all tests**

Run: `pytest -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add label_suggester.py
git commit -m "feat: cache refresh uses label event parsing

refresh_customer_cache now parses message events instead of reading
current labels. Excludes internal contacts. Captures removed labels."
```

---

## Task 9: Full Test Suite & Final Wiring

**Files:**
- All files

- [ ] **Step 1: Run the full test suite**

Run: `pytest -v`
Expected: All tests PASS (65 original + new tests)

- [ ] **Step 2: Verify no import errors**

Run: `python -c "from label_suggester import scan_for_suggestions, refresh_customer_cache; from harvest_history import harvest_customer_history; from label_history_parser import get_ever_applied_labels; from customer_matcher import CustomerMatcher; print('All imports OK')"`
Expected: `All imports OK`

- [ ] **Step 3: Commit any remaining changes**

```bash
git status
git add -A
git commit -m "chore: v2 improvements complete — internal contacts, label events, customer matching"
```

# AI Label Suggester v2 — Improvements Design Spec

**Date:** 2026-04-04
**Status:** Draft — awaiting user review
**Builds on:** `docs/superpowers/specs/2026-04-03-ai-label-suggester-design.md`

## Problems Identified After v1 Launch

### 1. Internal contacts pollute customer history
Team members (Jos, Carl, Staf, Michael, Ludwig, Roy, Martine) create tickets on behalf of customers. Their contact IDs accumulate labels from many different customers, making their label history useless for predictions. Jos alone has 351 tickets spanning multiple routes and label types.

### 2. Labels removed before closing = lost data
Some team members (notably Ziggy and Ludwig) remove labels from tickets before closing them. The harvest/cache refresh only reads labels currently on closed tickets, so this data is lost. The system can't learn from these tickets.

### 3. No customer name extraction for internal tickets
When Jos emails "La Porte Dór — langsgaan internet nazien", the system needs to understand that the real customer is "La Porte Dór", not Jos Biesbroeck, and look up La Porte Dór's route history.

## Solution Overview

Three improvements that work together:

```
Improvement 1: Internal Contacts Blacklist
  → Skip internal contacts for Layer 1 (history lookup)
  → Add extra GPT instruction to extract real customer name

Improvement 2: Label History from Message Events
  → Parse "Label X toegevoegd" / "Label X verwijderd" from ticket messages
  → Reconstruct which labels were actually used, even if removed before closing
  → Much more reliable than reading current labels on closed tickets

Improvement 3: Customer Name → History Lookup
  → When GPT extracts a customer name from an internal ticket
  → Fuzzy match against known customer names in the cache
  → Use that customer's route history for the suggestion
```

## Improvement 1: Internal Contacts Blacklist

### Configuration

Add to `label_config.py`:

```python
# Internal team contacts — their tickets are created on behalf of customers.
# Skip their contact history for Layer 1; use GPT to extract the real customer.
INTERNAL_CONTACTS = {
    "Jos Biesbroeck",
    "Carl van Dorsselaer",
    "Staf Biesbroeck",
    "Michael Grguric",
    "Roy Ernst",
    "Martine",       # TODO: confirm full name
    "Ludwig",        # TODO: confirm full name
    "support@biesbroeck.eu",
    "info@unitouch.eu",
    "HeyTom",
}
```

Also store by contact ID once known (faster lookup):

```python
INTERNAL_CONTACT_IDS = set()  # populated at runtime from harvest data
```

### Behavior Changes

**In the scan orchestrator (`scan_for_suggestions`):**
- Check if ticket creator is internal
- If internal: skip Layer 1 for the creator's history, use modified GPT prompt
- If not internal: normal flow (Layer 1 + Layer 2)

**Modified GPT prompt for internal tickets:**
```
Dit ticket is aangemaakt door een interne collega namens een klant.
De klantnaam staat meestal in de eerste regel(s) van het bericht.
Identificeer de echte klant en baseer je suggesties daarop.
```

### Harvest Changes

- Exclude internal contact IDs from the customer history cache
- Their tickets should still be processed, but attributed to the real customer (via label history parsing — see Improvement 2)

## Improvement 2: Label History from Message Events

### Discovery

Trengo stores label changes as messages in the ticket feed:
```
"Label Route Kust toegevoegd door Roy Ernst op 03-04-2026, 08:37"
"Label Route Jos toegevoegd door Jos Biesbroeck op 03-04-2026, 09:25"
"Label Route Kust verwijderd door Ziggy op 03-04-2026, 15:00"
```

These are available via the `GET /tickets/{id}/messages` endpoint.

### Parsing Logic

For each closed ticket, fetch messages and parse label events:

```python
import re

LABEL_ADDED_PATTERN = re.compile(
    r"Label (.+?) toegevoegd door .+ op .+"
)
LABEL_REMOVED_PATTERN = re.compile(
    r"Label (.+?) verwijderd door .+ op .+"
)
```

Build a set of labels that were **ever applied** to the ticket:
1. Parse all "toegevoegd" events → add to set
2. Parse all "verwijderd" events → note removals
3. Final set = labels that were added (even if later removed)

**Why "ever applied" instead of "final state"?**
Because if someone added "Route Kust" and then removed it before closing, the intent was still to tag it as Route Kust. The removal is typically cleanup, not a correction. If it was a correction (wrong label), they usually add the correct one — and that one also shows in the history.

### Alternative: Only count labels that were NOT removed

If a label was added AND then removed, we could skip it. This is more conservative:
- Added "Route Hulst" → removed "Route Hulst" → added "Route Kust" → Result: only "Route Kust" counts
- This handles corrections better

**Recommendation:** Use the conservative approach (added minus removed). This correctly handles both:
- Ziggy removing labels before closing (labels still counted since they were added)
- Corrections (wrong label removed, right label added → only right one counts)

### Impact on Harvest

Replace the current approach (reading `ticket.labels`) with message-based label parsing:

**Current flow:**
```
get_closed_tickets() → read ticket.labels → count
```

**New flow:**
```
get_closed_tickets() → get_ticket_messages() → parse label events → count
```

This is slower (extra API call per ticket for messages) but much more accurate. The messages are already fetched in some flows, and the harvest is a one-time operation.

### Impact on Cache Refresh

Same change: `refresh_customer_cache()` should use message-based label parsing instead of reading current labels.

## Improvement 3: Customer Name → History Lookup

### The Problem

When GPT reads Jos's email and extracts "La Porte Dór", we need to find that customer in our history cache to look up their route. But the cache is keyed by contact_id, not by name.

### Solution

Build a reverse lookup: customer name → contact_id. Populated from the harvest data.

```python
# In customer_label_history.json, each entry already has customer_name.
# Build lookup at startup:
name_to_contact = {}
for contact_id, data in cache.items():
    name = data.get("customer_name", "").lower().strip()
    if name and name != "onbekend":
        name_to_contact[name] = contact_id
```

### Fuzzy Matching

Jos might write "La Porte d'Or" while Trengo has "La Porte Dór". Use simple fuzzy matching:
- Normalize: lowercase, strip accents, remove punctuation
- If exact match: use it
- If no exact match: find closest match above a similarity threshold (e.g., 80%)
- Python's `difflib.SequenceMatcher` is sufficient (no new dependencies)

### Flow for Internal Tickets

```
1. Ticket from Jos detected (internal contact)
2. Send to GPT with extra instruction: "extract the real customer name"
3. GPT responds with: {"extracted_customer": "La Porte Dór", "suggestions": [...]}
4. Fuzzy match "La Porte Dór" against known customer names
5. Found: contact_id 12345 → get their route history
6. Combine route history with GPT content suggestions
7. Show on /tagger page with note: "Klant: La Porte Dór (via Jos)"
```

### When Customer Not Found

If the extracted name doesn't match any known customer:
- Use GPT content suggestions only (no route history)
- Show on /tagger: "Nieuwe klant: La Porte Dór (niet gevonden in historie)"
- When team accepts/labels it → the label gets captured → next time the customer is known

## Updated GPT Prompt

### For normal tickets (unchanged):
```
Je bent een ticket-classifier voor een Nederlands IT/kassa support bedrijf.
Bepaal welke label(s) van toepassing zijn op dit ticket.
[label definitions]
[rules]
```

### For internal tickets (new):
```
Je bent een ticket-classifier voor een Nederlands IT/kassa support bedrijf.

BELANGRIJK: Dit ticket is aangemaakt door een interne collega ({creator_name})
namens een klant. De echte klantnaam staat meestal op de eerste regel van
het bericht, vóór de eigenlijke beschrijving.

Stap 1: Identificeer de echte klantnaam uit het bericht.
Stap 2: Bepaal welke label(s) van toepassing zijn.

Beschikbare labels:
[label definitions]

Antwoord formaat:
{
  "extracted_customer": "Klantnaam uit het bericht",
  "suggestions": [{"label": "...", "confidence": 85, "reason": "..."}]
}
```

## Configuration Changes

New env vars in `.env.example`:
```
# Internal contacts (v2)
# No new env vars needed — configured in label_config.py
```

## Data File Changes

`customer_label_history.json` format stays the same but now:
- Excludes internal contacts from having their own entries
- Labels are sourced from message events instead of current ticket labels
- Customer names are used as a reverse lookup key

## Testing Strategy

- Unit tests for label event parsing (regex patterns, add/remove logic)
- Unit tests for fuzzy customer name matching
- Unit tests for internal contact detection
- Mock test for modified GPT prompt (internal vs normal tickets)
- Integration test: internal ticket → extract customer → lookup history → suggest route
- Manual validation: run against 10 known Jos tickets, verify correct customer extraction

## Out of Scope

- Automatic internal contact detection (manually configured list for now)
- Customer merging (same customer with multiple contact IDs)
- Label event timestamps for time-based weighting

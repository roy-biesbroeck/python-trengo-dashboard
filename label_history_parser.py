"""Parse label add/remove events from Trengo ticket messages.

Trengo records label changes as system messages in the ticket feed:
  "Label Route Kust toegevoegd door Roy Ernst op 03-04-2026, 08:37"
  "Label Route Kust verwijderd door Ziggy op 03-04-2026, 15:00"
"""

import re
from typing import Dict, List, Set

_LABEL_ADDED = re.compile(r"^Label (.+?) toegevoegd door .+ op .+$")
_LABEL_REMOVED = re.compile(r"^Label (.+?) verwijderd door .+ op .+$")


def parse_label_events(messages: List[Dict]) -> List[Dict]:
    """Parse label add/remove events from ticket messages."""
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
    """Get labels effectively applied (added minus removed).
    If added then removed then re-added, it counts."""
    events = parse_label_events(messages)
    added = set()
    removed = set()

    for event in events:
        label = event["label"]
        if event["action"] == "added":
            added.add(label)
            removed.discard(label)
        elif event["action"] == "removed":
            removed.add(label)

    return added - removed


def get_ever_applied_labels(messages: List[Dict]) -> Set[str]:
    """Get ALL labels that were ever added, regardless of removal."""
    events = parse_label_events(messages)
    return {e["label"] for e in events if e["action"] == "added"}

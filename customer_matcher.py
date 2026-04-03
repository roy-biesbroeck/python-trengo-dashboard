"""Fuzzy customer name matching for the label suggester.

When an internal team member creates a ticket, GPT extracts the real
customer name. This module matches that name against the history cache.
"""

import unicodedata
from difflib import SequenceMatcher
from typing import Dict, Optional


def _normalize(text: str) -> str:
    """Normalize text for comparison: lowercase, strip accents, remove punctuation."""
    if not text:
        return ""
    text = text.lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.replace("'", "").replace("`", "").replace("\u2019", "").replace("-", " ")
    return text


class CustomerMatcher:
    """Match customer names against the history cache using fuzzy matching."""

    SIMILARITY_THRESHOLD = 0.75

    def __init__(self, cache: Dict):
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
        """Find best matching customer. Returns None if no match above threshold."""
        if not query:
            return None

        query_norm = _normalize(query)
        if not query_norm:
            return None

        best_match = None
        best_score = 0

        for entry in self._entries:
            if query_norm == entry["normalized"]:
                return {
                    "contact_id": entry["contact_id"],
                    "customer_name": entry["customer_name"],
                    "label_counts": entry["label_counts"],
                    "similarity": 1.0,
                }

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

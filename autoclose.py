"""Ruijie Cloud Alarm auto-close module.

Detects duplicate "Ruijie Cloud Alarm Notification" tickets and closes
all but the most recently created one.
"""

import json
import os
import logging
from datetime import datetime, timezone
from typing import List, Dict, Tuple, Optional

from trengo_client import TrengoClient, parse_datetime

RUIJIE_SUBJECT = "ruijie cloud alarm notification"
MAX_CLOSE_PER_RUN = int(os.getenv("AUTOCLOSE_MAX_PER_RUN", "20"))
DRY_RUN = os.getenv("AUTOCLOSE_DRY_RUN", "true").lower() in ("true", "1", "yes")

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "autoclose.log")

logger = logging.getLogger("autoclose")
logger.setLevel(logging.INFO)

# File handler — append to log file
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
_fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
_fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(_fh)


def find_ruijie_duplicates(tickets: List[Dict]) -> Tuple[Optional[int], List[int]]:
    """Find Ruijie alarm tickets and return (keep_id, [close_ids]).

    Returns (None, []) if no Ruijie tickets found.
    Returns (newest_id, []) if only one Ruijie ticket exists.
    Returns (newest_id, [older_ids...]) if duplicates exist.
    """
    ruijie = []
    for t in tickets:
        subject = (t.get("subject") or "").lower().strip()
        if subject == RUIJIE_SUBJECT:
            created = parse_datetime(t.get("created_at"))
            if created:
                ruijie.append((t["id"], created))

    if not ruijie:
        return None, []

    # Sort by created_at descending — newest first
    ruijie.sort(key=lambda x: x[1], reverse=True)

    keep_id = ruijie[0][0]
    close_ids = [tid for tid, _ in ruijie[1:]]

    return keep_id, close_ids


# In-memory state for dashboard display
_last_result = {"ts": None, "result": None}


def get_last_result() -> Dict:
    """Return the last autoclose run result for dashboard display."""
    return _last_result.copy()


def run_autoclose(
    client: TrengoClient = None,
    dry_run: bool = None,
    max_per_run: int = None,
) -> Dict:
    """Run the Ruijie auto-close cycle.

    Returns a dict with: kept, closed_ids, would_close_ids, dry_run, capped, error.
    """
    if dry_run is None:
        dry_run = DRY_RUN
    if max_per_run is None:
        max_per_run = MAX_CLOSE_PER_RUN
    if client is None:
        client = TrengoClient()

    result = {
        "kept": None,
        "closed_ids": [],
        "would_close_ids": [],
        "dry_run": dry_run,
        "capped": False,
        "error": None,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    try:
        open_tickets = client.get_tickets("OPEN")
        assigned_tickets = client.get_tickets("ASSIGNED")
        all_tickets = open_tickets + assigned_tickets

        keep_id, close_ids = find_ruijie_duplicates(all_tickets)
        result["kept"] = keep_id

        if not close_ids:
            logger.info("Geen Ruijie duplicaten gevonden.")
            _last_result["ts"] = result["ts"]
            _last_result["result"] = result
            return result

        # Apply cap
        if len(close_ids) > max_per_run:
            logger.warning(
                f"Limiet bereikt: {len(close_ids)} duplicaten gevonden, "
                f"maximaal {max_per_run} per keer."
            )
            close_ids = close_ids[:max_per_run]
            result["capped"] = True

        if dry_run:
            result["would_close_ids"] = close_ids
            logger.info(
                f"DRY RUN: zou {len(close_ids)} tickets sluiten: {close_ids}. "
                f"Bewaard: #{keep_id}"
            )
        else:
            for tid in close_ids:
                success = client.close_ticket(tid)
                if success:
                    result["closed_ids"].append(tid)
                    logger.info(f"Ticket #{tid} gesloten (bewaard: #{keep_id})")
                else:
                    logger.error(f"Kon ticket #{tid} niet sluiten")

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Autoclose fout: {e}")

    _last_result["ts"] = result["ts"]
    _last_result["result"] = result
    return result

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

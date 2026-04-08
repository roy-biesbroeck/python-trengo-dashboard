"""Probe Trengo's tickets pagination to find the highest non-empty page
without walking every page. Uses a coarse probe + binary search.

Usage:
    python check_pagination.py              # ALL tickets, no status filter
    python check_pagination.py CLOSED       # only CLOSED tickets
    python check_pagination.py OPEN         # only OPEN tickets
"""

import os
import sys
import time
from typing import Optional

import requests
from dotenv import load_dotenv

URL = "https://app.trengo.com/api/v2/tickets"
INITIAL_PROBES = [10, 100, 500, 1000, 2500, 5000, 10000]


def fetch_page(token: str, page: int, status: Optional[str]) -> dict:
    """Fetch one page. Returns {'count': N, 'status': int, 'meta': {...}}."""
    params = {"page": page}
    if status:
        params["status"] = status
    while True:
        resp = requests.get(
            URL,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            params=params,
            timeout=15,
        )
        if resp.status_code == 429:
            print(f"  pagina {page}: rate limit, 3s wachten...")
            time.sleep(3)
            continue
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("data", []) if isinstance(data, dict) else data
        meta = data.get("meta") or {}
        return {"count": len(batch), "status": resp.status_code, "meta": meta}


def main() -> None:
    load_dotenv()
    token = os.getenv("TRENGO_API_TOKEN")
    if not token:
        print("TRENGO_API_TOKEN niet gevonden in .env")
        sys.exit(1)

    status_filter = sys.argv[1] if len(sys.argv) > 1 else None
    label = f"status={status_filter}" if status_filter else "alle statussen"
    print(f"=== Probe: {label} ===")
    print("=== Fase 1: grove probe ===")
    results: dict[int, int] = {}  # page -> count
    for page in INITIAL_PROBES:
        info = fetch_page(token, page, status_filter)
        n = info["count"]
        results[page] = n
        marker = "OK" if n > 0 else "LEEG"
        print(f"  pagina {page:>5d}: {n:>3d} tickets  [{marker}]")
        time.sleep(0.3)

    has_data = sorted(p for p, n in results.items() if n > 0)
    no_data = sorted(p for p, n in results.items() if n == 0)

    if not has_data:
        print("\nResultaat: geen enkele probe-pagina gaf data terug. Vreemd.")
        return
    if not no_data:
        print(
            f"\nResultaat: zelfs pagina {has_data[-1]} bevat nog data — "
            f"je hebt MEER dan {has_data[-1] * 25} closed tickets. "
            f"Verhoog INITIAL_PROBES en draai opnieuw."
        )
        return

    low = has_data[-1]   # last page known to have data
    high = no_data[0]    # first page known to be empty
    print(f"\n=== Fase 2: binaire zoektocht tussen {low} en {high} ===")

    # Binary search for the largest page that returns data
    while high - low > 1:
        mid = (low + high) // 2
        info = fetch_page(token, mid, status_filter)
        n = info["count"]
        marker = "OK" if n > 0 else "LEEG"
        print(f"  pagina {mid:>5d}: {n:>3d} tickets  [{marker}]")
        if n > 0:
            low = mid
        else:
            high = mid
        time.sleep(0.3)

    print(f"\n=== Resultaat ===")
    print(f"  Laatste pagina met data: {low}")
    print(f"  Eerste lege pagina:      {high}")
    print(f"  Geschat aantal tickets:  ~{low * 25} tot {(low * 25) + 25}")
    print(f"  (Trengo geeft 25 tickets per pagina, vaste waarde.)")


if __name__ == "__main__":
    main()

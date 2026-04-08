"""Resumable bulk scraper: diffs Trengo's closed ticket list against the
local cache and only fetches messages for new or changed tickets."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional

from trengo_client import TrengoClient
from ticket_cache import (
    init_db,
    upsert_ticket,
    upsert_messages,
    compute_fingerprint,
    get_all_ticket_fingerprints,
)

ProgressCb = Callable[[int, int], None]


def _tickets_needing_fetch(
    remote_tickets: List[Dict], cached_fps: Dict[int, str]
) -> List[Dict]:
    """Return the subset of remote tickets whose fingerprint differs from
    (or is missing in) the cache."""
    need = []
    for t in remote_tickets:
        tid = t["id"]
        if cached_fps.get(tid) != compute_fingerprint(t):
            need.append(t)
    return need


def scrape_all_closed(
    client: TrengoClient,
    conn,
    progress_cb: Optional[ProgressCb] = None,
    max_workers: int = 5,
) -> Dict:
    """Fetch every closed ticket Trengo still retains, cache any that are
    new or changed, and return a stats dict.

    Stats keys:
        total_remote:      number of closed tickets Trengo returned
        new_or_updated:    number we actually wrote to the cache
        skipped_unchanged: number we skipped because fingerprint matched
    """
    remote = client.get_all_closed_tickets()
    cached_fps = get_all_ticket_fingerprints(conn)

    to_fetch = _tickets_needing_fetch(remote, cached_fps)
    total = len(to_fetch)

    if progress_cb:
        progress_cb(0, total)

    if total == 0:
        return {
            "total_remote": len(remote),
            "new_or_updated": 0,
            "skipped_unchanged": len(remote),
            "errors": 0,
        }

    def _fetch(ticket):
        return ticket, client.get_ticket_messages(ticket["id"])

    done = 0
    errors = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch, t): t for t in to_fetch}
        for fut in as_completed(futures):
            try:
                ticket, messages = fut.result()
                # Sequential DB writes — sqlite3 default connection is not
                # thread-safe for writes, and writes are fast enough.
                upsert_ticket(conn, ticket)
                upsert_messages(conn, ticket["id"], messages)
                done += 1
            except Exception as exc:
                print(f"  fout bij ticket {futures[fut]['id']}: {exc}")
                errors += 1
            if progress_cb:
                progress_cb(done, total)

    return {
        "total_remote": len(remote),
        "new_or_updated": done,
        "skipped_unchanged": len(remote) - done,
        "errors": errors,
    }


def main():
    client = TrengoClient()
    conn = init_db()

    def _print_progress(done, total):
        if total and (done % 25 == 0 or done == total):
            print(f"  {done}/{total} tickets verwerkt...")

    print("Ophalen gesloten tickets van Trengo...")
    stats = scrape_all_closed(client, conn, progress_cb=_print_progress)
    print("\nKlaar!")
    print(f"  {stats['total_remote']} tickets bij Trengo")
    print(f"  {stats['new_or_updated']} nieuw of bijgewerkt in cache")
    print(f"  {stats['skipped_unchanged']} ongewijzigd overgeslagen")


if __name__ == "__main__":
    main()

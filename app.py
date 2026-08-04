import json
import os
import shutil
import tempfile
import threading
from datetime import datetime, timezone, timedelta

from flask import Flask, render_template, jsonify, request
from trengo_client import TrengoClient, parse_datetime
from apscheduler.schedulers.background import BackgroundScheduler
from autoclose import run_autoclose, get_last_result
from label_suggester import (
    scan_for_suggestions, get_suggestion_queue, get_scan_progress, ignore_suggestion,
    accept_suggestion, reject_suggestion, get_tagger_stats,
    refresh_customer_cache, get_customer_overview,
)

app = Flask(__name__)

HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'history.json')

# Spike/dip detection thresholds.
# A point is considered anomalous when it deviates from the local median by
# MORE than both the percentage threshold AND the absolute threshold.
_SPIKE_PCT   = 0.20   # 20 % relative deviation
_SPIKE_ABS   = 15     # 15 tickets absolute deviation

# Closed-ticket cache (refreshed every 30 minutes)
_closed_cache = {"data": None, "fetched_at": None}
_CLOSED_TTL = timedelta(minutes=30)
_closed_lock = threading.Lock()

# History retention: one snapshot per scheduler tick (5 min) -> ~34 days.
_MAX_HISTORY = 10000

# Dashboard cache. The scheduler is the single source that fetches Trengo and
# writes history; clients read this cache instead of driving their own fetch.
_dashboard_cache = {"data": None, "fetched_at": None}

# Serialize refreshes so overlapping callers (scheduler, manual refresh,
# cold-start warm) share one Trengo scrape instead of stacking parallel scrapes.
_refresh_lock = threading.Lock()

# Serialize history read-modify-write so overlapping writers can't corrupt it.
_history_lock = threading.Lock()


def _median(values):
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return (s[mid - 1] + s[mid]) / 2 if n % 2 == 0 else s[mid]


def _is_spike(value, reference_values):
    """Return True if *value* looks like a spike/dip versus *reference_values*."""
    if len(reference_values) < 2:
        return False
    med = _median(reference_values)
    if med == 0:
        return False
    deviation = abs(value - med)
    return deviation > _SPIKE_ABS and (deviation / med) > _SPIKE_PCT


def _filter_spikes(history, window=4):
    """Return history with obvious spike/dip points removed.

    For each entry the median of up to *window* preceding and *window*
    following entries (excluding the entry itself) is used as reference.
    """
    if len(history) < 3:
        return history
    result = []
    for i, entry in enumerate(history):
        start = max(0, i - window)
        end   = min(len(history), i + window + 1)
        neighbors = [history[j]['total'] for j in range(start, end) if j != i]
        if not _is_spike(entry['total'], neighbors):
            result.append(entry)
    return result


def _load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("history file is not a list")
        return data
    except Exception:
        # Corrupt/unreadable: set it aside for inspection instead of silently
        # returning [] and letting the next write clobber real data.
        try:
            os.replace(HISTORY_FILE, HISTORY_FILE + '.corrupt')
        except OSError:
            pass
        return []


def _maybe_backup():
    """Keep a once-a-day backup so a single bad write can never cost everything."""
    backup = HISTORY_FILE + '.bak'
    try:
        stale = (not os.path.exists(backup)
                 or datetime.now().timestamp() - os.path.getmtime(backup) > 86400)
        if stale:
            shutil.copy2(HISTORY_FILE, backup)
    except OSError:
        pass


def _atomic_write_history(history):
    """Write via a temp file + os.replace so a concurrent reader never sees a
    half-written or truncated file (the root cause of the history-wipe bug)."""
    directory = os.path.dirname(HISTORY_FILE)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix='.history-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(history, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, HISTORY_FILE)  # atomic
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    _maybe_backup()


def _save_snapshot(open_count, assigned_count, closed_count=None):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with _history_lock:
        history = _load_history()
        new_total = open_count + assigned_count

        # Skip snapshot when it looks like an API glitch (sudden spike or dip).
        if len(history) >= 3:
            recent_totals = [h['total'] for h in history[-5:]]
            if _is_spike(new_total, recent_totals):
                return  # Discard anomalous data point

        history.append({
            "ts":       datetime.now().isoformat(timespec='seconds'),
            "open":     open_count,
            "assigned": assigned_count,
            "total":    new_total,
            "closed":   closed_count,
        })
        if len(history) > _MAX_HISTORY:
            history = history[-_MAX_HISTORY:]
        _atomic_write_history(history)


@app.route("/")
def index():
    return render_template("index.html")


def _do_refresh():
    """Fetch live data, record one history snapshot, and cache the result.
    The single writer of history."""
    client = TrengoClient()
    data = client.get_dashboard_data()
    # Stamp the snapshot with closed_today from the separately-warmed closed
    # cache (a cheap read; don't trigger a closed scrape from the dashboard tick).
    cached_closed = _closed_cache['data']
    closed_today = cached_closed.get('closed_today') if cached_closed else None
    _save_snapshot(data['summary']['new'], data['summary']['assigned'], closed_today)
    _dashboard_cache['data'] = data
    _dashboard_cache['fetched_at'] = datetime.now(timezone.utc)
    return data


def _refresh_dashboard(force=False):
    """Return dashboard data, hitting Trengo only when needed.

    Warm cache without a forced refresh returns instantly and lock-free, so
    ordinary reads never block on an in-flight scrape. A cold or forced call
    takes the lock and double-checks, so concurrent cold callers (startup warm
    + first viewers) share one scrape instead of each launching their own.
    """
    if not force and _dashboard_cache['data'] is not None:
        return _dashboard_cache['data']
    with _refresh_lock:
        if not force and _dashboard_cache['data'] is not None:
            return _dashboard_cache['data']
        return _do_refresh()


def _scheduled_dashboard_refresh():
    _refresh_dashboard(force=True)


def _warm_caches():
    """Populate the dashboard and closed caches in the background at startup so
    the first page view after a restart doesn't block on a full Trengo scrape.
    Sequential (not parallel) to stay gentle on Trengo's rate limit."""
    for warm in (_refresh_dashboard, _get_closed_data):
        try:
            warm()
        except Exception:
            pass  # the scheduler will retry on its interval


@app.route("/api/dashboard")
def dashboard():
    try:
        data = _refresh_dashboard(force=request.args.get('refresh') == '1')
        return jsonify(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": f"Onverwachte fout: {str(e)}"}), 500


@app.route("/api/history")
def history():
    return jsonify(_filter_spikes(_load_history()))


def _closed_is_fresh():
    return (_closed_cache["data"] is not None
            and _closed_cache["fetched_at"] is not None
            and datetime.now(timezone.utc) - _closed_cache["fetched_at"] < _CLOSED_TTL)


def _get_closed_data(force=False):
    """Return closed-ticket stats from cache, scraping Trengo only when needed.

    Fresh cache + no force returns instantly and lock-free. A cold or forced
    call takes the lock and double-checks, so concurrent cold callers (startup
    warm, scheduler, first viewers) share one heavy scrape instead of stacking.
    """
    if not force and _closed_is_fresh():
        return _closed_cache["data"]
    with _closed_lock:
        if not force and _closed_is_fresh():
            return _closed_cache["data"]
        return _compute_closed_data()


def _compute_closed_data():
    """Fetch closed tickets and compute stats. The single heavy Trengo scrape."""
    now = datetime.now(timezone.utc)
    client = TrengoClient()
    closed_tickets = client.get_closed_tickets()

    now_utc = datetime.now(timezone.utc)
    today_local = datetime.now().date()
    week_ago = now_utc - timedelta(days=7)
    month_ago = now_utc - timedelta(days=30)

    closed_today = 0
    closed_week = 0
    closed_month = 0
    closed_total = len(closed_tickets)
    created_today_closed = 0
    daily_counts = {}

    for ticket in closed_tickets:
        closed_at = parse_datetime(ticket.get("closed_at"))
        if not closed_at:
            continue

        closed_local_date = closed_at.astimezone().date()
        date_key = closed_local_date.isoformat()
        daily_counts[date_key] = daily_counts.get(date_key, 0) + 1

        if closed_local_date == today_local:
            closed_today += 1
            # Vandaag aangemaakt én gesloten: staat niet meer in de open lijst,
            # dus summary.new_today telt deze niet mee.
            created_at = parse_datetime(ticket.get("created_at"))
            if created_at and created_at.astimezone().date() == today_local:
                created_today_closed += 1
        if closed_at >= week_ago:
            closed_week += 1
        if closed_at >= month_ago:
            closed_month += 1

    result = {
        "closed_today": closed_today,
        "closed_week": closed_week,
        "closed_month": closed_month,
        "closed_90d": closed_total,
        "created_today_closed": created_today_closed,
        "daily_counts": daily_counts,
        "fetched_at": now.isoformat(),
    }
    _closed_cache["data"] = result
    _closed_cache["fetched_at"] = now
    return result


def _scheduled_closed_refresh():
    _get_closed_data(force=True)


@app.route("/api/closed")
def closed():
    try:
        return jsonify(_get_closed_data())
    except ValueError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": f"Onverwachte fout: {str(e)}"}), 500


# ── Autoclose scheduler ─────────────────────────────
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(run_autoclose, "interval", minutes=30, id="ruijie_autoclose")
# Server-side dashboard poll: one fetch + one history snapshot per tick,
# independent of how many browsers are open. coalesce/max_instances stop a slow
# Trengo scrape from stacking up.
scheduler.add_job(
    _scheduled_dashboard_refresh, "interval", minutes=5, id="dashboard_refresh",
    max_instances=1, coalesce=True,
)
# Refresh the closed cache well before its 30-min TTL expires, so a viewer
# never lands on an expired cache and triggers a synchronous heavy scrape.
scheduler.add_job(
    _scheduled_closed_refresh, "interval", minutes=15, id="closed_refresh",
    max_instances=1, coalesce=True,
)
scheduler.start()

# ── Label Suggester scheduler ────────────────────────
if os.getenv("TAGGER_ENABLED", "false").lower() in ("true", "1", "yes"):
    _tagger_interval = int(os.getenv("TAGGER_SCAN_INTERVAL", "15"))
    scheduler.add_job(
        scan_for_suggestions, "interval",
        minutes=_tagger_interval, id="label_suggester_scan",
    )
    _cache_refresh_hours = int(os.getenv("TAGGER_CACHE_REFRESH_HOURS", "6"))
    scheduler.add_job(
        refresh_customer_cache, "interval",
        hours=_cache_refresh_hours, id="label_cache_refresh",
    )


@app.route("/api/autoclose")
def autoclose_status():
    """Return the last autoclose run result."""
    try:
        return jsonify(get_last_result())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/autoclose/run", methods=["POST"])
def autoclose_trigger():
    """Manually trigger an autoclose run."""
    try:
        result = run_autoclose()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Label Suggester routes ───────────────────────────

@app.route("/tagger")
def tagger():
    return render_template("tagger.html")


@app.route("/api/tagger/queue")
def tagger_queue():
    """Return the current suggestion queue + stats."""
    try:
        return jsonify({
            "queue": get_suggestion_queue(),
            "stats": get_tagger_stats(),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/tagger/accept", methods=["POST"])
def tagger_accept():
    """Accept a label suggestion."""
    try:
        data = request.get_json()
        ticket_id = data.get("ticket_id")
        label_name = data.get("label_name")
        if not ticket_id or not label_name:
            return jsonify({"error": "ticket_id en label_name zijn verplicht"}), 400
        result = accept_suggestion(ticket_id=ticket_id, label_name=label_name)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/tagger/reject", methods=["POST"])
def tagger_reject():
    """Reject a label suggestion."""
    try:
        data = request.get_json()
        ticket_id = data.get("ticket_id")
        label_name = data.get("label_name")
        if not ticket_id or not label_name:
            return jsonify({"error": "ticket_id en label_name zijn verplicht"}), 400
        result = reject_suggestion(ticket_id=ticket_id, label_name=label_name)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/tagger/ignore", methods=["POST"])
def tagger_ignore():
    """Ignore a suggestion (no feedback logged)."""
    try:
        data = request.get_json()
        ticket_id = data.get("ticket_id")
        label_name = data.get("label_name")
        if not ticket_id or not label_name:
            return jsonify({"error": "ticket_id en label_name zijn verplicht"}), 400
        result = ignore_suggestion(ticket_id=ticket_id, label_name=label_name)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


import threading

_scan_state = {"running": False, "started_at": None, "result": None}
_scan_lock = threading.Lock()


def _run_scan_background():
    try:
        result = scan_for_suggestions()
        with _scan_lock:
            _scan_state["result"] = result
    except Exception as e:
        with _scan_lock:
            _scan_state["result"] = {"error": str(e)}
    finally:
        with _scan_lock:
            _scan_state["running"] = False


@app.route("/api/tagger/scan", methods=["POST"])
def tagger_scan():
    """Manually trigger a suggestion scan (runs in background)."""
    with _scan_lock:
        if _scan_state["running"]:
            return jsonify({"status": "already_running", "started_at": _scan_state["started_at"]})
        _scan_state["running"] = True
        _scan_state["started_at"] = datetime.now(timezone.utc).isoformat()
        _scan_state["result"] = None

    thread = threading.Thread(target=_run_scan_background, daemon=True)
    thread.start()

    return jsonify({"status": "started", "started_at": _scan_state["started_at"]})


@app.route("/api/tagger/scan/status")
def tagger_scan_status():
    """Return current scan status (running/idle + progress + last result)."""
    with _scan_lock:
        return jsonify({
            "running": _scan_state["running"],
            "started_at": _scan_state["started_at"],
            "result": _scan_state["result"],
            "progress": get_scan_progress(),
        })


@app.route("/customers")
def customers():
    return render_template("customers.html")


@app.route("/api/tagger/customers")
def tagger_customers():
    """Return customer label overview data."""
    try:
        return jsonify({"customers": get_customer_overview()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    threading.Thread(target=_warm_caches, daemon=True).start()
    app.run(debug=False, host="0.0.0.0", port=5000)

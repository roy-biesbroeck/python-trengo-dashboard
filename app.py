import json
import os
from datetime import datetime

from flask import Flask, render_template, jsonify
from trengo_client import TrengoClient

app = Flask(__name__)

HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'history.json')

# Spike/dip detection thresholds.
# A point is considered anomalous when it deviates from the local median by
# MORE than both the percentage threshold AND the absolute threshold.
_SPIKE_PCT   = 0.20   # 20 % relative deviation
_SPIKE_ABS   = 15     # 15 tickets absolute deviation


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
            return json.load(f)
    except Exception:
        return []


def _save_snapshot(open_count, assigned_count):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
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
    })
    # Keep last 1000 entries
    if len(history) > 1000:
        history = history[-1000:]
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/dashboard")
def dashboard():
    try:
        client = TrengoClient()
        data = client.get_dashboard_data()
        _save_snapshot(data['summary']['new'], data['summary']['assigned'])
        return jsonify(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": f"Onverwachte fout: {str(e)}"}), 500


@app.route("/api/history")
def history():
    return jsonify(_filter_spikes(_load_history()))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

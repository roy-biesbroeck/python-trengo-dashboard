const queueEl = document.getElementById('queue');
const loadingEl = document.getElementById('loading');
const emptyEl = document.getElementById('empty-state');
const statTotalEl = document.getElementById('stat-total');
const statRateEl = document.getElementById('stat-rate');
const btnScan = document.getElementById('btn-scan');

async function loadQueue() {
    try {
        const resp = await fetch('/api/tagger/queue');
        const data = await resp.json();
        updateStats(data.stats);
        renderQueue(data.queue);
    } catch (err) {
        queueEl.innerHTML = '<div class="loading">Fout bij laden.</div>';
        console.error('Queue load error:', err);
    }
}

function updateStats(stats) {
    if (!stats) return;
    statTotalEl.textContent = stats.total_decisions + ' beslissingen';
    statRateEl.textContent = stats.acceptance_rate + '% geaccepteerd';
}

function renderQueue(queue) {
    loadingEl.style.display = 'none';
    if (!queue || queue.length === 0) {
        queueEl.innerHTML = '';
        emptyEl.style.display = 'block';
        return;
    }
    emptyEl.style.display = 'none';
    queueEl.innerHTML = queue.map(function(ticket) {
        var trengoUrl = 'https://app.trengo.com/tickets/' + ticket.ticket_id;
        return '<div class="ticket-card" id="ticket-' + ticket.ticket_id + '">' +
            '<div class="ticket-header"><div>' +
            '<span class="ticket-id">#' + ticket.ticket_id + '</span>' +
            '<div class="ticket-subject">' + escapeHtml(ticket.ticket_subject) + '</div>' +
            '<div class="ticket-customer">' + (function() {
                var customerLine = escapeHtml(ticket.customer_name);
                if (ticket.internal_creator) {
                    customerLine = escapeHtml(ticket.customer_name) +
                        ' <span class="internal-badge">via ' + escapeHtml(ticket.internal_creator) + '</span>';
                }
                return customerLine;
            })() + '</div>' +
            '</div>' +
            '<a class="btn btn-open" href="' + trengoUrl + '" target="_blank" rel="noopener">Open in Trengo →</a>' +
            '</div>' +
            (ticket.message_preview ? '<div class="ticket-preview">' + escapeHtml(ticket.message_preview) + '</div>' : '') +
            '<div class="suggestions">' +
            ticket.suggestions.map(function(s) { return renderSuggestion(ticket.ticket_id, s); }).join('') +
            '</div></div>';
    }).join('');
}

function renderSuggestion(ticketId, s) {
    var confClass = s.confidence >= 90 ? 'high' : s.confidence >= 75 ? 'medium' : '';
    return '<div class="suggestion-row" id="suggestion-' + ticketId + '-' + slugify(s.label) + '">' +
        '<div class="suggestion-info">' +
        '<span class="suggestion-label">' + escapeHtml(s.label) + '</span>' +
        '<span class="suggestion-confidence ' + confClass + '">' + s.confidence + '%</span>' +
        '<span class="suggestion-reason">' + escapeHtml(s.reason) + '</span>' +
        '<span class="suggestion-source">' + (s.source || '') + '</span>' +
        '</div>' +
        '<div class="suggestion-actions">' +
        '<button class="btn btn-accept" onclick="acceptLabel(' + ticketId + ', \'' + escapeJs(s.label) + '\')">Accepteer</button>' +
        '<button class="btn btn-reject" onclick="rejectLabel(' + ticketId + ', \'' + escapeJs(s.label) + '\')">Afwijzen</button>' +
        '</div></div>';
}

async function acceptLabel(ticketId, labelName) {
    var row = document.getElementById('suggestion-' + ticketId + '-' + slugify(labelName));
    if (row) disableButtons(row);
    try {
        var resp = await fetch('/api/tagger/accept', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ticket_id: ticketId, label_name: labelName }),
        });
        var data = await resp.json();
        if (data.success) {
            if (row) row.style.background = '#f0fdf4';
            setTimeout(loadQueue, 500);
        } else {
            alert('Fout: ' + (data.error || 'Onbekende fout'));
            if (row) enableButtons(row);
        }
    } catch (err) {
        alert('Netwerkfout bij accepteren');
        if (row) enableButtons(row);
    }
}

async function rejectLabel(ticketId, labelName) {
    var row = document.getElementById('suggestion-' + ticketId + '-' + slugify(labelName));
    if (row) disableButtons(row);
    try {
        await fetch('/api/tagger/reject', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ticket_id: ticketId, label_name: labelName }),
        });
        if (row) row.style.background = '#fef2f2';
        setTimeout(loadQueue, 500);
    } catch (err) {
        alert('Netwerkfout bij afwijzen');
        if (row) enableButtons(row);
    }
}

var scanPollInterval = null;

async function triggerScan() {
    btnScan.disabled = true;
    btnScan.textContent = 'Scannen...';

    // Show progress banner
    showScanBanner('Scan gestart — tickets ophalen van Trengo (kan even duren bij rate limits)...');

    try {
        await fetch('/api/tagger/scan', { method: 'POST' });

        // Poll status every 3 seconds
        scanPollInterval = setInterval(checkScanStatus, 3000);
        loadQueue(); // immediate refresh
    } catch (err) {
        hideScanBanner();
        alert('Fout bij starten scan');
        btnScan.disabled = false;
        btnScan.textContent = 'Scan Nu';
    }
}

async function checkScanStatus() {
    try {
        var resp = await fetch('/api/tagger/scan/status');
        var status = await resp.json();

        // Refresh queue while scanning so new suggestions appear live
        loadQueue();

        if (!status.running) {
            // Scan finished
            clearInterval(scanPollInterval);
            scanPollInterval = null;
            btnScan.disabled = false;
            btnScan.textContent = 'Scan Nu';

            var result = status.result || {};
            if (result.error) {
                showScanBanner('Scan fout: ' + result.error, 'error');
            } else {
                showScanBanner(
                    'Scan klaar: ' + (result.scanned || 0) + ' verwerkt, ' +
                    (result.suggested || 0) + ' nieuwe suggesties, ' +
                    (result.skipped_has_labels || 0) + ' al gelabeld',
                    'success'
                );
            }
            setTimeout(hideScanBanner, 6000);
        }
    } catch (err) {
        console.error('Status check failed', err);
    }
}

function showScanBanner(text, type) {
    var container = document.getElementById('scan-banner-container');
    container.innerHTML = '';
    var banner = document.createElement('div');
    banner.id = 'scan-banner';
    banner.className = 'scan-result' + (type === 'error' ? ' scan-result-error' : '');
    banner.textContent = text;
    container.appendChild(banner);
}

function hideScanBanner() {
    var container = document.getElementById('scan-banner-container');
    if (container) container.innerHTML = '';
}

function escapeHtml(str) {
    if (!str) return '';
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function escapeJs(str) {
    return str.replace(/'/g, "\\'").replace(/"/g, '\\"');
}

function slugify(str) {
    return str.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
}

function disableButtons(row) {
    row.querySelectorAll('.btn').forEach(function(b) { b.disabled = true; });
}

function enableButtons(row) {
    row.querySelectorAll('.btn').forEach(function(b) { b.disabled = false; });
}

// Resume scan polling if a scan is already running
async function resumeScanPollIfRunning() {
    try {
        var resp = await fetch('/api/tagger/scan/status');
        var status = await resp.json();
        if (status.running) {
            btnScan.disabled = true;
            btnScan.textContent = 'Scannen...';
            showScanBanner('Scan loopt al — wachten op resultaten...');
            scanPollInterval = setInterval(checkScanStatus, 3000);
        }
    } catch (err) {}
}

loadQueue();
resumeScanPollIfRunning();
setInterval(loadQueue, 60000);

var allCustomers = [];
var listEl = document.getElementById('customer-list');
var searchEl = document.getElementById('search');
var summaryEl = document.getElementById('summary-bar');

var ROUTE_LABELS = [
    'Route Hulst', 'Route Kust', 'Route Overkant',
    'Route Kanaalzone', 'Route BE', 'Route NL'
];

async function loadCustomers() {
    try {
        var resp = await fetch('/api/tagger/customers');
        var data = await resp.json();
        allCustomers = data.customers || [];
        renderSummary();
        renderCustomers(allCustomers);
    } catch (err) {
        listEl.innerHTML = '<div class="loading">Fout bij laden.</div>';
    }
}

function renderSummary() {
    var total = allCustomers.length;
    var withRoutes = allCustomers.filter(function(c) {
        return c.top_labels.some(function(l) { return ROUTE_LABELS.indexOf(l.name) >= 0; });
    }).length;
    var totalTickets = allCustomers.reduce(function(sum, c) { return sum + c.ticket_count; }, 0);
    summaryEl.innerHTML = '<span>' + total + ' klanten</span><span>|</span><span>' + totalTickets + ' tickets verwerkt</span><span>|</span><span>' + withRoutes + ' met route-labels</span>';
}

function renderCustomers(customers) {
    if (!customers.length) {
        listEl.innerHTML = '<div class="loading">Geen klanten gevonden.</div>';
        return;
    }
    listEl.innerHTML = customers.map(function(c) {
        return '<div class="customer-card"><div class="customer-header">' +
            '<span class="customer-id">Klant #' + c.contact_id + '</span>' +
            '<span class="customer-ticket-count">' + c.ticket_count + ' tickets</span>' +
            '</div><div class="label-pills">' +
            c.top_labels.map(function(l) {
                var isRoute = ROUTE_LABELS.indexOf(l.name) >= 0;
                return '<span class="label-pill ' + (isRoute ? 'route' : '') + '">' +
                    escapeHtml(l.name) + '<span class="count">' + l.count + 'x</span></span>';
            }).join('') +
            (c.total_labels > 5 ? '<span class="label-pill">+' + (c.total_labels - 5) + ' meer</span>' : '') +
            '</div></div>';
    }).join('');
}

function filterCustomers() {
    var query = searchEl.value.toLowerCase().trim();
    if (!query) {
        renderCustomers(allCustomers);
        return;
    }
    var filtered = allCustomers.filter(function(c) {
        if (String(c.contact_id).indexOf(query) >= 0) return true;
        return c.top_labels.some(function(l) { return l.name.toLowerCase().indexOf(query) >= 0; });
    });
    renderCustomers(filtered);
}

function escapeHtml(str) {
    if (!str) return '';
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

loadCustomers();

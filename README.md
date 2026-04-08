# Trengo Dashboard

Een lokale Flask-webapplicatie die live ticketstatistieken ophaalt uit de Trengo API en weergeeft in een overzichtelijk dashboard.

## Functies

- **Samenvatting**: totaal aantal openstaande tickets, opgesplitst in _nieuw_ (OPEN) en _toegewezen_ (ASSIGNED)
- **Per team**: ticketverdeling per team, gesorteerd op volume
- **Per agent**: aantal toegewezen tickets per medewerker
- **Leeftijdsverdeling**: tickets ingedeeld naar hoe oud ze zijn (vandaag, < 1 week, 1–2 weken, enz.)
- **Historiegrafiek**: tijdlijn van het totale aantal openstaande tickets (opgeslagen in `data/history.json`)
- **Anomaliefiltering**: automatische detectie en weggooien van API-uitschieters in zowel de opslag als de grafiek

## Vereisten

- Python 3.10+
- Een Trengo API-token ([Trengo → Instellingen → API](https://app.trengo.com/settings/api))

## Installatie

### Windows

```bat
copy .env.example .env
# Vul TRENGO_API_TOKEN in in .env
run.bat
```

`run.bat` maakt automatisch een virtuele omgeving aan en installeert de afhankelijkheden.

### Linux / macOS

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Vul TRENGO_API_TOKEN in in .env
python app.py
```

### Android (Termux)

Het script `start-dashboard.sh` is bedoeld voor gebruik via Termux. Het start de Flask-server en opent het dashboard in de browser:

```bash
bash start-dashboard.sh
```

## Configuratie

Maak een `.env`-bestand aan in de projectmap (kopieer `.env.example`):

```env
TRENGO_API_TOKEN=jouw_token_hier
```

## Gebruik

Na het starten is het dashboard bereikbaar op:

```
http://localhost:5000
```

De pagina haalt automatisch verse data op via `/api/dashboard`. Elke succesvolle opvraging wordt als snapshot opgeslagen in `data/history.json` (maximaal 1000 entries).

## API-endpoints

| Endpoint        | Omschrijving                                      |
|-----------------|---------------------------------------------------|
| `GET /`         | Dashboard-frontend                                |
| `GET /api/dashboard` | Live Trengo-data als JSON                   |
| `GET /api/history`   | Historische snapshots (gefilterd op uitschieters) |

## Projectstructuur

```
trengo-dashboard/
├── app.py              # Flask-applicatie en logica
├── trengo_client.py    # Trengo API-client
├── templates/          # HTML-template(s)
├── data/
│   └── history.json    # Automatisch gegenereerde geschiedenis
├── requirements.txt
├── run.bat             # Windows-startscript
└── start-dashboard.sh  # Termux-startscript
```

## Afhankelijkheden

- [Flask](https://flask.palletsprojects.com/) >= 3.0
- [requests](https://docs.python-requests.org/) >= 2.31
- [python-dotenv](https://pypi.org/project/python-dotenv/) >= 1.0

## Ticket cache

Closed Trengo tickets and their messages are cached in
`data/ticket_analysis.db` (SQLite). The cache powers historical features
(`harvest_history.py`, and future root-cause insights) without repeatedly
hitting Trengo's rate-limited API.

### Populating the cache

```bash
python scrape_tickets.py
```

Subsequent runs only fetch tickets whose `closed_at` or message count
changed since the last scrape. Running a full scrape twice is safe and
near-free on the second run.

### Schema overview

- `tickets` — one row per closed Trengo ticket. `raw_payload` stores the
  full Trengo JSON verbatim; indexed columns (`contact_id`, `closed_at`,
  `message_count`) are extracted for fast lookups.
- `messages` — one row per message, `body_text` pre-stripped of HTML for
  downstream text processing. `raw_payload` preserves the full Trengo
  message JSON.

### Consuming the cache from Python

```python
from ticket_cache import init_db, get_customer_tickets, get_messages

conn = init_db()
for ticket in get_customer_tickets(conn, contact_id=10):
    print(ticket["subject"])
    for msg in get_messages(conn, ticket["ticket_id"]):
        print("  ", msg["body_text"])
```

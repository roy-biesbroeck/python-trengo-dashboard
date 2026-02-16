import os
import time
import requests
from typing import List, Dict
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()


class TrengoClient:
    def __init__(self):
        self.api_token = os.getenv("TRENGO_API_TOKEN")
        if not self.api_token:
            raise ValueError("TRENGO_API_TOKEN niet gevonden in .env bestand")
        self.base_url = "https://app.trengo.com/api/v2"
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    def _get_paginated(self, endpoint: str, params: dict = None) -> List[Dict]:
        """Haal alle pagina's op van een endpoint."""
        results = []
        page = 1
        base_params = params.copy() if params else {}

        while True:
            base_params["page"] = page
            base_params["limit"] = 100

            try:
                response = requests.get(
                    f"{self.base_url}/{endpoint}",
                    headers=self.headers,
                    params=base_params,
                    timeout=15,
                )
                response.raise_for_status()
                data = response.json()

                batch = data.get("data", []) if isinstance(data, dict) else data
                if not batch:
                    break

                results.extend(batch)

                # Controleer of er een volgende pagina is
                links = data.get("links", {}) if isinstance(data, dict) else {}
                if not links.get("next"):
                    break

                page += 1
                if page > 200:  # Veiligheidsgrens
                    break

            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 429:
                    print(f"Rate limit bereikt, 2 seconden wachten...")
                    time.sleep(2)
                    continue
                print(f"HTTP fout bij {endpoint} (pagina {page}): {e}")
                break
            except requests.exceptions.RequestException as e:
                print(f"Verzoekfout bij {endpoint} (pagina {page}): {e}")
                break

        return results

    def get_teams(self) -> List[Dict]:
        """Haal alle teams op."""
        return self._get_paginated("teams")

    def get_users(self) -> List[Dict]:
        """Haal alle gebruikers/agents op."""
        return self._get_paginated("users")

    def get_tickets(self, status: str) -> List[Dict]:
        """Haal alle tickets op met een bepaalde status."""
        return self._get_paginated("tickets", {"status": status})

    def get_dashboard_data(self) -> Dict:
        """Compileer alle dashboard statistieken."""
        # Teams en gebruikers ophalen
        teams = self.get_teams()
        users = self.get_users()

        team_map = {
            t["id"]: t.get("name", "Onbekend")
            for t in teams
            if isinstance(t, dict) and "id" in t
        }
        user_map = {
            u["id"]: u.get("name", "Onbekend")
            for u in users
            if isinstance(u, dict) and "id" in u
        }

        # Tickets ophalen (OPEN = nieuw/niet-toegewezen, ASSIGNED = toegewezen)
        open_tickets = self.get_tickets("OPEN")
        assigned_tickets = self.get_tickets("ASSIGNED")
        all_tickets = open_tickets + assigned_tickets

        # Team statistieken initialiseren
        team_stats: Dict[int, Dict] = {
            tid: {"id": tid, "name": name, "total": 0, "new": 0, "assigned": 0}
            for tid, name in team_map.items()
        }
        no_team = {"id": None, "name": "Geen team", "total": 0, "new": 0, "assigned": 0}

        # Gebruiker statistieken initialiseren
        user_stats: Dict[int, Dict] = {
            uid: {"id": uid, "name": name, "assigned": 0}
            for uid, name in user_map.items()
        }

        # Tickets tellen per team en gebruiker
        for ticket in all_tickets:
            if not isinstance(ticket, dict):
                continue

            ticket_status = ticket.get("status", "")
            is_new = ticket_status == "OPEN"
            is_assigned = ticket_status == "ASSIGNED"

            # Team tellen
            team_id = ticket.get("team_id")
            if team_id is None:
                team_obj = ticket.get("team") or ticket.get("assignedTeam")
                if isinstance(team_obj, dict):
                    team_id = team_obj.get("id")

            if team_id and team_id in team_stats:
                team_stats[team_id]["total"] += 1
                if is_new:
                    team_stats[team_id]["new"] += 1
                elif is_assigned:
                    team_stats[team_id]["assigned"] += 1
            else:
                no_team["total"] += 1
                if is_new:
                    no_team["new"] += 1
                elif is_assigned:
                    no_team["assigned"] += 1

            # Gebruiker tellen (alleen ASSIGNED tickets)
            if is_assigned:
                user_id = ticket.get("user_id")
                if user_id and user_id in user_stats:
                    user_stats[user_id]["assigned"] += 1

        # Teams sorteren op totaal (aflopend), alleen teams met tickets
        teams_list = sorted(
            [s for s in team_stats.values() if s["total"] > 0],
            key=lambda x: x["total"],
            reverse=True,
        )
        if no_team["total"] > 0:
            teams_list.append(no_team)

        # Gebruikers sorteren op assigned (aflopend), alleen gebruikers met tickets
        users_list = sorted(
            [s for s in user_stats.values() if s["assigned"] > 0],
            key=lambda x: x["assigned"],
            reverse=True,
        )

        # Ticket ouderdom berekenen
        age_counts = [0, 0, 0, 0, 0, 0]  # vandaag / week / 2wkn / mnd / 3mnd / ouder
        unknown_age = 0
        now_utc = datetime.now(timezone.utc)
        today_local = datetime.now().date()  # kalenderdag in lokale tijd

        for ticket in all_tickets:
            if not isinstance(ticket, dict):
                continue
            created_raw = ticket.get("created_at")
            if not created_raw:
                unknown_age += 1
                continue
            try:
                created_str = str(created_raw).replace("Z", "+00:00")
                created_at = datetime.fromisoformat(created_str)
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                # "Vandaag" = zelfde kalenderdag in lokale tijd
                created_local_date = created_at.astimezone().date()
                age_days = (now_utc - created_at).total_seconds() / 86400
                if created_local_date == today_local:
                    age_counts[0] += 1
                elif age_days < 7:
                    age_counts[1] += 1
                elif age_days < 14:
                    age_counts[2] += 1
                elif age_days < 30:
                    age_counts[3] += 1
                elif age_days < 90:
                    age_counts[4] += 1
                else:
                    age_counts[5] += 1
            except (ValueError, TypeError):
                unknown_age += 1

        age_buckets = [
            {"key": "today",    "label": "Vandaag",      "sublabel": "Kalenderdag",    "count": age_counts[0]},
            {"key": "week",     "label": "< 1 week",     "sublabel": "1–6 dagen",      "count": age_counts[1]},
            {"key": "twoweeks", "label": "1–2 weken",    "sublabel": "7–14 dagen",     "count": age_counts[2]},
            {"key": "month",    "label": "2 wkn–1 mnd",  "sublabel": "14–30 dagen",    "count": age_counts[3]},
            {"key": "quarter",  "label": "1–3 maanden",  "sublabel": "30–90 dagen",    "count": age_counts[4]},
            {"key": "older",    "label": "> 3 maanden",  "sublabel": "90+ dagen",      "count": age_counts[5]},
        ]

        return {
            "summary": {
                "total": len(all_tickets),
                "new": len(open_tickets),
                "assigned": len(assigned_tickets),
            },
            "teams": teams_list,
            "users": users_list,
            "age_buckets": age_buckets,
            "last_updated": datetime.now().isoformat(),
        }

"""Label configuration for the AI label suggester.

Central registry of all Trengo labels with IDs, descriptions, and
categorization. Sourced from label-definitions.md.
"""

LABELS = {
    "Bespreken": {
        "id": 1680401,
        "description": "Ticket moet intern besproken worden met team/leidinggevende",
    },
    "Urgent": {
        "id": 1578199,
        "description": "Hoge prioriteit, moet zo snel mogelijk opgepakt worden",
    },
    "Reparatie @BA": {
        "id": 1645587,
        "description": "Apparaat moet gerepareerd worden op kantoor (klant brengt langs of stuurt op)",
    },
    "Reparatie @klant": {
        "id": 1624094,
        "description": "Apparaat moet ter plekke bij de klant gerepareerd worden (technicus gaat langs)",
    },
    "RMA": {
        "id": 1667038,
        "description": "Apparaat moet retour naar leverancier/fabrikant (Return Merchandise Authorization)",
    },
    "Route Hulst": {
        "id": 1666479,
        "description": "Klantbezoek in regio Hulst, vanaf Axel naar rechts in Zeeuws-Vlaanderen",
    },
    "Route Kust": {
        "id": 1578209,
        "description": "Klantbezoek in kustregio (Sluis, etc.), vanaf Biervliet naar links in Zeeuws-Vlaanderen",
    },
    "Route Overkant": {
        "id": 1623274,
        "description": "Klantbezoek overkant, alle locaties boven Zeeuws-Vlaanderen die in Zeeland vallen",
    },
    "Artikelaanpassingen": {
        "id": 1635464,
        "description": "Aanpassingen aan artikelen/producten in het systeem (prijzen, omschrijvingen, etc.)",
    },
    "Route Kanaalzone": {
        "id": 1578214,
        "description": "Klantbezoek in de Kanaalzone, tussen Biervliet en Axel in Zeeuws-Vlaanderen",
    },
    "Aanmelden Klearly": {
        "id": 1728073,
        "description": "Klant moet aangemeld/geregistreerd worden bij Klearly",
    },
    "Aanmelden UMS": {
        "id": 1773871,
        "description": "Klant moet aangemeld/geregistreerd worden bij UMS",
    },
    "Autorun controle": {
        "id": 1734528,
        "description": "Autorun instellingen in de backoffice moeten nagekeken worden of deze goed staan of dat de autorun wel draait",
    },
    "Bespreken DEV": {
        "id": 1788585,
        "description": "Ticket moet besproken worden met het development team (technisch issue/feature request)",
    },
    "Bespreken toegewezen": {
        "id": 1798828,
        "description": "Legacy label (automatische regel, niet meer actief)",
    },
    "Bestelling": {
        "id": 1799081,
        "description": "Klant wil iets bestellen / er moet een bestelling geplaatst worden",
    },
    "Boekhoudkoppeling": {
        "id": 1817462,
        "description": "Boekhoudkoppeling moet ingesteld/geconfigureerd worden voor de klant",
    },
    "HeyTom / HeyEmma": {
        "id": 1642301,
        "description": "Ticket gaat over HeyTom of HeyEmma platform, support en onboarding",
    },
    "HeyTom Order": {
        "id": 1745017,
        "description": "Bestelling via HeyTom platform",
    },
    "HH - PAX": {
        "id": 1711066,
        "description": "Issue met PAX handheld betaalterminal",
    },
    "HH - PAY": {
        "id": 1746275,
        "description": "Issue met PAY handheld betaalterminal",
    },
    "Kassarollen": {
        "id": 1796676,
        "description": "Klant heeft kassarollen/bonrollen nodig (bestelling/levering)",
    },
    "Ligt klaar voor uitlevering": {
        "id": 1790946,
        "description": "Apparaat/bestelling is klaar en kan opgehaald/bezorgd worden",
    },
    "Nieuw": {
        "id": 1796957,
        "description": "Doel onduidelijk — niet gebruiken voor suggesties",
    },
    "Nog retour": {
        "id": 1740325,
        "description": "Er moet nog apparatuur teruggestuurd worden (door klant of naar leverancier)",
    },
    "Pay.nl": {
        "id": 1805687,
        "description": "Ticket gaat over Pay.nl betalingen/integratie",
    },
    "Potentiele klant": {
        "id": 1788204,
        "description": "Geen bestaande klant — lead/prospect die interesse toont",
    },
    "Route BE": {
        "id": 1692532,
        "description": "Klantbezoek in Belgie (niet specifieke regio)",
    },
    "Route Jos": {
        "id": 1649714,
        "description": "Toegewezen aan technicus Jos",
    },
    "Route Ludwig": {
        "id": 1650908,
        "description": "Toegewezen aan technicus Ludwig",
    },
    "Route Michael": {
        "id": 1649713,
        "description": "Toegewezen aan technicus Michael",
    },
    "Route NL": {
        "id": 1692539,
        "description": "Klantbezoek in Nederland (niet specifieke regio)",
    },
    "Route Ricardo": {
        "id": 1649707,
        "description": "Toegewezen aan technicus Ricardo",
    },
    "Route Roy": {
        "id": 1790933,
        "description": "Toegewezen aan technicus Roy",
    },
    "Route Ziggy": {
        "id": 1649712,
        "description": "Toegewezen aan technicus Ziggy",
    },
    "Support - Backoffice": {
        "id": 1807990,
        "description": "Supportvraag over backoffice software",
    },
    "Support - Handheld": {
        "id": 1807988,
        "description": "Supportvraag over handheld apparaat",
    },
    "Support - Kassa": {
        "id": 1807989,
        "description": "Supportvraag over kassasysteem/POS",
    },
    "Viva Wallet Problemen": {
        "id": 1667307,
        "description": "Problemen met Viva Wallet betaalterminal (storing, transactie mislukt, etc.)",
    },
    "Wacht op levering": {
        "id": 1792780,
        "description": "Wachten tot bestelling/apparatuur geleverd wordt",
    },
}

MANUAL_ONLY_LABELS = {
    "Route Jos",
    "Route Ludwig",
    "Route Michael",
    "Route Ricardo",
    "Route Roy",
    "Route Ziggy",
    "Ligt klaar voor uitlevering",
    "Wacht op levering",
    "Bespreken toegewezen",
    "Nieuw",
}

ROUTE_LABELS = {
    "Route Hulst",
    "Route Kust",
    "Route Overkant",
    "Route Kanaalzone",
    "Route BE",
    "Route NL",
}

SUGGESTABLE_LABELS = {
    name: info for name, info in LABELS.items()
    if name not in MANUAL_ONLY_LABELS
}


def get_label_id(name: str):
    """Return the Trengo label ID for a given label name, or None."""
    info = LABELS.get(name)
    return info["id"] if info else None


def get_label_name(label_id: int):
    """Return the label name for a given Trengo label ID, or None."""
    for name, info in LABELS.items():
        if info["id"] == label_id:
            return name
    return None


def get_label_definitions_prompt() -> str:
    """Build the label definitions section for the GPT prompt.

    Only includes suggestable labels (excludes MANUAL_ONLY).
    """
    lines = []
    for name, info in SUGGESTABLE_LABELS.items():
        lines.append(f"- {name}: {info['description']}")
    return "\n".join(lines)

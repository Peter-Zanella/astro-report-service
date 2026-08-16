#!/usr/bin/env python3
"""
fixstars.py — Fixstern-Konjunktionen im Rāśi (D1).

Reine ANZEIGE: Das Modul liefert einen eigenen Tab im Bericht und fliesst
bewusst NICHT in die KI-Deutung ein — es steht in keinem Faktenblock.

Datenherkunft und Umrechnung
────────────────────────────
Die Vorlage nennt die Sternpositionen **tropisch** zur Epoche 2026. Dieses
Projekt rechnet durchgehend **siderisch (Lahiri)**; direkt übernommen läge
jeder Stern rund 24° falsch. Die Tabelle wird deshalb beim Laden einmalig
umgerechnet:

    siderisch = (tropisch − Ayanamsha(2026.0)) mod 360

mit derselben Lahiri-Funktion, die auch die Planeten benutzen
(astro_engine._ayanamsha). Kontrollpunkt: Lahiri ist über Spica bei 180°00'
definiert — die Vorlage landet bei 179.8°, die Abweichung stammt aus ihrer
Rundung auf ganze Grad.

Im siderischen Tierkreis sind Fixsterne über Jahrhunderte praktisch
ortsfest (nur Eigenbewegung, Bogensekunden pro Jahrhundert), die Tabelle
veraltet also nicht. Die Rundung der Vorlage auf 1° bleibt aber die
begrenzende Genauigkeit — bei Praxis-Orben von 1–1.5° ist das spürbar und
wird im Tab offen ausgewiesen.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

SIGNS_DE = ["Widder", "Stier", "Zwillinge", "Krebs", "Löwe", "Jungfrau",
            "Waage", "Skorpion", "Schütze", "Steinbock", "Wassermann", "Fische"]

#: Julianisches Datum zu 2026.0 — Epoche der tropischen Vorlage.
EPOCH_JD = 2461041.5

#: Deutsche Namen der Grahas für die Anzeige.
DE = {"Ascendant": "Aszendent", "Sun": "Sonne", "Moon": "Mond", "Mars": "Mars",
      "Mercury": "Merkur", "Jupiter": "Jupiter", "Venus": "Venus",
      "Saturn": "Saturn", "Rahu": "Rāhu", "Ketu": "Ketu"}

#: Reihenfolge der geprüften Punkte — klassisch wirken Fixsterne vor allem
#: auf Lagna und die Lichter.
BODIES = ["Ascendant", "Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter",
          "Saturn", "Rahu", "Ketu"]

#: (Name, tropischer Grad, tropischer Zeichenindex, Natur, Themen, Praxis-Orb)
#: Vorlage unverändert übernommen; die Umrechnung geschieht in _sidereal().
TROPICAL_2026: List[Tuple[str, float, int, str, str, float]] = [
    ("Algol",        26.0,  1, "Saturn/Jupiter", "extreme Intensität, Machtfragen, Kontrollverlust", 1.5),
    ("Aldebaran",    10.0,  2, "Mars",           "Mut, Durchsetzung, Ehre, militärischer Erfolg", 1.5),
    ("Rigel",        17.0,  2, "Jupiter/Saturn", "Erfolg, Können, Rang", 1.0),
    ("Sirius",       15.0,  3, "Jupiter/Mars",   "Ruhm, Macht, Ehrgeiz, aussergewöhnlicher Erfolg", 1.5),
    ("Castor",       21.0,  3, "Merkur",         "Intellekt, Geschicklichkeit, Schreiben", 1.0),
    ("Pollux",       24.0,  3, "Mars",           "Mut, Wettbewerb, Härte", 1.0),
    ("Procyon",      26.0,  3, "Merkur/Mars",    "schneller Aufstieg, Aktivität — aber Instabilität", 1.0),
    ("Regulus",       0.0,  5, "Mars/Jupiter",   "Herrschaft, Rang, Ruhm, Aufstieg", 1.5),
    ("Vindemiatrix", 10.0,  6, "Saturn/Merkur",  "Vorsicht, Trennung, schwierige Entscheidungen", 1.0),
    ("Spica",        24.0,  6, "Venus/Mars",     "Schutz, Talent, Erfolg, Kunst, Gelehrsamkeit", 1.5),
    ("Arcturus",     24.0,  6, "Mars/Jupiter",   "Führung, Erfolg, Wohlstand", 1.0),
    ("Unukalhai",    22.0,  7, "Saturn/Mars",    "Gefahr, Konflikt, schwierige Verwicklungen", 1.0),
    ("Antares",      10.0,  8, "Mars/Jupiter",   "Mut, Kampf, Ruhm, extreme Ambition", 1.5),
    ("Vega",         15.0,  9, "Venus/Merkur",   "Kunst, Musik, Charisma, Raffinesse", 1.5),
    ("Altair",        2.0, 10, "Mars/Jupiter",   "Kühnheit, Ehrgeiz, Aufstieg", 1.0),
    ("Deneb Algedi", 24.0, 10, "Saturn/Jupiter", "Recht, Autorität, Integrität", 1.0),
    ("Fomalhaut",     4.0, 11, "Venus/Merkur",   "Idealismus, Vision, Kunst, Spiritualität", 1.5),
    # Vorlage nennt "30° Fische" — das ist exakt die Zeichengrenze (= 0° Widder).
    # Gemeint ist das Ende der Fische; hier als 29°30' geführt.
    ("Scheat",       29.5, 11, "Mars/Merkur",    "Intellekt, Unabhängigkeit, extreme Erfahrungen", 1.0),
]

_CACHE: List[Dict] = []


def _sidereal() -> List[Dict]:
    """Tabelle einmalig nach siderisch (Lahiri) umgerechnet."""
    if _CACHE:
        return _CACHE
    try:
        from astro_engine import _ayanamsha
        ayan = _ayanamsha(EPOCH_JD)
    except Exception:
        ayan = 24.2163                      # Lahiri 2026.0, Notnagel
    for name, deg, si, nature, theme, orb in TROPICAL_2026:
        lon = ((si * 30 + deg) - ayan) % 360
        _CACHE.append({
            "name": name, "lon": round(lon, 2),
            "sign": SIGNS_DE[int(lon // 30)], "deg_in_sign": round(lon % 30, 2),
            "nature": nature, "themes": theme, "orb": orb,
        })
    _CACHE.sort(key=lambda s: s["lon"])
    return _CACHE


def _sep(a: float, b: float) -> float:
    """Kürzester Winkelabstand zweier Längen in Grad (0…180)."""
    d = abs(a - b) % 360.0
    return d if d <= 180.0 else 360.0 - d


def compute(chart: Dict) -> Dict:
    """{'stars': [...], 'hits': [...]} — Konjunktionen im D1 innerhalb des
    jeweiligen Praxis-Orbs. Nur Rāśi; Divisionalcharts bleiben aussen vor."""
    pls = chart.get("planets", {}) or {}
    hits = []
    for body in BODIES:
        rec = pls.get(body) or {}
        lon = rec.get("lon")
        if lon is None:
            continue
        for st in _sidereal():
            sep = _sep(float(lon), st["lon"])
            if sep <= st["orb"]:
                hits.append({
                    "body": body, "body_de": DE.get(body, body),
                    "star": st["name"], "orb": round(sep, 2),
                    "tight": sep <= 0.5,
                    "nature": st["nature"], "themes": st["themes"],
                    "sign": st["sign"], "deg_in_sign": st["deg_in_sign"],
                })
    hits.sort(key=lambda h: (BODIES.index(h["body"]), h["orb"]))
    return {"stars": _sidereal(), "hits": hits}


def render_tab(chart: Dict) -> str:
    """Innerer HTML-Inhalt des Fixstern-Tabs (Dark-Theme des Viewers)."""
    data = compute(chart)
    hits, stars = data["hits"], data["stars"]

    if hits:
        rows = "".join(
            f"<tr><td><strong>{h['body_de']}</strong></td>"
            f"<td style='color:var(--ac);font-weight:600'>{h['star']}"
            f"{' ★' if h['tight'] else ''}</td>"
            f"<td>{h['orb']:.2f}&deg;</td>"
            f"<td style='color:var(--mu)'>{h['nature']}</td>"
            f"<td style='color:var(--mu);font-size:.86rem'>{h['themes']}</td></tr>"
            for h in hits)
        hit_html = (
            "<table class='dt'><thead><tr><th>Punkt</th><th>Fixstern</th>"
            "<th>Orb</th><th>Natur</th><th>Themen</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
            "<p style='color:var(--mu);font-size:.82rem;margin:6px 0 0'>"
            "★ = sehr enge Konjunktion (unter 0.5&deg;).</p>")
    else:
        hit_html = ("<p style='color:var(--mu)'>Kein Planet und kein Aszendent "
                    "steht in diesem Horoskop innerhalb des Praxis-Orbs bei "
                    "einem der aufgef&uuml;hrten Fixsterne.</p>")

    srows = "".join(
        f"<tr><td><strong>{s['name']}</strong></td>"
        f"<td>{s['deg_in_sign']:.1f}&deg; {s['sign']}</td>"
        f"<td style='color:var(--mu)'>{s['nature']}</td>"
        f"<td style='color:var(--mu);font-size:.86rem'>{s['themes']}</td>"
        f"<td style='color:var(--mu)'>&plusmn;{s['orb']}&deg;</td></tr>"
        for s in stars)

    return f"""
<p class="sh">Fixsterne im R&#257;&#347;i (D1)</p>
<p style="color:var(--mu);font-size:.9rem;line-height:1.55">
Fixsterne wirken klassisch durch <strong>Konjunktion</strong> mit einem Planeten
oder dem Aszendenten — nicht durch Aspekte, und nur mit engem Orb. Gepr&uuml;ft
wird ausschliesslich das R&#257;&#347;i; die Divisionalcharts bleiben aussen vor.
Diese Seite ist reine Beobachtung und flie&szlig;t nicht in die Deutung ein.</p>

<h3 style="margin:16px 0 6px">Treffer in diesem Horoskop</h3>
{hit_html}

<h3 style="margin:22px 0 6px">Die Fixsterne, siderisch (Lahiri)</h3>
{f'<table class="dt"><thead><tr><th>Stern</th><th>Position</th><th>Natur</th>'
 f'<th>Themen</th><th>Orb</th></tr></thead><tbody>{srows}</tbody></table>'}
<p style="color:var(--mu);font-size:.82rem;margin:8px 0 0;line-height:1.5">
Die Vorlage nennt die Positionen <strong>tropisch</strong> und auf ganze Grad
gerundet; sie sind hier mit dem Lahiri-Ayanamsha der Epoche 2026 nach
<strong>siderisch</strong> umgerechnet. Kontrollpunkt: Lahiri ist &uuml;ber Spica
bei 180&deg;00' definiert, die Tabelle landet bei 179.8&deg;. Aus der Rundung
bleibt eine Unsch&auml;rfe von bis zu einem halben Grad — bei Orben von 1–1.5&deg;
ist das zu bedenken.</p>"""

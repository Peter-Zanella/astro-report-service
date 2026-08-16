#!/usr/bin/env python3
"""
fixstars.py — Fixstern-Konjunktionen im Rāśi (D1).

Reine ANZEIGE: Das Modul liefert einen eigenen Tab im Bericht und fliesst
bewusst NICHT in die KI-Deutung ein — es steht in keinem Faktenblock.

Zwei Positionsquellen, in dieser Reihenfolge
────────────────────────────────────────────
1. **Swiss Ephemeris** (bevorzugt): ``fixstar2_ut`` im Sidereal-Modus Lahiri,
   gestellt auf das Julianische Datum der GEBURT (``chart['meta']['jd']``).
   Bogensekundengenau, berücksichtigt Eigenbewegung, veraltet nie.
2. **Statische Tabelle** (Rückfall je Stern): Die Vorlage nennt die Positionen
   **tropisch** zur Epoche 2026 und auf ganze Grad gerundet. Sie werden mit
   derselben Lahiri-Funktion umgerechnet, die auch die Planeten benutzen::

       siderisch = (tropisch − Ayanamsha(2026.0)) mod 360

   Kontrollpunkt: Lahiri ist über Spica bei 180°00' definiert; die Vorlage
   landet bei 179.8°, die Restabweichung stammt aus ihrer Rundung.

Der Rückfall greift **pro Stern**, nicht global: Findet die Ephemeride einen
Namen nicht, behält nur dieser eine Stern seinen Tabellenwert. Welche Quelle
gewonnen hat, steht im Tab — so ist im Betrieb sofort sichtbar, ob die
Ephemeride wirklich greift.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

SIGNS_DE = ["Widder", "Stier", "Zwillinge", "Krebs", "Löwe", "Jungfrau",
            "Waage", "Skorpion", "Schütze", "Steinbock", "Wassermann", "Fische"]

#: Julianisches Datum zu 2026.0 — Epoche der tropischen Vorlage.
EPOCH_JD = 2461041.5

DE = {"Ascendant": "Aszendent", "Sun": "Sonne", "Moon": "Mond", "Mars": "Mars",
      "Mercury": "Merkur", "Jupiter": "Jupiter", "Venus": "Venus",
      "Saturn": "Saturn", "Rahu": "Rāhu", "Ketu": "Ketu"}

#: Klassisch wirken Fixsterne vor allem auf Lagna und die Lichter.
BODIES = ["Ascendant", "Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter",
          "Saturn", "Rahu", "Ketu"]

#: (Name, tropischer Grad, Zeichenindex, Natur, Themen, Praxis-Orb,
#:  Suchnamen für Swiss Ephemeris — Eigenname zuerst, Bayer als Rückfall)
TROPICAL_2026: List[Tuple[str, float, int, str, str, float, Tuple[str, ...]]] = [
    ("Algol",        26.0,  1, "Saturn/Jupiter", "extreme Intensität, Machtfragen, Kontrollverlust", 1.5, ("Algol", ",bePer")),
    ("Aldebaran",    10.0,  2, "Mars",           "Mut, Durchsetzung, Ehre, militärischer Erfolg", 1.5, ("Aldebaran", ",alTau")),
    ("Rigel",        17.0,  2, "Jupiter/Saturn", "Erfolg, Können, Rang", 1.0, ("Rigel", ",beOri")),
    ("Sirius",       15.0,  3, "Jupiter/Mars",   "Ruhm, Macht, Ehrgeiz, aussergewöhnlicher Erfolg", 1.5, ("Sirius", ",alCMa")),
    ("Castor",       21.0,  3, "Merkur",         "Intellekt, Geschicklichkeit, Schreiben", 1.0, ("Castor", ",alGem")),
    ("Pollux",       24.0,  3, "Mars",           "Mut, Wettbewerb, Härte", 1.0, ("Pollux", ",beGem")),
    ("Procyon",      26.0,  3, "Merkur/Mars",    "schneller Aufstieg, Aktivität — aber Instabilität", 1.0, ("Procyon", ",alCMi")),
    ("Regulus",       0.0,  5, "Mars/Jupiter",   "Herrschaft, Rang, Ruhm, Aufstieg", 1.5, ("Regulus", ",alLeo")),
    ("Vindemiatrix", 10.0,  6, "Saturn/Merkur",  "Vorsicht, Trennung, schwierige Entscheidungen", 1.0, ("Vindemiatrix", ",epVir")),
    ("Spica",        24.0,  6, "Venus/Mars",     "Schutz, Talent, Erfolg, Kunst, Gelehrsamkeit", 1.5, ("Spica", ",alVir")),
    ("Arcturus",     24.0,  6, "Mars/Jupiter",   "Führung, Erfolg, Wohlstand", 1.0, ("Arcturus", ",alBoo")),
    ("Unukalhai",    22.0,  7, "Saturn/Mars",    "Gefahr, Konflikt, schwierige Verwicklungen", 1.0, ("Unukalhai", ",alSer")),
    ("Antares",      10.0,  8, "Mars/Jupiter",   "Mut, Kampf, Ruhm, extreme Ambition", 1.5, ("Antares", ",alSco")),
    ("Vega",         15.0,  9, "Venus/Merkur",   "Kunst, Musik, Charisma, Raffinesse", 1.5, ("Vega", ",alLyr")),
    ("Altair",        2.0, 10, "Mars/Jupiter",   "Kühnheit, Ehrgeiz, Aufstieg", 1.0, ("Altair", ",alAql")),
    ("Deneb Algedi", 24.0, 10, "Saturn/Jupiter", "Recht, Autorität, Integrität", 1.0, ("Deneb Algedi", ",deCap")),
    ("Fomalhaut",     4.0, 11, "Venus/Merkur",   "Idealismus, Vision, Kunst, Spiritualität", 1.5, ("Fomalhaut", ",alPsA")),
    # Vorlage nennt "30° Fische" — exakt die Zeichengrenze (= 0° Widder).
    # Gemeint ist das Ende der Fische; hier als 29°30' geführt. Liefert die
    # Ephemeride einen Wert, ersetzt er diesen Näherungswert ohnehin.
    ("Scheat",       29.5, 11, "Mars/Merkur",    "Intellekt, Unabhängigkeit, extreme Erfahrungen", 1.0, ("Scheat", ",bePeg")),
]


def _table_lon(deg: float, sign_idx: int) -> float:
    """Tropischer Tabellenwert → siderisch (Lahiri, Epoche der Vorlage)."""
    try:
        from astro_engine import _ayanamsha
        ayan = _ayanamsha(EPOCH_JD)
    except Exception:
        ayan = 24.2163                      # Lahiri 2026.0, Notnagel
    return ((sign_idx * 30 + deg) - ayan) % 360


def _swe_lon(names: Tuple[str, ...], jd: float) -> Optional[float]:
    """Siderische Länge aus der Swiss Ephemeris, oder None.

    Probiert Eigenname und Bayer-Bezeichnung. Jeder Fehler — Modul fehlt,
    Sterndatei fehlt, Name unbekannt — führt zu None und damit zum
    Tabellenwert dieses einen Sterns.
    """
    try:
        import swisseph as swe
    except Exception:
        return None
    try:
        swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
        flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL
    except Exception:
        return None
    for nm in names:
        try:
            res = swe.fixstar2_ut(nm, jd, flags)
        except Exception:
            continue
        try:
            # pyswisseph 2.10: ((lon, lat, dist, ...), name, retflag)
            xx = res[0]
            lon = float(xx[0]) if isinstance(xx, (list, tuple)) else float(xx)
        except Exception:
            continue
        if 0.0 <= lon < 360.0:
            return lon
    return None


def positions(jd: Optional[float] = None) -> Tuple[List[Dict], str]:
    """(Sternliste, Quelle). Quelle ∈ {'swisseph', 'gemischt', 'tabelle'}."""
    out, n_swe = [], 0
    for name, deg, si, nature, theme, orb, swe_names in TROPICAL_2026:
        lon = _swe_lon(swe_names, jd) if jd else None
        src = "swisseph" if lon is not None else "tabelle"
        if lon is None:
            lon = _table_lon(deg, si)
        else:
            n_swe += 1
        out.append({
            "name": name, "lon": round(lon, 4), "src": src,
            "sign": SIGNS_DE[int(lon // 30)], "deg_in_sign": round(lon % 30, 2),
            "nature": nature, "themes": theme, "orb": orb,
        })
    out.sort(key=lambda s: s["lon"])
    source = ("swisseph" if n_swe == len(out)
              else "tabelle" if n_swe == 0 else "gemischt")
    return out, source


def _sep(a: float, b: float) -> float:
    """Kürzester Winkelabstand zweier Längen in Grad (0…180)."""
    d = abs(a - b) % 360.0
    return d if d <= 180.0 else 360.0 - d


def compute(chart: Dict) -> Dict:
    """{'stars', 'hits', 'source'} — Konjunktionen im D1 innerhalb des
    jeweiligen Praxis-Orbs. Nur Rāśi; Divisionalcharts bleiben aussen vor."""
    pls = chart.get("planets", {}) or {}
    jd = (chart.get("meta") or {}).get("jd")
    stars, source = positions(jd)
    hits = []
    for body in BODIES:
        lon = (pls.get(body) or {}).get("lon")
        if lon is None:
            continue
        for st in stars:
            sep = _sep(float(lon), st["lon"])
            if sep <= st["orb"]:
                hits.append({
                    "body": body, "body_de": DE.get(body, body),
                    "star": st["name"], "orb": round(sep, 2),
                    "tight": sep <= 0.5, "nature": st["nature"],
                    "themes": st["themes"], "sign": st["sign"],
                    "deg_in_sign": st["deg_in_sign"],
                })
    hits.sort(key=lambda h: (BODIES.index(h["body"]), h["orb"]))
    return {"stars": stars, "hits": hits, "source": source}


_SRC_NOTE = {
    "swisseph": ("Positionen aus der <strong>Swiss Ephemeris</strong>, siderisch "
                 "(Lahiri), gestellt auf den Geburtszeitpunkt — bogensekundengenau."),
    "gemischt": ("Positionen &uuml;berwiegend aus der <strong>Swiss Ephemeris</strong>; "
                 "einzelne Sterne, deren Namen die Sterndatei nicht kennt, stammen "
                 "aus der gerundeten Tabelle."),
    "tabelle":  ("Die Swiss Ephemeris war nicht erreichbar. Die Positionen stammen "
                 "aus der <strong>tropischen Vorlage</strong> (Epoche 2026, auf ganze "
                 "Grad gerundet), umgerechnet mit dem Lahiri-Ayanamsha. Kontrollpunkt: "
                 "Spica liegt definitionsgem&auml;ss auf 180&deg;00', die Tabelle "
                 "landet bei 179.8&deg;. Bei Orben von 1–1.5&deg; ist diese Rundung "
                 "zu bedenken."),
}


def render_tab(chart: Dict) -> str:
    """Innerer HTML-Inhalt des Fixstern-Tabs (Dark-Theme des Viewers)."""
    data = compute(chart)
    hits, stars, source = data["hits"], data["stars"], data["source"]

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
        f"<td>{s['deg_in_sign']:.2f}&deg; {s['sign']}</td>"
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
<table class="dt"><thead><tr><th>Stern</th><th>Position</th><th>Natur</th>
<th>Themen</th><th>Orb</th></tr></thead><tbody>{srows}</tbody></table>
<p style="color:var(--mu);font-size:.82rem;margin:8px 0 0;line-height:1.5">
{_SRC_NOTE.get(source, '')}</p>"""

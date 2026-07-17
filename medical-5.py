# -*- coding: utf-8 -*-
"""
medical.py — Medizinische Astrologie (Ayurveda-Jyotiṣa) für den Medizin-Tab.
=============================================================================
Prinzip unverändert: astro_engine ist die alleinige Quelle aller Positionen.
Dieses Modul LEITET daraus ab (keine Ephemeriden-Rechnung):

  1. Körperliche Konstitution (Doshas) — Methodik:
     Planeteneinflüsse auf Lagna (primär), auf das 6. Haus und auf den Mond
     (hell = Kapha / dunkel = Vata; Planeteneinflüsse dominieren). Das
     Lagna-ZEICHEN zählt nur, wenn gar keine Planeteneinflüsse vorliegen.
  2. Mentale Konstitution (Gunas) — über die Nakshatra-Herrscher von Lagna
     und allen neun Grahas (Sattva: So/Mo/Ju · Rajas: Me/Ve · Tamas: Ma/Sa/Ra/Ke).
  3. KAP-Tabelle (krankheitsanzeigende Punkte) — H6-/H8-Herr (je 2 Punkte),
     Debilitation, 22. Drekkāna-Herr (vom Lagna), 64. Navāṃśa-Herr (vom Mond),
     Mṛtyu Bhāga (fataler Grad, Orbis 1°), Verbrennung ≤ 8°, Rückläufigkeit,
     Gnāti-Kāraka, Graha Yuddha, Knotennähe ≤ 8°, Sandhi/Gandānta ≤ 1° (2 Punkte),
     Zeichen des grossen Feindes (Adhi-Śatru, zusammengesetzte Freundschaft).
  4. Fokusbereiche — Häuser/Zeichen, in denen sich die KAP-stärksten Planeten
     sammeln, mit klassischer Körperzuordnung (Kālapuruṣa).

Bewusst NICHT enthalten: Lebensspannen-/Maraka-Einschätzung und konkrete
Krankheitsdiagnosen — für einen Kundenbericht ungeeignet. Der Tab trägt einen
deutlichen Hinweis, dass er keine medizinische Beratung ersetzt.
"""
from typing import Dict, List, Optional, Tuple

from astro_engine import (SIGNS, SIGN_LORDS, _SPECIAL_ASPECTS, _MALEFICS,
                          drekkana_sign, navamsa_sign, norm)

GRAHAS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn",
          "Rahu", "Ketu"]
KAP_COLS = ["Lagna"] + GRAHAS

DE = {"Sun": "Sonne", "Moon": "Mond", "Mars": "Mars", "Mercury": "Merkur",
      "Jupiter": "Jupiter", "Venus": "Venus", "Saturn": "Saturn",
      "Rahu": "Rahu", "Ketu": "Ketu", "Lagna": "Lagna", "Ascendant": "Lagna"}

SIGN_DE = {"Aries": "Widder", "Taurus": "Stier", "Gemini": "Zwillinge",
           "Cancer": "Krebs", "Leo": "Löwe", "Virgo": "Jungfrau",
           "Libra": "Waage", "Scorpio": "Skorpion", "Sagittarius": "Schütze",
           "Capricorn": "Steinbock", "Aquarius": "Wassermann",
           "Pisces": "Fische"}

# ── Dosha-Zuordnung der Grahas (klassisch, u.a. nach Charak) ─────────────────
# Mond je nach Helligkeit; Merkur Tridosha mit Vata-Tendenz.
PLANET_DOSHA = {"Sun": "Pitta", "Mars": "Pitta", "Ketu": "Pitta",
                "Jupiter": "Kapha", "Venus": "Kapha",
                "Saturn": "Vata", "Rahu": "Vata"}

GUNA_OF_LORD = {"Sun": "Sattva", "Moon": "Sattva", "Jupiter": "Sattva",
                "Mercury": "Rajas", "Venus": "Rajas",
                "Mars": "Tamas", "Saturn": "Tamas",
                "Rahu": "Tamas", "Ketu": "Tamas"}

ELEMENT_DOSHA = {  # nur Fallback, wenn KEIN Planeteneinfluss auf das Lagna
    "Aries": "Pitta", "Leo": "Pitta", "Sagittarius": "Pitta",
    "Gemini": "Vata", "Libra": "Vata", "Aquarius": "Vata",
    "Cancer": "Kapha", "Scorpio": "Kapha", "Pisces": "Kapha",
    "Taurus": "Kapha", "Virgo": "Vata", "Capricorn": "Pitta",
}

# ── Kālapuruṣa: Zeichen → Körperbereiche (klassische Melothesie) ─────────────
SIGN_BODY = {
    "Aries": "Kopf, Gehirn, Augen", "Taurus": "Hals, Kehle, Schilddrüse, Zähne",
    "Gemini": "Schultern, Arme, Bronchien, oberer Brustkorb",
    "Cancer": "Brustkorb, Brustgewebe, Lunge",
    "Leo": "Oberbauch: Magen, Herz, Leber, Milz",
    "Virgo": "Dünndarm, Verdauung/Resorption, Nieren",
    "Libra": "Nieren, innere Fortpflanzungsorgane, Teil des Dickdarms",
    "Scorpio": "Genitalien, Enddarm, Blase, Ausscheidungsorgane",
    "Sagittarius": "Hüften, Oberschenkel",
    "Capricorn": "Knie, Gelenke, Rücken insgesamt",
    "Aquarius": "Unterschenkel, Waden, Durchblutung",
    "Pisces": "Füsse, Lymphsystem",
}
HOUSE_BODY = {
    1: "Kopf, Gesamtvitalität", 2: "Gesicht, Mund, Zähne, Ernährungsweise",
    3: "Schultern, Arme, obere Atemwege", 4: "Brustkorb, Herz (emotional), Lunge",
    5: "Magen, Herz, Leber, Oberbauch", 6: "Verdauungstrakt, Immunsystem",
    7: "Unterbauch, Nieren, innere Organe des Beckens",
    8: "Ausscheidungs- und Fortpflanzungsorgane, chronische Prozesse",
    9: "Hüften, Oberschenkel", 10: "Knie, Gelenke, Haut",
    11: "Unterschenkel, Durchblutung", 12: "Füsse, Schlaf, Regeneration",
}

# ── Planet → Organ-Signifikationen (klassische Kārakas) ──────────────────────
PLANET_ORGANS = {
    "Sun":     "Herz, Vitalität, rechtes Auge, Knochen, Magen (Agni)",
    "Moon":    "Flüssigkeitshaushalt, Blutplasma, linkes Auge, Psyche, Schleimhäute",
    "Mars":    "Muskulatur, Blut/Hämoglobin, Knochenmark, Gallenblase, Milz",
    "Mercury": "Nervensystem/Reizleitung, Haut, Lunge, Resorption (Dünndarm), Sprache",
    "Jupiter": "Leber, Fettstoffwechsel, Bauchspeicheldrüse (Insulin), Hüften, Ohren",
    "Venus":   "Nieren, Drüsen und Hormone, Verdauungssäfte, Fortpflanzungsorgane, Augenlinse",
    "Saturn":  "Nervenbahnen, Knochen, Zähne, Dickdarm, Beine; Chronizität",
    "Rahu":    "verstärkt/verzerrt bestehende Muster; Unruhe, Schlaf, Ungewöhnliches",
    "Ketu":    "wirkt Mars-ähnlich (Pitta); schwer fassbare, plötzliche Prozesse",
}
PLANET_TENDENCY = {
    "Sun":     "Als Kāraka für Herz und Lebenskraft zentral: geschwächt zeigt sie nachlassende Vitalität und Regenerationskraft an.",
    "Moon":    "Zeigt den Zustand von Gemüt und Säftehaushalt; ein dunkler oder bedrängter Mond macht empfindsam und erschöpfbar.",
    "Mars":    "Steht für Hitze, Entzündungsneigung, Verletzungen und Eingriffe; gibt zugleich Antrieb und Abwehrkraft.",
    "Mercury": "Beschädigt zeigt er nervöse Unruhe, Haut- und Resorptionsthemen; stark gibt er ein anpassungsfähiges System.",
    "Jupiter": "Zu stark oder bedrängt: Themen von Fülle (Gewicht, Stoffwechsel, Leber); stark und rein wirkt er ausgesprochen schützend.",
    "Venus":   "Betrifft Drüsen, Hormone und den Genussbereich; ihre Würde zeigt, wie gut Genuss und Mass im Gleichgewicht sind.",
    "Saturn":  "Der allgemeine Krankheits-Kāraka: Verhärtung, Verzögerung, chronische Verläufe — aber auch Ausdauer und Disziplin.",
    "Rahu":    "Allein löst er selten etwas aus; wo er mitwirkt, werden Prozesse unregelmässiger, diffuser und dramatischer.",
    "Ketu":    "Bringt schwer greifbare, plötzliche oder tief verwurzelte Themen; diagnostisch oft die »unklare« Komponente.",
}

DOSHA_PROFILE = {
    "Vata": ("Bewegung (Äther/Luft)",
             "Feingliedrig, schnell, wandelbar; sensibles Nervensystem und "
             "unregelmässige Verdauung. Kreativ und kommunikativ, aber rasch "
             "erschöpft und kälteempfindlich.",
             "Ausgleich: Wärme, Regelmässigkeit (Essen, Schlaf), warme Mahlzeiten, "
             "Ruhephasen, Ölmassagen; Reizüberflutung meiden."),
    "Pitta": ("Transformation (Feuer/Wasser)",
              "Dynamisch, zielstrebig, durchsetzungsstark; kräftige Verdauung und "
              "gute Argumentation. Neigt zu Hitze, Übersäuerung, Entzündungen und "
              "Reizbarkeit unter Druck.",
              "Ausgleich: Kühlendes und Mässigung bei Scharfem, Saurem, Alkohol; "
              "Pausen, Bewegung als Ventil, Meditation."),
    "Kapha": ("Stabilität (Wasser/Erde)",
              "Kräftig gebaut, ausdauernd, ruhig und loyal; gutes Immunsystem. "
              "Neigt zu Trägheit, Gewichtszunahme, Schleimbildung und langsamer "
              "Verdauung.",
              "Ausgleich: Regelmässige Bewegung, leichte und anregende Kost, "
              "Abwechslung; Tagschlaf und Schwere meiden."),
}
GUNA_PROFILE = {
    "Sattva": "Klarheit, Ethik, Harmonie — der Zug nach oben; viel Sattva strebt nach dem Idealen.",
    "Rajas":  "Aktivität, Wunsch, Umtriebigkeit — die kinetische Kraft, die Dinge in Bewegung setzt.",
    "Tamas":  "Beharrung, Schwere, Fixierung — gibt Umsetzungskraft und Ausdauer, im Übermass Starrheit.",
}

# ── Mṛtyu Bhāga (fatale Grade) je Zeichen, Orbis 1° ──────────────────────────
# Reihenfolge der Werte: Widder … Fische
MRITYU_BHAGA = {
    "Sun":     [20, 9, 12, 6, 8, 24, 16, 17, 22, 2, 3, 23],
    "Moon":    [26, 12, 13, 25, 24, 11, 26, 14, 13, 25, 5, 12],
    "Mars":    [19, 28, 25, 23, 29, 28, 14, 21, 2, 15, 11, 6],
    "Mercury": [15, 14, 13, 12, 8, 18, 20, 10, 21, 22, 7, 5],
    "Jupiter": [19, 29, 12, 27, 6, 4, 13, 10, 17, 11, 15, 28],
    "Venus":   [28, 15, 11, 17, 10, 13, 4, 6, 27, 12, 29, 19],
    "Saturn":  [10, 4, 7, 9, 12, 16, 3, 18, 28, 14, 13, 15],
    "Rahu":    [14, 13, 12, 11, 24, 23, 22, 21, 10, 20, 18, 8],
    "Ketu":    [8, 18, 20, 10, 21, 22, 23, 24, 11, 12, 13, 14],
    "Lagna":   [8, 9, 22, 22, 25, 14, 4, 23, 18, 20, 21, 10],
}

# ── Natürliche Freundschaften (BPHS) für Adhi-Śatru ──────────────────────────
_NAT_FRIEND = {
    "Sun": {"Moon", "Mars", "Jupiter"}, "Moon": {"Sun", "Mercury"},
    "Mars": {"Sun", "Moon", "Jupiter"}, "Mercury": {"Sun", "Venus"},
    "Jupiter": {"Sun", "Moon", "Mars"}, "Venus": {"Mercury", "Saturn"},
    "Saturn": {"Mercury", "Venus"},
}
_NAT_ENEMY = {
    "Sun": {"Venus", "Saturn"}, "Moon": set(), "Mars": {"Mercury"},
    "Mercury": {"Moon"}, "Jupiter": {"Mercury", "Venus"},
    "Venus": {"Sun", "Moon"}, "Saturn": {"Sun", "Moon", "Mars"},
}
_SEVEN = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]


# ══════════════════════════════════════════════════════════════════════════════
# Hilfsfunktionen
# ══════════════════════════════════════════════════════════════════════════════

def _deg_in_sign(pls: Dict, p: str) -> float:
    lon = pls.get(p, {}).get("lon")
    return (lon % 30.0) if lon is not None else -99.0


def _aspected_houses(p: str, h: int) -> List[int]:
    """Häuser, die Planet p aus Haus h per Graha-Drishti aspektiert
    (7. für alle; Sonderaspekte für Ma/Ju/Sa/Ra/Ke wie im astro_engine)."""
    if not h:
        return []
    out = [((h + 5) % 12) + 1]                       # 7. Haus
    for off in _SPECIAL_ASPECTS.get(p, []):
        out.append(((h + off - 2) % 12) + 1)
    return out


def _influences_on_house(chart: Dict, house: int) -> List[str]:
    """Besetzer + aspektierende Planeten eines Hauses (Whole-Sign)."""
    occ = list((chart.get("occupants") or {}).get(house, []) or [])
    pls = chart.get("planets", {})
    asp = [p for p in GRAHAS
           if p not in occ and house in _aspected_houses(p, pls.get(p, {}).get("house", 0))]
    return occ + asp


def _moon_brightness(chart: Dict) -> Tuple[str, float]:
    """(hell|mittel|dunkel, Elongation°) aus Sonnen-/Mondlänge."""
    lons = chart.get("lons", {})
    if "Sun" not in lons or "Moon" not in lons:
        return "mittel", 0.0
    elong = (lons["Moon"] - lons["Sun"]) % 360.0
    d = min(elong, 360.0 - elong)          # Winkelabstand zur Sonne 0–180°
    if d >= 120.0:
        return "hell", elong
    if d <= 60.0:
        return "dunkel", elong
    return "mittel", elong


def _dosha_vote(p: str, moon_state: str) -> Optional[Tuple[str, float, str]]:
    """(Dosha, Gewicht, Begründung) eines einwirkenden Planeten."""
    if p == "Moon":
        if moon_state == "hell":
            return ("Kapha", 1.0, "heller Mond")
        if moon_state == "dunkel":
            return ("Vata", 1.0, "dunkler Mond")
        return ("Kapha", 0.5, "Mond (mittel)")
    if p == "Mercury":
        return ("Vata", 0.5, "Merkur (Tridosha, leichte Vata-Tendenz)")
    d = PLANET_DOSHA.get(p)
    return (d, 1.0, DE.get(p, p)) if d else None


# ══════════════════════════════════════════════════════════════════════════════
# 1. Konstitution (Doshas)
# ══════════════════════════════════════════════════════════════════════════════

def compute_doshas(chart: Dict) -> Dict:
    pls = chart.get("planets", {})
    moon_state, _ = _moon_brightness(chart)
    score = {"Vata": 0.0, "Pitta": 0.0, "Kapha": 0.0}
    lines: List[Tuple[str, str]] = []

    # (1) Lagna — primäre Gewichtung (×2). Zeichen NUR als Fallback.
    lag_infl = _influences_on_house(chart, 1)
    if lag_infl:
        parts = []
        for p in lag_infl:
            v = _dosha_vote(p, moon_state)
            if v:
                score[v[0]] += v[1] * 2.0
                parts.append(f"{DE.get(p, p)} → {v[0]}")
        lines.append(("Lagna (primär)", ", ".join(parts) if parts else "—"))
    else:
        sign = chart.get("lagna")
        d = ELEMENT_DOSHA.get(sign, "Vata")
        score[d] += 2.0
        lines.append(("Lagna (primär)",
                      f"keine Planeteneinflüsse — Zeichen {SIGN_DE.get(sign, sign)} → {d}"))

    # (2) 6. Haus
    h6_infl = _influences_on_house(chart, 6)
    parts = []
    for p in h6_infl:
        v = _dosha_vote(p, moon_state)
        if v:
            score[v[0]] += v[1]
            parts.append(f"{DE.get(p, p)} → {v[0]}")
    lines.append(("6. Haus", ", ".join(parts) if parts else "unbesetzt und unaspektiert"))

    # (3) Mond: Planeteneinflüsse dominieren, Helligkeit sonst/sekundär.
    mh = pls.get("Moon", {}).get("house", 0)
    m_infl = [p for p in _influences_on_house(chart, mh) if p != "Moon"] if mh else []
    parts = []
    if m_infl:
        for p in m_infl:
            v = _dosha_vote(p, moon_state)
            if v:
                score[v[0]] += v[1]
                parts.append(f"{DE.get(p, p)} → {v[0]}")
        parts.append(f"(Mond selbst: {moon_state})")
    else:
        v = _dosha_vote("Moon", moon_state)
        if v:
            score[v[0]] += v[1]
        parts.append(f"Mond {moon_state} → {v[0] if v else '—'}")
    lines.append(("Mond", ", ".join(parts)))

    ranked = sorted(score.items(), key=lambda kv: -kv[1])
    primary, secondary = ranked[0][0], ranked[1][0]
    if ranked[1][1] <= 0:
        secondary = None
    return {"scores": {k: round(v, 1) for k, v in score.items()},
            "primary": primary, "secondary": secondary,
            "moon_state": moon_state, "derivation": lines}


# ══════════════════════════════════════════════════════════════════════════════
# 2. Mentale Konstitution (Gunas)
# ══════════════════════════════════════════════════════════════════════════════

def compute_gunas(chart: Dict) -> Dict:
    pls = chart.get("planets", {})
    counts = {"Sattva": 0, "Rajas": 0, "Tamas": 0}
    rows = []
    for p in ["Ascendant"] + GRAHAS:
        nl = pls.get(p, {}).get("nak_lord")
        g = GUNA_OF_LORD.get(nl)
        if g:
            counts[g] += 1
        rows.append((DE.get(p, p), pls.get(p, {}).get("nakshatra", "—"),
                     DE.get(nl, nl or "—"), g or "—"))
    dominant = max(counts, key=counts.get)
    low = min(counts, key=counts.get)
    note = ""
    if counts["Tamas"] <= 1:
        note = ("Wenig Tamas: viele Ideen und Ideale, aber die praktische "
                "Umsetzungs- und Beharrungskraft will bewusst gepflegt sein.")
    elif counts["Rajas"] <= 1:
        note = ("Wenig Rajas: die Bewegungsenergie, um Vorhaben anzustossen, "
                "ist der Engpass — kleine, regelmässige Schritte helfen.")
    elif counts["Sattva"] <= 1:
        note = ("Wenig Sattva: Klarheit und Ausgleich brauchen bewusste Pflege "
                "(Ruhe, Natur, ethische Ausrichtung).")
    return {"counts": counts, "dominant": dominant, "low": low,
            "rows": rows, "note": note}


# ══════════════════════════════════════════════════════════════════════════════
# 3. KAP-Tabelle (krankheitsanzeigende Punkte)
# ══════════════════════════════════════════════════════════════════════════════

def _compound_great_enemies(pls: Dict) -> Dict[str, set]:
    """Adhi-Śatru je Planet: natürlicher UND temporärer Feind."""
    out: Dict[str, set] = {}
    sidx = {p: pls.get(p, {}).get("sign_idx") for p in _SEVEN}
    for p in _SEVEN:
        si = sidx.get(p)
        if si is None:
            out[p] = set()
            continue
        temp_friend = set()
        for q in _SEVEN:
            if q == p or sidx.get(q) is None:
                continue
            rel = (sidx[q] - si) % 12 + 1        # Haus von q, von p aus gezählt
            if rel in (2, 3, 4, 10, 11, 12):
                temp_friend.add(q)
        temp_enemy = {q for q in _SEVEN if q != p} - temp_friend
        out[p] = _NAT_ENEMY.get(p, set()) & temp_enemy
    return out


def compute_kap(chart: Dict) -> Dict:
    """Punktematrix: Kriterien × (Lagna + 9 Grahas)."""
    pls = chart.get("planets", {})
    houses = chart.get("houses", {}) or {}
    aff = chart.get("afflictions", {}) or {}
    lons = chart.get("lons", {})
    h6_lord = SIGN_LORDS.get(houses.get(6, houses.get("6")))
    h8_lord = SIGN_LORDS.get(houses.get(8, houses.get("8")))
    gk = ((chart.get("jaimini") or {}).get("karakas") or {}) \
        .get("Gnatikaraka", {}).get("planet")
    great_enemy = _compound_great_enemies(pls)

    rows: List[Tuple[str, Dict[str, int]]] = []

    def row(label, marks: Dict[str, int]):
        rows.append((label, marks))

    row("Herr des 6. Hauses (2 Punkte)", {h6_lord: 2} if h6_lord else {})
    row("Herr des 8. Hauses (2 Punkte)", {h8_lord: 2} if h8_lord else {})
    row("Debilitation (Fall)",
        {p: 1 for p in GRAHAS if "Debil" in pls.get(p, {}).get("dignity", "")})

    asc_lon = lons.get("Ascendant")
    m22 = {}
    if asc_lon is not None:
        # 22. Drekkāna = 21 Drekkānas (à 10°) weiter → +210°
        lord = SIGN_LORDS[SIGNS[drekkana_sign(norm(asc_lon + 210.0))]]
        m22[lord] = 1
    row("Herr des 22. Drekkāna (vom Lagna)", m22)

    moon_lon = lons.get("Moon")
    m64 = {}
    if moon_lon is not None:
        # 64. Navāṃśa = 63 Navāṃśas (à 3°20') weiter → +210°
        lord = SIGN_LORDS[SIGNS[navamsa_sign(norm(moon_lon + 210.0))]]
        m64[lord] = 1
    row("Herr des 64. Navāṃśa (vom Mond)", m64)

    mb = {}
    for p in KAP_COLS:
        key = "Ascendant" if p == "Lagna" else p
        deg = _deg_in_sign(pls, key)
        si = pls.get(key, {}).get("sign_idx")
        if deg >= 0 and si is not None:
            if abs(deg - MRITYU_BHAGA[p][si]) <= 1.0:
                mb[p] = 1
    row("Mṛtyu Bhāga — fataler Grad (Orbis 1°)", mb)

    sun_lon = lons.get("Sun")
    comb = {}
    if sun_lon is not None:
        for p in GRAHAS:
            if p in ("Sun", "Rahu", "Ketu"):
                continue
            l = pls.get(p, {}).get("lon")
            if l is not None and abs((l - sun_lon + 180) % 360 - 180) <= 8.0:
                comb[p] = 1
    row("Verbrannt (≤ 8° zur Sonne)", comb)

    row("Rückläufig", {p: 1 for p in GRAHAS
                       if p not in ("Sun", "Moon", "Rahu", "Ketu")
                       and pls.get(p, {}).get("retrograde")})
    row("Gnāti-Kāraka (Jaimini)", {gk: 1} if gk in GRAHAS else {})
    row("Graha Yuddha (Planetenkrieg)",
        {p: 1 for p in GRAHAS if any("Graha Yuddha" in a for a in aff.get(p, []))})

    nodal = {}
    for node in ("Rahu", "Ketu"):
        nl = pls.get(node, {}).get("lon")
        if nl is None:
            continue
        for p in GRAHAS:
            if p in ("Rahu", "Ketu"):
                continue
            l = pls.get(p, {}).get("lon")
            if l is not None and abs((l - nl + 180) % 360 - 180) <= 8.0:
                nodal[p] = 1
    row("Knotennähe ≤ 8° (Finsternisachse)", nodal)

    sandhi = {}
    for p in KAP_COLS:
        key = "Ascendant" if p == "Lagna" else p
        deg = _deg_in_sign(pls, key)
        if deg >= 0 and min(deg, 30.0 - deg) <= 1.0:
            sandhi[p] = 2
    row("Sandhi / Gandānta ≤ 1° (2 Punkte)", sandhi)

    row("Im Zeichen des grossen Feindes (Adhi-Śatru)",
        {p: 1 for p in _SEVEN
         if pls.get(p, {}).get("sign_lord") in great_enemy.get(p, set())})

    totals = {c: 0 for c in KAP_COLS}
    for _label, marks in rows:
        for p, v in marks.items():
            if p in totals:
                totals[p] += v
    return {"rows": rows, "totals": totals,
            "h6_lord": h6_lord, "h8_lord": h8_lord}


# ══════════════════════════════════════════════════════════════════════════════
# 4. Fokusbereiche (wo sammeln sich die KAP-stärksten Planeten?)
# ══════════════════════════════════════════════════════════════════════════════

def compute_focus(chart: Dict, kap: Dict, top_n: int = 3) -> Dict:
    pls = chart.get("planets", {})
    houses = chart.get("houses", {}) or {}
    totals = kap["totals"]
    lagna_idx = chart.get("lagna_idx", 0)

    house_score = {h: 0.0 for h in range(1, 13)}
    house_who: Dict[int, List[str]] = {h: [] for h in range(1, 13)}
    for p in GRAHAS:
        w = totals.get(p, 0)
        if w <= 0:
            continue
        h = pls.get(p, {}).get("house", 0)
        if h:
            house_score[h] += w
            house_who[h].append(f"{DE[p]} ({w})")
            for ah in _aspected_houses(p, h):
                house_score[ah] += w * 0.5
                house_who[ah].append(f"{DE[p]}-Aspekt ({w}·½)")

    hot = sorted(house_score.items(), key=lambda kv: -kv[1])[:top_n]
    items = []
    for h, sc in hot:
        if sc <= 0:
            continue
        sign = houses.get(h, houses.get(str(h)))
        sign_de = SIGN_DE.get(sign, sign or "—")
        body = HOUSE_BODY.get(h, "")
        body_sign = SIGN_BODY.get(sign, "")
        items.append({"house": h, "sign": sign_de, "score": round(sc, 1),
                      "who": house_who[h], "body_house": body,
                      "body_sign": body_sign})

    # Treffen sich H6- und H8-Herr? (klassisch besonders zu beachten)
    meet = None
    h6l, h8l = kap.get("h6_lord"), kap.get("h8_lord")
    if h6l and h8l:
        hh6 = pls.get(h6l, {}).get("house")
        hh8 = pls.get(h8l, {}).get("house")
        if hh6 and hh6 == hh8:
            sign = houses.get(hh6, houses.get(str(hh6)))
            meet = {"house": hh6, "sign": SIGN_DE.get(sign, sign),
                    "lords": f"{DE.get(h6l)} (H6) und {DE.get(h8l)} (H8)"}
    return {"items": items, "h6_h8_meet": meet}


# ══════════════════════════════════════════════════════════════════════════════
# 5. Lebensspanne (NUR Test-Modus — niemals im Kundenbericht)
# ══════════════════════════════════════════════════════════════════════════════
# Checkliste nach der Seminar-Methodik. Ausgabe sind Plus-/Minus-Befunde je
# Kriterium und eine vorsichtige Gesamttendenz — bewusst KEINE Jahreszahlen
# und keine Vorhersage. Der Schlüssel liegt klassisch in der Daśā-Sequenz;
# dafür werden die Maraka- und Dushthana-Herren benannt (Abgleich im Daśā-Tab).

_BENEFICS = {"Jupiter", "Venus", "Mercury"}
_KENDRA, _TRIKONA = {1, 4, 7, 10}, {1, 5, 9}
_DUSHTHANA, _UPACHAYA = {6, 8, 12}, {3, 6, 10, 11}


def compute_lifespan(chart: Dict) -> Dict:
    pls = chart.get("planets", {})
    houses = chart.get("houses", {}) or {}
    aff = chart.get("afflictions", {}) or {}
    sb = ((chart.get("shadbala") or {}).get("planets") or {})
    lagna_sign = chart.get("lagna")
    lagna_lord = SIGN_LORDS.get(lagna_sign)
    moon_state, _ = _moon_brightness(chart)

    def h(p):   return pls.get(p, {}).get("house", 0)
    def dig(p): return pls.get(p, {}).get("dignity", "-")
    def rupa(p):
        v = sb.get(p, {}).get("total")
        return round(v / 60.0, 2) if isinstance(v, (int, float)) else None

    plus: List[str] = []
    minus: List[str] = []
    rows: List[Tuple[str, str, str]] = []   # (Kriterium, Befund, +/-/·)

    def row(crit, finding, mark):
        rows.append((crit, finding, mark))
        (plus if mark == "+" else minus if mark == "−" else []).append(crit)

    # 1. Allgemeine Stärke des Rasi
    ben_kendra = [p for p in _BENEFICS if h(p) in _KENDRA]
    if moon_state == "hell" and h("Moon") in _KENDRA:
        ben_kendra.append("Moon")
    mal_kendra = [p for p in _MALEFICS if h(p) in _KENDRA]
    # Dushthana-Besetzung differenziert: Übeltäter im 6. Haus (Upachaya UND
    # Roga-Bhāva) STÜTZEN Gesundheit und Abwehr — sie zählen hier nicht
    # negativ (Kredit folgt unter »Verbessernde Faktoren«). Negativ bleiben:
    # alle Besetzer von 8/12 sowie Wohltäter und Mond in 6.
    dusht_bad = [p for p in GRAHAS
                 if h(p) in _DUSHTHANA
                 and not (h(p) == 6 and p in _MALEFICS)]
    mal_in_6 = [p for p in _MALEFICS if h(p) == 6]
    t = (f"Wohltäter in Kendras: {', '.join(DE[p] for p in ben_kendra) or 'keine'} · "
         f"Übeltäter in Kendras: {', '.join(DE[p] for p in mal_kendra) or 'keine'} · "
         f"belastende Dushthana-Besetzung (8/12; Wohltäter/Mond in 6): "
         f"{', '.join(DE[p] for p in dusht_bad) or 'keine'}"
         + (f" · Übeltäter in 6 stützen die Abwehr: "
            f"{', '.join(DE[p] for p in mal_in_6)}" if mal_in_6 else ""))
    m = "+" if len(ben_kendra) > len(mal_kendra) and len(dusht_bad) <= 1 else \
        "−" if (len(dusht_bad) >= 3 or (mal_kendra and not ben_kendra)) else "·"
    row("Allgemeine Stärke des Rasi", t, m)

    # 2. Lagna-Herr: Kendra/Trikona +, 2/3/11 ok, Dushthana −
    lh = h(lagna_lord) if lagna_lord else 0
    la = aff.get(lagna_lord, [])
    pos = ("Kendra/Trikona" if lh in _KENDRA | _TRIKONA else
           "2/3/11 (ordentlich)" if lh in (2, 3, 11) else
           "Dushthana" if lh in _DUSHTHANA else f"Haus {lh}")
    t = (f"{DE.get(lagna_lord)} in Haus {lh} ({pos}), Würde: {dig(lagna_lord)}"
         + (f", Affliktionen: {'; '.join(la)}" if la else ""))
    m = ("+" if lh in _KENDRA | _TRIKONA and not la else
         "−" if lh in _DUSHTHANA or len(la) >= 2 else "·")
    row("Stärke des Lagna-Herrn", t, m)

    # 3. Mond: am besten 3,4,5,9,10,11, hell, unbeschädigt; nicht gut in 1/7
    mh, ma = h("Moon"), aff.get("Moon", [])
    good_h = mh in {3, 4, 5, 9, 10, 11}
    t = (f"Haus {mh} ({'günstig' if good_h else 'nicht ideal'}), Mond {moon_state}"
         + (f", Affliktionen: {'; '.join(ma)}" if ma else ", unbeschädigt"))
    m = ("+" if good_h and moon_state == "hell" and not ma else
         "−" if (mh in _DUSHTHANA or mh in (1, 7)) and (moon_state == "dunkel" or ma)
         else "·")
    row("Stärke & Position des Mondes", t, m)

    # 4. Sonne
    sh, sa = h("Sun"), aff.get("Sun", [])
    t = f"Haus {sh}, Würde: {dig('Sun')}" + (f", Affliktionen: {'; '.join(sa)}" if sa else "")
    m = ("+" if dig("Sun") in ("Exalted", "Own Sign", "Moolatrikona") and sh not in _DUSHTHANA
         else "−" if sh in _DUSHTHANA or "Debil" in dig("Sun") else "·")
    row("Stärke der Sonne", t, m)

    # 5. Āyur-Kāraka Saturn (Rückläufigkeit stärkt die Lebenslänge)
    sat_h, sat_r = h("Saturn"), bool(pls.get("Saturn", {}).get("retrograde"))
    t = (f"Haus {sat_h}, Würde: {dig('Saturn')}"
         + (", rückläufig (stärkt die Lebenslänge)" if sat_r else "")
         + (f", Rupas: {rupa('Saturn')}" if rupa("Saturn") is not None else ""))
    m = ("+" if dig("Saturn") in ("Exalted", "Own Sign", "Moolatrikona")
         or sat_r or sat_h in _UPACHAYA | _KENDRA else
         "−" if "Debil" in dig("Saturn") or sat_h in (8, 12) else "·")
    row("Stärke des Āyur-Kāraka Saturn", t, m)

    # 6. Achtes Haus: Herr nicht in 7/12; nicht stärker als der Lagna-Herr
    h8_lord = SIGN_LORDS.get(houses.get(8, houses.get("8")))
    l8 = h(h8_lord) if h8_lord else 0
    r8, rl = rupa(h8_lord), rupa(lagna_lord)
    findings = [f"H8-Herr {DE.get(h8_lord)} in Haus {l8}"]
    bad = False
    if l8 in (7, 12):
        findings.append("steht in 7/12 — klassisch ungünstig"); bad = True
    if r8 is not None and rl is not None:
        findings.append(f"Rupas H8-Herr {r8} vs. Lagna-Herr {rl}")
        if r8 > rl:
            findings.append("H8-Herr ist stärker als der Lagna-Herr"); bad = True
    m = "−" if bad else ("+" if dig(h8_lord) in ("Exalted", "Own Sign",
                                                 "Moolatrikona") and not bad else "·")
    row("Beurteilung des 8. Hauses", ", ".join(findings), m)

    # 6b. Vipareeta Rāja Yoga (D1): Dushthana-Herr im Dushthana — stärkt die
    # Lebensspanne (Kraft durch Überwindung), ist aber für die GESUNDHEIT
    # neutral bis fordernd ("Vimala/Vipareeta stärkend, aber nicht für die
    # Gesundheit"). Volle Wirkung klassisch nur bei sonst unverbundenem Herrn.
    vry_hits = []
    for hd, nm in ((6, "Harsha"), (8, "Sarala"), (12, "Vimala")):
        L = SIGN_LORDS.get(houses.get(hd, houses.get(str(hd))))
        if L and h(L) in _DUSHTHANA:
            vry_hits.append(f"{nm} ({DE.get(L)}: H{hd}-Herr in Haus {h(L)})")
    row("Vipareeta Rāja Yoga (Lebensspanne)",
        ("; ".join(vry_hits) + " — stärkt die Lebensspanne, für Gesundheit "
         "neutral bis fordernd") if vry_hits else "keines",
        "+" if vry_hits else "·")

    # 7. Verbessernde Faktoren
    day_birth = h("Sun") in {7, 8, 9, 10, 11, 12}   # Sonne über dem Horizont (Whole-Sign-Näherung)
    mal_upa = [p for p in _MALEFICS if h(p) in _UPACHAYA]
    impr = []
    if ben_kendra: impr.append(f"Wohltäter in Kendras ({', '.join(DE[p] for p in ben_kendra)})")
    if mal_upa:    impr.append(f"Übeltäter in Upachayas ({', '.join(DE[p] for p in mal_upa)})")
    if h("Sun") == 11 and day_birth:       impr.append("Sonne in 11 bei Taggeburt")
    if h("Moon") == 11 and not day_birth:  impr.append("Mond in 11 bei Nachtgeburt")
    row("Verbessernde Faktoren", "; ".join(impr) or "keine", "+" if impr else "·")

    # 8. Verkürzende Faktoren
    shortening = [f"{DE[p]} in 8" for p in ("Ketu", "Mars") if h(p) == 8]
    row("Verkürzende Faktoren (Ketu/Mars in 8)",
        "; ".join(shortening) or "keine", "−" if shortening else "·")

    # Daśā-Hinweis: Maraka- (H2/H7) und Dushthana-Herren (H6/H8/H12)
    def lord_of(hn):
        return SIGN_LORDS.get(houses.get(hn, houses.get(str(hn))))
    maraka = sorted({lord_of(2), lord_of(7)} - {None})
    dush_lords = sorted({lord_of(6), lord_of(8), lord_of(12)} - {None})

    score = sum(1 for _c, _f, mk in rows if mk == "+") - \
            sum(1 for _c, _f, mk in rows if mk == "−")
    tendency = ("überwiegend stützende Faktoren" if score >= 2 else
                "gemischtes Bild" if score >= -1 else
                "überwiegend belastende Faktoren")
    return {"rows": rows, "score": score, "tendency": tendency,
            "day_birth": day_birth,
            "maraka_lords": [DE.get(p, p) for p in maraka],
            "dushthana_lords": [DE.get(p, p) for p in dush_lords]}


def _render_lifespan(chart: Dict) -> str:
    ls = compute_lifespan(chart)
    col = {"+": "#7dbb7d", "−": "#c96a5a", "·": "var(--mu)"}
    body = "".join(
        f"<tr><td style='white-space:nowrap'>{crit}</td><td>{txt}</td>"
        f"<td style='text-align:center;font-weight:700;color:{col[mk]}'>{mk}</td></tr>"
        for crit, txt, mk in ls["rows"])
    return (
        f"<p class='sh'>Lebensspannen-Checkliste <span style='color:#c96a5a'>"
        f"(nur Test-Modus)</span></p>"
        f"<div style='border:1px solid #c96a5a;border-radius:8px;padding:10px 14px;"
        f"font-size:.78rem;line-height:1.5;color:var(--mu);margin-bottom:12px'>"
        f"Interne Analyse nach der klassischen Checkliste — erscheint NIE in "
        f"Kundenberichten. Sie beschreibt stützende und belastende Faktoren, "
        f"keine Vorhersage und keine Jahreszahlen. Klassisch entscheidet die "
        f"Daśā-Sequenz: Auslösungen der unten genannten Herren im "
        f"Viṃśottarī-Tab prüfen, zusammen mit Sade Sati / Śani Aṣṭamī.</div>"
        f"<div class='ow'><table class='dt'><thead><tr><th>Kriterium</th>"
        f"<th>Befund</th><th>±</th></tr></thead><tbody>{body}</tbody></table></div>"
        f"<p style='font-size:.86rem;margin-top:10px'><strong>Bilanz:</strong> "
        f"{ls['tendency']} (Saldo {ls['score']:+d}) · "
        f"{'Taggeburt' if ls['day_birth'] else 'Nachtgeburt'} (Whole-Sign-Näherung)"
        f"</p>"
        f"<p style='font-size:.82rem;color:var(--mu)'>Für die Daśā-Prüfung: "
        f"Maraka-Herren (H2/H7): {', '.join(ls['maraka_lords'])} · "
        f"Dushthana-Herren (H6/H8/H12): {', '.join(ls['dushthana_lords'])}.</p>")


# ══════════════════════════════════════════════════════════════════════════════
# Gesamtberechnung + Tab-HTML
# ══════════════════════════════════════════════════════════════════════════════

def compute(chart: Dict) -> Dict:
    doshas = compute_doshas(chart)
    gunas = compute_gunas(chart)
    kap = compute_kap(chart)
    focus = compute_focus(chart, kap)
    return {"doshas": doshas, "gunas": gunas, "kap": kap, "focus": focus}


_DISCLAIMER = (
    "Dieser Abschnitt beschreibt die <strong>klassische ayurvedisch-jyotische "
    "Sichtweise</strong> auf Konstitution und Zeitqualität. Er ist keine "
    "medizinische Beratung, Diagnose oder Therapieempfehlung und ersetzt "
    "keinen Arztbesuch. Bei gesundheitlichen Beschwerden wende dich bitte "
    "immer an eine Ärztin oder einen Arzt.")


def render_tab(chart: Dict) -> str:
    """Kompletter innerer HTML-Inhalt des Medizin-Tabs (Dark-Theme-Klassen
    des Report-Viewers: .sh, .ow, table.dt, CSS-Variablen --ac/--mu/--tx)."""
    med = compute(chart)
    d, g, kap, focus = med["doshas"], med["gunas"], med["kap"], med["focus"]

    # ── Konstitution ──────────────────────────────────────────────────────
    prim, sec = d["primary"], d["secondary"]
    prof = DOSHA_PROFILE[prim]
    dosha_cards = (
        f"<div style='display:flex;gap:14px;flex-wrap:wrap;margin:10px 0 4px'>"
        f"<div style='flex:1;min-width:240px;border:1px solid var(--ac);"
        f"border-radius:10px;padding:14px 16px'>"
        f"<div style='color:var(--ac);font-size:1.05rem;font-weight:600'>"
        f"Prim&auml;r: {prim}</div>"
        f"<div style='color:var(--mu);font-size:.8rem;margin:2px 0 8px'>{prof[0]}</div>"
        f"<div style='font-size:.86rem;line-height:1.5'>{prof[1]}</div>"
        f"<div style='font-size:.82rem;line-height:1.5;color:var(--mu);"
        f"margin-top:8px'>{prof[2]}</div></div>")
    if sec:
        sprof = DOSHA_PROFILE[sec]
        dosha_cards += (
            f"<div style='flex:1;min-width:240px;border:1px solid "
            f"rgba(255,255,255,.14);border-radius:10px;padding:14px 16px'>"
            f"<div style='font-size:1.0rem;font-weight:600'>Sekund&auml;r: {sec}</div>"
            f"<div style='color:var(--mu);font-size:.8rem;margin:2px 0 8px'>{sprof[0]}</div>"
            f"<div style='font-size:.84rem;line-height:1.5;color:var(--mu)'>{sprof[1]}</div>"
            f"</div>")
    dosha_cards += "</div>"

    deriv = "".join(
        f"<tr><td style='white-space:nowrap'>{lbl}</td><td>{txt}</td></tr>"
        for lbl, txt in d["derivation"])
    sc = d["scores"]
    dosha_html = (
        dosha_cards +
        f"<div class='ow'><table class='dt'><thead><tr><th>Ebene</th>"
        f"<th>Einfl&uuml;sse &rarr; Dosha</th></tr></thead><tbody>{deriv}"
        f"<tr><td><strong>Gewichtung</strong></td><td>Vata {sc['Vata']} &middot; "
        f"Pitta {sc['Pitta']} &middot; Kapha {sc['Kapha']} &mdash; Lagna doppelt "
        f"gewichtet; das Lagna-Zeichen z&auml;hlt nur ohne Planeteneinfl&uuml;sse."
        f"</td></tr></tbody></table></div>")

    # ── Gunas ─────────────────────────────────────────────────────────────
    gc = g["counts"]
    total = sum(gc.values()) or 1
    bar = "".join(
        f"<div style='flex:{gc[k]};background:{col};min-width:{'2px' if gc[k] else '0'};"
        f"height:10px'></div>"
        for k, col in (("Sattva", "#d9c27a"), ("Rajas", "#b06a5a"),
                       ("Tamas", "#5a6b8c")))
    guna_rows = "".join(
        f"<tr><td>{p}</td><td>{nak}</td><td>{lord}</td><td>{gu}</td></tr>"
        for p, nak, lord, gu in g["rows"])
    guna_html = (
        f"<p style='font-size:.9rem'><strong>{gc['Sattva']} &times; Sattva &middot; "
        f"{gc['Rajas']} &times; Rajas &middot; {gc['Tamas']} &times; Tamas</strong> "
        f"&mdash; dominant: {g['dominant']}</p>"
        f"<div style='display:flex;border-radius:5px;overflow:hidden;"
        f"margin:6px 0 10px'>{bar}</div>"
        f"<p style='font-size:.84rem;color:var(--mu);line-height:1.5'>"
        f"{GUNA_PROFILE[g['dominant']]}"
        + (f" {g['note']}" if g["note"] else "") + "</p>"
        f"<details style='margin:8px 0 0'><summary style='cursor:pointer;"
        f"color:var(--mu);font-size:.8rem'>Herleitung &uuml;ber die "
        f"Nakshatra-Herrscher anzeigen</summary>"
        f"<div class='ow'><table class='dt'><thead><tr><th>Punkt</th>"
        f"<th>Nakshatra</th><th>Herrscher</th><th>Guna</th></tr></thead>"
        f"<tbody>{guna_rows}</tbody></table></div></details>")

    # ── KAP-Matrix ────────────────────────────────────────────────────────
    head = "".join(f"<th>{DE[c]}</th>" for c in KAP_COLS)
    body = ""
    for label, marks in kap["rows"]:
        cells = "".join(
            f"<td style='text-align:center'>{'x' * marks.get(c, 0) or ''}</td>"
            for c in KAP_COLS)
        body += f"<tr><td>{label}</td>{cells}</tr>"
    tot = kap["totals"]
    tot_cells = "".join(
        f"<td style='text-align:center;font-weight:700;"
        f"color:{'var(--ac)' if tot[c] >= 3 else 'inherit'}'>{tot[c]}</td>"
        for c in KAP_COLS)
    kap_html = (
        f"<p style='font-size:.84rem;color:var(--mu);line-height:1.5'>"
        f"Klassische Belastungskriterien je Planet (KAP &mdash; "
        f"krankheitsanzeigende Punkte). Hohe Summen zeigen, welche Grahas in "
        f"diesem Horoskop gesundheitlich sensibel wirken &mdash; besonders "
        f"relevant, wenn sie in Da&scaron;&#257;-Phasen ausgel&ouml;st werden.</p>"
        f"<div class='ow'><table class='dt'><thead><tr><th>Kriterium</th>{head}"
        f"</tr></thead><tbody>{body}<tr><td><strong>Summe</strong></td>{tot_cells}"
        f"</tr></tbody></table></div>")

    # ── Fokusbereiche ─────────────────────────────────────────────────────
    focus_html = ""
    if focus["h6_h8_meet"]:
        m = focus["h6_h8_meet"]
        focus_html += (
            f"<p style='font-size:.86rem;border-left:3px solid var(--ac);"
            f"padding-left:10px'>{m['lords']} treffen sich in Haus {m['house']} "
            f"({m['sign']}) &mdash; dieser Bereich verdient klassisch die "
            f"gr&ouml;sste Aufmerksamkeit.</p>")
    if focus["items"]:
        rows_f = "".join(
            f"<tr><td>Haus {it['house']} &middot; {it['sign']}</td>"
            f"<td>{it['body_house']}<br><span style='color:var(--mu)'>"
            f"Zeichen: {it['body_sign']}</span></td>"
            f"<td>{', '.join(it['who'][:5])}</td>"
            f"<td style='text-align:center'>{it['score']}</td></tr>"
            for it in focus["items"])
        focus_html += (
            f"<p style='font-size:.84rem;color:var(--mu);line-height:1.5'>"
            f"Bereiche, in denen sich die punktst&auml;rksten Planeten sammeln "
            f"(Besetzung voll, Aspekte halb gewichtet) &mdash; als Einladung zu "
            f"Achtsamkeit und Vorsorge, nicht als Befund.</p>"
            f"<div class='ow'><table class='dt'><thead><tr><th>Bereich</th>"
            f"<th>K&ouml;rperzuordnung (K&#257;lapuru&#7779;a)</th>"
            f"<th>Beteiligte</th><th>Punkte</th></tr></thead>"
            f"<tbody>{rows_f}</tbody></table></div>")

    # ── Referenztabellen ──────────────────────────────────────────────────
    sign_rows = "".join(
        f"<tr><td>{SIGN_DE[s]}</td><td>{SIGN_BODY[s]}</td></tr>" for s in SIGNS)
    org_rows = "".join(
        f"<tr><td>{DE[p]}</td><td>{PLANET_ORGANS[p]}</td>"
        f"<td style='color:var(--mu)'>{PLANET_TENDENCY[p]}</td></tr>"
        for p in GRAHAS)
    ref_html = (
        f"<details style='margin-top:6px'><summary style='cursor:pointer;"
        f"color:var(--mu);font-size:.82rem'>Referenz: Zeichen &rarr; "
        f"K&ouml;rperbereiche (K&#257;lapuru&#7779;a)</summary>"
        f"<div class='ow'><table class='dt'><thead><tr><th>Zeichen</th>"
        f"<th>K&ouml;rperbereich</th></tr></thead><tbody>{sign_rows}</tbody>"
        f"</table></div></details>"
        f"<details style='margin-top:6px'><summary style='cursor:pointer;"
        f"color:var(--mu);font-size:.82rem'>Referenz: Planeten &rarr; Organe "
        f"&amp; Tendenzen</summary>"
        f"<div class='ow'><table class='dt'><thead><tr><th>Graha</th>"
        f"<th>Organe / K&#257;raka</th><th>Tendenz</th></tr></thead>"
        f"<tbody>{org_rows}</tbody></table></div></details>")

    src_html = (
        "<p style='font-size:.74rem;color:var(--mu);margin-top:16px'>"
        "Methodik: klassische ayurvedisch-jyotische Zuordnungen (BPHS; "
        "K.S. Charak, <em>Essentials of Medical Astrology</em>; V. Lad, "
        "<em>Ayurveda &mdash; The Science of Self-Healing</em>). "
        "Konstitution nach Einfl&uuml;ssen auf Lagna, 6. Haus und Mond; "
        "Gunas &uuml;ber die Nakshatra-Herrscher.</p>")

    lifespan_html = _render_lifespan(chart) if chart.get("show_lifespan") else ""

    return (
        f"<div style='border:1px solid rgba(217,194,122,.5);border-radius:8px;"
        f"padding:10px 14px;font-size:.8rem;line-height:1.5;color:var(--mu);"
        f"margin-bottom:14px'>{_DISCLAIMER}</div>"
        f"<p class='sh'>Ayurvedische Konstitution (Prak&#7771;ti)</p>{dosha_html}"
        f"<p class='sh'>Mentale Konstitution (Gunas)</p>{guna_html}"
        f"<p class='sh'>Sensible Planeten (KAP-Punkte)</p>{kap_html}"
        f"<p class='sh'>Bereiche erh&ouml;hter Aufmerksamkeit</p>{focus_html}"
        f"<p class='sh'>Klassische Zuordnungen</p>{ref_html}{lifespan_html}{src_html}")

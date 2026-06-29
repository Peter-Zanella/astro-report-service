"""
ai_report.py — structured Jyotiṣa interpretation using the Anthropic API.

Methodology (classical sequence):
  1. D1 Rāśi from Lagna  — fundamental nature, body, dharma
  2. D1 Rāśi from Moon   — mind, emotions, inner world
  3. D9 Navāṃśa          — soul-level strengths, marriage, dharma fulfillment
  4. D10 Daśāṃśa         — career, public role, professional karma
  5. D3 Drekkāna         — vitality, siblings, courage
  6. D4 Chaturthamsha    — property, home, fixed assets
  7. Afflictions         — combustion, Papakartari, debilitation, retrograde,
                           Gandanta, Graha Yuddha
  8. Aspects             — Graha Drishti, Rāśi Drishti, special aspects
  9. Yogas               — weighted by Shad Bala strength
 10. Timing              — Viṃśottarī Daśā (maha/antar/pratyantar)
 11. Varshaphala         — solar return year (if depth='year')

Key principle: the LLM NEVER computes astrological positions.
It only interprets the exact facts the engine already calculated.
"""

from __future__ import annotations
import json, os
from typing import Dict, Optional


# ─────────────────────────────────────────────────────────────────────────────
# 1. FACTS EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

SIGNS = ["Aries","Taurus","Gemini","Cancer","Leo","Virgo",
         "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"]

MALEFICS = {"Sun","Mars","Saturn","Rahu","Ketu"}
BENEFICS = {"Moon","Mercury","Jupiter","Venus"}

# Gandanta zones: last 3°20' of water signs / first 3°20' of fire signs
_GANDANTA = {
    "Cancer": (26.67, 30), "Scorpio": (26.67, 30), "Pisces": (26.67, 30),
    "Aries":  (0, 3.33),   "Leo":     (0, 3.33),   "Sagittarius": (0, 3.33),
}

def _deg_in_sign(pos_str: str) -> float:
    """Parse '7° 48\\'' → 7.8"""
    try:
        parts = str(pos_str).replace("°","°").replace("'","").split("°")
        deg = float(parts[0].strip())
        mins = float(parts[1].strip()) if len(parts) > 1 else 0
        return deg + mins / 60
    except Exception:
        return 0.0

def _build_afflictions(planets: Dict, sun_sign: str, sun_deg: float) -> Dict:
    """Detect all six affliction types from computed planet data."""
    aff = {}
    planet_signs   = {p: d.get("sign","") for p,d in planets.items() if p!="Ascendant"}
    planet_degrees = {p: _deg_in_sign(d.get("pos","0°0'")) for p,d in planets.items() if p!="Ascendant"}
    planet_houses  = {p: d.get("house", 0) for p,d in planets.items() if p!="Ascendant"}

    for pname, pdata in planets.items():
        if pname in ("Ascendant","Sun"): continue
        issues = []

        # 1. Combust (within 6° of Sun, same sign)
        if pdata.get("sign") == sun_sign:
            diff = abs(planet_degrees.get(pname, 0) - sun_deg)
            if diff < 6:
                issues.append(f"combust ({diff:.1f}° from Sun)")

        # 2. Debilitated and not cancelled (neecha bhanga)
        dig = pdata.get("dignity","")
        if "Debil" in dig:
            # Simple neecha bhanga check: lord of debilitation sign in kendra from lagna or moon
            issues.append("debilitated — check for Neecha Bhanga")

        # 3. Retrograde
        if pdata.get("retrograde") or "R" in str(pdata.get("pos","")):
            issues.append("retrograde")

        # 4. Gandanta
        sign = pdata.get("sign","")
        deg  = planet_degrees.get(pname, 0)
        if sign in _GANDANTA:
            lo, hi = _GANDANTA[sign]
            if lo <= deg <= hi:
                issues.append(f"Gandanta ({deg:.1f}° in {sign})")

        if issues:
            aff[pname] = issues

    # 5. Papakartari Yoga: planet hemmed between malefics in adjacent houses
    for pname, pdata in planets.items():
        if pname in ("Ascendant",): continue
        h = planet_houses.get(pname, 0)
        if h == 0: continue
        prev_h, next_h = ((h-2) % 12) + 1, (h % 12) + 1
        prev_mal = [p for p,ph in planet_houses.items() if ph == prev_h and p in MALEFICS]
        next_mal = [p for p,ph in planet_houses.items() if ph == next_h and p in MALEFICS]
        if prev_mal and next_mal:
            entry = aff.get(pname, [])
            entry.append(f"Papakartari (between {prev_mal[0]} H{prev_h} and {next_mal[0]} H{next_h})")
            aff[pname] = entry

    # 6. Graha Yuddha (planetary war): two planets within 1° in same sign (excl. Sun/Moon/nodes)
    yuddha_planets = [p for p in planets if p not in ("Sun","Moon","Rahu","Ketu","Ascendant")]
    for i, p1 in enumerate(yuddha_planets):
        for p2 in yuddha_planets[i+1:]:
            if planets[p1].get("sign") == planets[p2].get("sign"):
                diff = abs(planet_degrees.get(p1,0) - planet_degrees.get(p2,0))
                if diff < 1.0:
                    for p in (p1, p2):
                        entry = aff.get(p, [])
                        entry.append(f"Graha Yuddha with {p2 if p==p1 else p1} ({diff:.2f}°)")
                        aff[p] = entry

    return aff


def _build_aspects(planets: Dict, lagna_idx: int) -> Dict:
    """Build Graha Drishti and special aspects from house positions."""
    aspects = {}
    planet_houses = {p: d.get("house", 0) for p,d in planets.items() if p!="Ascendant"}

    # Standard Graha Drishti: all planets aspect 7th from themselves
    # Special: Mars→4,8; Jupiter→5,9; Saturn→3,10; Rahu/Ketu→5,9
    SPECIAL = {
        "Mars":    [4, 8],
        "Jupiter": [5, 9],
        "Saturn":  [3, 10],
        "Rahu":    [5, 9],
        "Ketu":    [5, 9],
    }

    for p1, h1 in planet_houses.items():
        if h1 == 0: continue
        aspected_houses = {((h1 + 6 - 1) % 12) + 1}  # 7th aspect (all planets)
        for offset in SPECIAL.get(p1, []):
            aspected_houses.add(((h1 + offset - 2) % 12) + 1)

        for p2, h2 in planet_houses.items():
            if p2 == p1 or h2 == 0: continue
            if h2 in aspected_houses:
                entry = aspects.get(p1, [])
                entry.append(f"aspects {p2} in H{h2}")
                aspects[p1] = entry
                # also record who receives
                recv = aspects.get(p2, [])
                recv.append(f"receives aspect from {p1} (H{h1})")
                aspects[p2] = recv

    return aspects


def _build_divisional_summary(chart: Dict) -> Dict:
    """Extract D1/D9/D10/D3/D4 Lagna and planet placements."""
    out = {}
    SIGNS_L = SIGNS

    for key, name in [("d9","D9 Navāṃśa"),("d10","D10 Daśāṃśa"),
                       ("d3","D3 Drekkāna"),("d4","D4 Chaturthamsha")]:
        div = chart.get(key, {})
        if not div: continue
        asc_si = div.get("Ascendant")
        lagna = SIGNS_L[asc_si % 12] if isinstance(asc_si, int) else "—"
        placements = {p: SIGNS_L[si % 12] for p,si in div.items()
                      if p != "Ascendant" and isinstance(si, int)}
        out[name] = {"lagna": lagna, "planets": placements}

    return out


def _build_varshaphala_facts(chart: Dict) -> Dict:
    """Extract Varshaphala (solar return) facts."""
    vp = chart.get("varshaphala", {})
    if not vp:
        return {}
    out = {
        "year":         vp.get("year"),
        "solar_return": str(vp.get("solar_return_utc", "")),
        "lagna":        vp.get("lagna"),
        "lagna_pos":    vp.get("lagna_pos"),
        "muntha":       vp.get("muntha"),
        "muntha_lord":  vp.get("muntha_lord"),
        "varsha_pati":  vp.get("varsha_pati"),
        "planets":      {},
    }
    for p, pd in vp.get("planets", {}).items():
        if p == "Ascendant": continue
        out["planets"][p] = {
            "sign":  pd.get("sign"),
            "house": pd.get("house"),
            "dignity": pd.get("dignity"),
        }
    return out


def build_facts(chart: Dict, depth: str = "premium") -> str:
    """Build the complete structured facts block for the LLM."""
    f: Dict = {}
    pls = chart.get("planets", {})

    # ── Lagna ──────────────────────────────────────────────────────────────
    li = chart.get("lagna_idx")
    f["lagna"] = {
        "sign":    SIGNS[li] if li is not None else None,
        "pos":     chart.get("lagna_pos"),
        "lord":    chart.get("lagna_lord"),
        "lord_house": pls.get(chart.get("lagna_lord", ""), {}).get("house"),
    }

    # ── Moon (Chandra Lagna) ───────────────────────────────────────────────
    moon = pls.get("Moon", {})
    f["moon"] = {
        "sign":      moon.get("sign"),
        "house":     moon.get("house"),
        "nakshatra": moon.get("nakshatra"),
        "pada":      moon.get("pada"),
        "dignity":   moon.get("dignity"),
    }

    # ── All planets from D1 ────────────────────────────────────────────────
    f["planets"] = {}
    sun_sign = pls.get("Sun", {}).get("sign", "")
    sun_deg  = _deg_in_sign(pls.get("Sun", {}).get("pos", "0°0'"))

    for p, d in pls.items():
        if p == "Ascendant": continue
        f["planets"][p] = {
            "sign":      d.get("sign"),
            "house":     d.get("house"),
            "nakshatra": d.get("nakshatra"),
            "pada":      d.get("pada"),
            "dignity":   d.get("dignity"),
            "nak_lord":  d.get("nak_lord"),
            "pos":       d.get("pos"),
            "retrograde": d.get("retrograde", False),
        }

    # ── Houses ────────────────────────────────────────────────────────────
    f["houses"] = chart.get("houses", {})
    f["occupants"] = {str(h): v for h, v in chart.get("occupants", {}).items()}

    # ── Afflictions ───────────────────────────────────────────────────────
    f["afflictions"] = _build_afflictions(pls, sun_sign, sun_deg)

    # ── Aspects ───────────────────────────────────────────────────────────
    f["aspects"] = _build_aspects(pls, li or 0)

    # ── Divisional charts ─────────────────────────────────────────────────
    f["divisional"] = _build_divisional_summary(chart)

    # ── Yogas ────────────────────────────────────────────────────────────
    f["yogas"] = [{"name": y.get("name"), "group": y.get("group",""),
                   "planets": y.get("planets",""), "detail": y.get("detail","")}
                  for y in chart.get("yogas", [])]

    # ── Shad Bala ────────────────────────────────────────────────────────
    sb = chart.get("shadbala", {})
    if sb:
        P = sb.get("planets", {})
        f["shadbala"] = {
            p: {"rupa": P[p].get("rupa"), "strong": P[p].get("strong"),
                "ishta": P[p].get("ishta"), "kashta": P[p].get("kashta")}
            for p in sb.get("order", []) if p in P
        }
        f["shadbala_strongest"] = sb.get("order", [None])[0]
        f["shadbala_weakest"]   = sb.get("order", [None])[-1]

    # ── Bhava Bala ───────────────────────────────────────────────────────
    bb = chart.get("bhavabala", {})
    if bb:
        f["bhavabala_strongest"] = bb.get("order", [None])[0]
        f["bhavabala_weakest"]   = bb.get("order", [None])[-1]
        f["bhavabala_houses"]    = {str(h): v.get("rupa")
                                    for h, v in bb.get("houses", {}).items()}

    # ── Jaimini ──────────────────────────────────────────────────────────
    jai = chart.get("jaimini", {})
    if jai:
        f["jaimini"] = {
            "atmakaraka":    jai.get("atmakaraka"),
            "amatyakaraka":  jai.get("amatyakaraka"),
            "darakaraka":    jai.get("darakaraka"),
            "karakamsha":    jai.get("karakamsha"),
            "arudha_lagna":  jai.get("arudha_lagna"),
            "upapada_lagna": jai.get("upapada_lagna"),
        }

    # ── Chara Dasha current ───────────────────────────────────────────────
    chara = chart.get("chara_dasha", {})
    if chara:
        cur = chara.get("current", {})
        f["chara_dasha_current"] = {
            "mahadasha": cur.get("maha_sign"),
            "antardasha": cur.get("antar_sign"),
        }

    # ── Viṃśottarī Daśā ──────────────────────────────────────────────────
    dashas = chart.get("dashas", {})
    if dashas:
        cur = dashas.get("current", {})
        f["vimshottari_current"] = {
            "mahadasha":       cur.get("maha"),
            "antardasha":      cur.get("antar"),
            "pratyantardasha": cur.get("pratyantar"),
        }
        for maha_entry in dashas.get("mahadashas", []):
            if maha_entry.get("active"):
                f["vimshottari_current"]["mahadasha_end"] = str(maha_entry.get("end",""))
                for antar in maha_entry.get("antardashas", []):
                    if antar.get("active"):
                        f["vimshottari_current"]["antardasha_start"] = str(antar.get("start",""))
                        f["vimshottari_current"]["antardasha_end"]   = str(antar.get("end",""))
                        for pad in antar.get("pratyantardashas", []):
                            if pad.get("active"):
                                f["vimshottari_current"]["pratyantardasha_end"] = str(pad.get("end",""))
                        break
                break

    # ── Panchang ─────────────────────────────────────────────────────────
    pan = chart.get("panchang", {})
    if pan:
        f["panchang"] = {k: pan.get(k) for k in
                         ("tithi","vara","vara_lord","nakshatra","nakshatra_lord","yoga","karana")}

    # ── Varshaphala (year depth) ──────────────────────────────────────────
    if depth == "year":
        vp_facts = _build_varshaphala_facts(chart)
        if vp_facts:
            f["varshaphala"] = vp_facts

    # ── Meta ──────────────────────────────────────────────────────────────
    meta = chart.get("meta", {})
    f["meta"] = {
        "name":     meta.get("name"),
        "gender":   meta.get("gender"),
        "birth":    meta.get("birth"),
        "location": meta.get("location"),
    }

    return json.dumps(f, ensure_ascii=False, indent=1, default=str)


# ─────────────────────────────────────────────────────────────────────────────
# 2. SYSTEM PROMPTS
# ─────────────────────────────────────────────────────────────────────────────

_BASE_RULES = {
    "de": """Du bist ein erfahrener Jyotiṣa-Astrologe und schreibst einen persönlichen Bericht.

STRENGE REGELN:
• Du deutest AUSSCHLIESSLICH die im JSON gelieferten, bereits berechneten Fakten.
• Du berechnest, veränderst oder erfindest KEINE Positionen, Zeichen, Grade oder Daten.
• Schreibe klar, warm und tiefgründig auf Deutsch. Erkläre Sanskrit-Begriffe kurz beim ersten Auftreten.
• Keine medizinischen, rechtlichen oder finanziellen Ratschläge. Keine Schicksalssprache.
• Keine garantierten Vorhersagen — nur Tendenzen, Energien und Zeitfenster.
• Strukturiere den Text exakt mit den vorgegebenen Markdown-Abschnittsüberschriften (##).

METHODISCHE PRINZIPIEN (die du anwenden sollst):
1. GEWICHTUNG: Ein Planet ist stärker wenn er (a) hohe Shad-Bala-Rupas hat, (b) in einem Kendra/Trikona steht, (c) im eigenen Zeichen oder erhöht ist. Schwächere Planeten werden entsprechend relativiert.
2. AFFLICTIONS: Benenne explizit wenn ein Planet verbrannt (combusted), geschwächt (debilitated), retrograd, in Gandanta, in Graha Yuddha oder in Papakartari steht — und erkläre was das für die betreffende Lebenssphäre bedeutet.
3. DIVISIONALCHARTS: Nutze D9 (Navāṃśa) um die Tiefenqualität eines Planeten zu bestätigen oder zu relativieren. Nutze D10 (Daśāṃśa) für Beruf, D3 (Drekkāna) für Vitalität, D4 (Chaturthamsha) für Immobilien/Heimat. Nur wenn diese Daten im JSON vorhanden sind.
4. ASPEKTE: Berücksichtige explizit die Graha Drishti (Jupiter auf 5./9., Mars auf 4./8., Saturn auf 3./10.) und deren Wirkung auf die aspektierten Häuser und Planeten.
5. TIMING: Im Daśā-Abschnitt verwende NUR die Planeten aus 'vimshottari_current'. Benenne Maha, Antar und Pratyantardaśā exakt wie im JSON angegeben.
6. QUALIFIZIERE: Wenn ein Yoga durch eine Affliction abgeschwächt wird, sage das. Wenn ein Defizit durch andere Faktoren ausgeglichen wird, sage das auch.""",

    "en": """You are an experienced Jyotiṣa astrologer writing a personalised chart report.

STRICT RULES:
• Interpret ONLY the already-calculated facts provided in the JSON below.
• Do NOT compute, alter or invent any positions, signs, degrees or dates.
• Write clearly, warmly and with depth in English. Briefly explain Sanskrit terms on first use.
• No medical, legal or financial advice. No fate or doom language. No guaranteed predictions.
• Structure the text exactly with the given Markdown section headings (##).

METHODOLOGICAL PRINCIPLES (to apply):
1. WEIGHTING: A planet is stronger when it has (a) high Shad Bala rupas, (b) is in a Kendra/Trikona, (c) is in its own sign or exalted. Qualify weaker planets accordingly.
2. AFFLICTIONS: Explicitly name when a planet is combust, debilitated, retrograde, in Gandanta, in Graha Yuddha or in Papakartari — and explain what this means for the life area concerned.
3. DIVISIONAL CHARTS: Use D9 (Navāṃśa) to confirm or qualify a planet's deeper quality. Use D10 (Daśāṃśa) for career, D3 (Drekkāna) for vitality, D4 (Chaturthamsha) for property/home. Only where data is present in the JSON.
4. ASPECTS: Explicitly consider Graha Drishti (Jupiter on 5th/9th, Mars on 4th/8th, Saturn on 3rd/10th) and their effect on aspected houses and planets.
5. TIMING: In the Daśā section use ONLY the planets from 'vimshottari_current'. Name Maha, Antar and Pratyantardaśā exactly as given in the JSON.
6. QUALIFY: If a Yoga is weakened by an affliction, say so. If a deficit is compensated by other factors, say that too.""",
}


# ─────────────────────────────────────────────────────────────────────────────
# 3. SECTION DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────

_SECTIONS = {
    "de": {
        "basis": [
            "Aszendent & Grundwesen",
            "Mond & Gefühlswelt",
            "Kernthemen & Stärken",
            "Ein Hinweis für den Alltag",
        ],
        "premium": [
            "Aszendent & Grundwesen (D1 vom Lagna)",
            "Mond, Nakshatra & Gefühlswelt (D1 vom Mond)",
            "Stärken, Yogas & Shad Bala",
            "Affliktionen & Herausforderungen",
            "Aspekte & Planetarische Beziehungen",
            "Navāṃśa (D9) — Seelenqualität & Ehe",
            "Daśāṃśa (D10) — Beruf & Karriere",
            "Drekkāna (D3) & Chaturthamsha (D4)",
            "Beziehungen & Partnerschaft",
            "Aktuelles Timing (Viṃśottarī Daśā)",
            "Jaimini — Ātmakāraka & Arudha",
            "Zusammenfassung",
        ],
        "year": [
            "Aszendent & Grundwesen (D1 vom Lagna)",
            "Mond, Nakshatra & Gefühlswelt",
            "Stärken, Yogas & Shad Bala",
            "Affliktionen & Herausforderungen",
            "Aspekte & Planetarische Beziehungen",
            "Navāṃśa (D9) — Seelenqualität",
            "Daśāṃśa (D10) — Beruf & Karriere",
            "Aktuelles Timing (Viṃśottarī Daśā)",
            "Varshaphala — Das Jahr im Überblick",
            "Varshaphala — Themen & Chancen des Jahres",
            "Varshaphala — Herausforderungen & Timing",
            "Zusammenfassung",
        ],
    },
    "en": {
        "basis": [
            "Ascendant & core nature",
            "Moon & emotional world",
            "Key themes & strengths",
            "A note for daily life",
        ],
        "premium": [
            "Ascendant & core nature (D1 from Lagna)",
            "Moon, nakshatra & emotional world (D1 from Moon)",
            "Strengths, yogas & Shad Bala",
            "Afflictions & challenges",
            "Aspects & planetary relationships",
            "Navāṃśa (D9) — soul quality & marriage",
            "Daśāṃśa (D10) — career & vocation",
            "Drekkāna (D3) & Chaturthamsha (D4)",
            "Relationships & partnership",
            "Current timing (Viṃśottarī Daśā)",
            "Jaimini — Ātmakāraka & Arudhā",
            "Summary",
        ],
        "year": [
            "Ascendant & core nature (D1 from Lagna)",
            "Moon, nakshatra & emotional world",
            "Strengths, yogas & Shad Bala",
            "Afflictions & challenges",
            "Aspects & planetary relationships",
            "Navāṃśa (D9) — soul quality",
            "Daśāṃśa (D10) — career & vocation",
            "Current timing (Viṃśottarī Daśā)",
            "Varshaphala — the year at a glance",
            "Varshaphala — themes & opportunities",
            "Varshaphala — challenges & timing",
            "Summary",
        ],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# 4. SECTION INSTRUCTIONS
# ─────────────────────────────────────────────────────────────────────────────

_SECTION_GUIDES = {
    "de": {
        "Aszendent & Grundwesen (D1 vom Lagna)":
            "Deute das Lagna-Zeichen, seinen Herrn (Position, Würde, Haus), "
            "alle Planeten im 1. Haus und deren Affliktionen. Berücksichtige "
            "Aspekte auf das Lagna. Nutze den D9-Lagna-Herrn zur Vertiefung. "
            "Vergleiche Lagna-Herrn im Natal vs. D9.",
        "Mond, Nakshatra & Gefühlswelt (D1 vom Mond)":
            "Zähle die Häuser neu vom Mond (Chandra Lagna). Deute die Qualität "
            "des Mondes (Zeichen, Nakshatra, Pada, Würde, Affliktionen). "
            "Erkläre die emotionale Grundstruktur, das innere Erleben, "
            "und wie der Mond-Atsmakaraka (wenn zutreffend) wirkt.",
        "Stärken, Yogas & Shad Bala":
            "Nenne die wichtigsten Yogas (Raja, Dhana, Lakshmi etc.) und "
            "qualifiziere sie durch Shad Bala. Wenn ein Yoga-Planet schwach ist "
            "(niedrige Rupas, Affliktion), sage das. Benenne den stärksten und "
            "schwächsten Planeten nach Shad Bala und was das praktisch bedeutet.",
        "Affliktionen & Herausforderungen":
            "Gehe durch alle Affliktionen im JSON-Feld 'afflictions'. "
            "Erkläre für jeden betroffenen Planeten: Was ist die Afliktion? "
            "Welche Lebenssphären (Häuser) sind betroffen? Gibt es mildernde "
            "Faktoren (Neecha Bhanga, starke Aspekte von Benefics)? "
            "Wie äussert sich das konkret im Leben?",
        "Aspekte & Planetarische Beziehungen":
            "Hebe die bedeutendsten Aspekte hervor: Jupiter's 5./9. Aspekt, "
            "Mars' 4./8. Aspekt, Saturn's 3./10. Aspekt und deren Wirkung "
            "auf die aspektierten Häuser. Erkläre Graha Drishti-Verbindungen "
            "zwischen Planeten und wie sie die Energien mischen.",
        "Navāṃśa (D9) — Seelenqualität & Ehe":
            "Nutze den D9-Lagna, D9-Planeten und deren Zeichen. Vergleiche "
            "wichtige Planeten (bes. Venus, 7. Herr) in D1 vs. D9. "
            "Vargottama-Planeten (gleich in D1 und D9) besonders erwähnen. "
            "Deute was das für die spirituelle Entwicklung und Ehe bedeutet.",
        "Daśāṃśa (D10) — Beruf & Karriere":
            "Nutze D10-Lagna, D10-Planeten. Vergleiche 10. Haus-Herrn in D1 "
            "vs. D10. Sun und Saturn in D10 besonders wichtig. "
            "Deute die berufliche Richtung, Erfolgspotenzial und Karriere-Karma.",
        "Drekkāna (D3) & Chaturthamsha (D4)":
            "D3: Deute Vitalität, Ausdauer, Geschwisterthemen vom D3-Lagna. "
            "D4: Deute Heimat, Immobilien, festes Vermögen vom D4-Lagna. "
            "Halte diese Abschnitte kompakt (je 1 Paragraph).",
        "Beziehungen & Partnerschaft":
            "Analysiere das 7. Haus (Zeichen, Herr, Position des Herrn, "
            "Aspekte auf das 7. Haus). Venus als natürlicher Karaka. "
            "7. Herr in D9 (Upapada Lagna wenn vorhanden). "
            "Qualifiziere durch Affliktionen des 7. Herrn oder Venus.",
        "Aktuelles Timing (Viṃśottarī Daśā)":
            "Verwende AUSSCHLIESSLICH die Planeten aus 'vimshottari_current'. "
            "Erkläre Mahādaśā-Planet (Haus, Zeichen, Würde, Lordschaft), "
            "dann Antaradaśā-Planet, dann Pratyantardaśā-Planet. "
            "Benenne das Enddatum der Antaradaśā explizit. "
            "Was aktiviert diese Kombination konkret im Leben jetzt?",
        "Jaimini — Ātmakāraka & Arudhā":
            "Deute den Ātmakāraka (Seelen-Signifikator) und seinen D1/D9-Stand. "
            "Erkläre den Arudhā Lagna (äussere Wahrnehmung) und Upapada Lagna. "
            "Halte kompakt auf 1–2 Paragraphen.",
        "Varshaphala — Das Jahr im Überblick":
            "Nutze NUR Daten aus 'varshaphala' im JSON. "
            "Erkläre: Jahreslagna, Muntha (Haus und Zeichen), Varsha Pati. "
            "Was ist der Grundton dieses Solarjahres? Welche Häuser sind aktiviert?",
        "Varshaphala — Themen & Chancen des Jahres":
            "Analysiere die stärksten Planeten im Jahreshoroskop (Varshaphala-Planeten). "
            "Welche Jahreshäuser sind gut besetzt? Welche Yogas entstehen im Jahreschart? "
            "Was sind die grössten Chancen und Öffnungen dieses Jahres?",
        "Varshaphala — Herausforderungen & Timing":
            "Welche Planeten stehen schwach oder affliktiert im Jahreschart? "
            "Wie verhält sich der Muntha-Herr? In welchen Monaten (Muntha-Bewegung) "
            "sind besonders intensive Phasen zu erwarten? Concrete Handlungsempfehlungen.",
        "Zusammenfassung":
            "Führe die Hauptthemen des Berichts in 2–3 Paragraphen zusammen. "
            "Nenne die wichtigste Stärke, die grösste Herausforderung und "
            "den wichtigsten aktuellen Zeitimpuls. Schluss mit einer einladenden, "
            "ermutigenden Formulierung — kein Schicksal, sondern Einladung.",
    },
    "en": {
        "Ascendant & core nature (D1 from Lagna)":
            "Interpret the Lagna sign, its lord (position, dignity, house), "
            "all planets in the 1st house and their afflictions. Consider "
            "aspects on the Lagna. Use D9 Lagna lord to deepen. "
            "Compare natal Lagna lord vs. D9.",
        "Moon, nakshatra & emotional world (D1 from Moon)":
            "Count houses from the Moon (Chandra Lagna). Interpret Moon quality "
            "(sign, nakshatra, pada, dignity, afflictions). "
            "Explain the emotional foundation, inner experience, "
            "and how the Moon-Atmakaraka (if applicable) functions.",
        "Strengths, yogas & Shad Bala":
            "Name the key yogas (Raja, Dhana, Lakshmi etc.) and qualify them "
            "by Shad Bala. If a yoga planet is weak (low rupas, affliction), say so. "
            "Name the strongest and weakest planet by Shad Bala and what that means practically.",
        "Afflictions & challenges":
            "Go through all afflictions in the JSON 'afflictions' field. "
            "For each affected planet explain: what is the affliction? "
            "Which life areas (houses) are affected? Are there mitigating factors "
            "(Neecha Bhanga, strong benefic aspects)? How does this manifest practically?",
        "Aspects & planetary relationships":
            "Highlight the most significant aspects: Jupiter's 5th/9th aspect, "
            "Mars' 4th/8th aspect, Saturn's 3rd/10th aspect and their effect "
            "on aspected houses. Explain Graha Drishti connections between "
            "planets and how they blend energies.",
        "Navāṃśa (D9) — soul quality & marriage":
            "Use D9 Lagna, D9 planets and their signs. Compare key planets "
            "(especially Venus, 7th lord) in D1 vs D9. "
            "Mention Vargottama planets (same sign in D1 and D9) explicitly. "
            "Interpret what this means for spiritual development and marriage.",
        "Daśāṃśa (D10) — career & vocation":
            "Use D10 Lagna, D10 planets. Compare 10th house lord in D1 vs D10. "
            "Sun and Saturn in D10 are especially important. "
            "Interpret professional direction, success potential and career karma.",
        "Drekkāna (D3) & Chaturthamsha (D4)":
            "D3: Interpret vitality, endurance, sibling themes from D3 Lagna. "
            "D4: Interpret home, property, fixed assets from D4 Lagna. "
            "Keep compact (1 paragraph each).",
        "Relationships & partnership":
            "Analyse the 7th house (sign, lord, lord's position, aspects on 7th). "
            "Venus as natural karaka. 7th lord in D9 (Upapada Lagna if available). "
            "Qualify through afflictions of the 7th lord or Venus.",
        "Current timing (Viṃśottarī Daśā)":
            "Use ONLY planets from 'vimshottari_current'. "
            "Explain Mahādaśā planet (house, sign, dignity, lordship), "
            "then Antaradaśā planet, then Pratyantardaśā planet. "
            "Name the Antaradaśā end date explicitly. "
            "What does this combination activate concretely in life right now?",
        "Jaimini — Ātmakāraka & Arudhā":
            "Interpret the Ātmakāraka (soul significator) and its D1/D9 placement. "
            "Explain the Arudhā Lagna (outer perception) and Upapada Lagna. "
            "Keep compact at 1–2 paragraphs.",
        "Varshaphala — the year at a glance":
            "Use ONLY data from 'varshaphala' in the JSON. "
            "Explain: year Lagna, Muntha (house and sign), Varsha Pati. "
            "What is the keynote of this solar year? Which houses are activated?",
        "Varshaphala — themes & opportunities":
            "Analyse the strongest planets in the solar return (Varshaphala planets). "
            "Which annual houses are well occupied? What yogas form in the annual chart? "
            "What are the greatest opportunities and openings of this year?",
        "Varshaphala — challenges & timing":
            "Which planets are weak or afflicted in the annual chart? "
            "How does the Muntha lord behave? In which months are particularly "
            "intense phases expected? Concrete practical recommendations.",
        "Summary":
            "Bring together the main themes of the report in 2–3 paragraphs. "
            "Name the key strength, the main challenge and the most important "
            "current timing impulse. Close with an inviting, encouraging formulation — "
            "not fate, but an invitation to self-knowledge.",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# 5. PROMPT BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_prompt(facts: str, lang: str, depth: str) -> str:
    secs = _SECTIONS[lang][depth]
    guides = _SECTION_GUIDES[lang]

    if lang == "de":
        head = ("Hier sind die exakt berechneten Horoskop-Fakten (JSON). "
                "Schreibe den Bericht mit genau diesen Abschnitten in der angegebenen Reihenfolge. "
                "Jeder Abschnitt hat eine Anweisung in [Klammern] — folge ihr genau, "
                "aber schreibe flüssig und persönlich, NICHT wie eine Checkliste.\n\n")
    else:
        head = ("Here are the precisely calculated chart facts (JSON). "
                "Write the report with exactly these sections in the given order. "
                "Each section has an instruction in [brackets] — follow it precisely, "
                "but write fluidly and personally, NOT like a checklist.\n\n")

    sections_txt = "\n".join(
        f"## {s}\n[{guides.get(s, '')}]"
        for s in secs
    )

    return f"{head}{sections_txt}\n\n--- FACTS ---\n{facts}"


# ─────────────────────────────────────────────────────────────────────────────
# 6. MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def generate_interpretation(
    chart: Dict,
    lang: str = "de",
    depth: str = "premium",
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 0,
    varshaphala_age: Optional[int] = None,
) -> str:
    """
    Return the written interpretation.
    depth ∈ {'basis', 'premium', 'year'}

    If depth='year' and varshaphala_age is set, the chart's varshaphala
    should already be computed for that age before calling this function.
    """
    try:
        import anthropic
    except ImportError as e:
        raise RuntimeError("pip install anthropic") from e
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("Set ANTHROPIC_API_KEY in the environment.")

    if depth not in ("basis", "premium", "year"):
        depth = "premium"
    if max_tokens == 0:
        max_tokens = 4000 if depth == "basis" else 10000

    facts  = build_facts(chart, depth=depth)
    system = _BASE_RULES[lang]
    prompt = build_prompt(facts, lang, depth)

    client = anthropic.Anthropic()
    resp   = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    ).strip()


# ─────────────────────────────────────────────────────────────────────────────
# 7. QUICK TEST
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import astro_engine as E
    c = E.generate_chart(
        1957, 8, 24, 13, 55, 47.4845, 7.7345, 1.0,
        "Liestal", "Peter", "Male"
    )
    print(generate_interpretation(c, lang="de", depth="premium"))

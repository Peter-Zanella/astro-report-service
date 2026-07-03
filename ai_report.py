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
def _deg_in_sign(pos_str: str) -> float:
    """Parse '7° 48\\'' → 7.8"""
    try:
        parts = str(pos_str).replace("°","°").replace("'","").split("°")
        deg = float(parts[0].strip())
        mins = float(parts[1].strip()) if len(parts) > 1 else 0
        return deg + mins / 60
    except Exception:
        return 0.0

def _build_divisional_summary(chart: Dict) -> Dict:
    """Read divisional charts (D9/D10/D3/D4) from astro_engine's *_full data.
    All dignity, vargottama, lagna_occupants and VRY come pre-computed."""
    out = {}
    for key, name in [("d9_full","D9 Navamsa"), ("d10_full","D10 Dasamsa"),
                      ("d3_full","D3 Drekkana"), ("d4_full","D4 Chaturthamsha")]:
        full = chart.get(key, {})
        if not full:
            continue
        meta = full.get("_meta", {})
        placements = {p: rec.get("sign") for p, rec in full.items()
                      if p not in ("Ascendant", "_meta")}
        entry = {"lagna": meta.get("lagna"), "planets": placements}
        if meta.get("lagna_occupants"):
            entry["lagna_occupants"] = meta["lagna_occupants"]
        if meta.get("vipareeta_raja_yoga"):
            entry["vipareeta_raja_yoga"] = meta["vipareeta_raja_yoga"]
        out[name] = entry
    return out


def _build_varshaphala_facts(chart: Dict) -> Dict:
    """Extract Varshaphala (solar return) facts. Keys match astro_engine output."""
    vp = chart.get("varshaphala", {})
    if not vp:
        return {}
    # house of each planet relative to the varshaphala lagna
    vp_lagna_si = vp.get("lagna_si", 0)
    out = {
        "year":         vp.get("target_year", vp.get("year")),
        "year_number":  vp.get("year_number"),
        "solar_return": str(vp.get("return_dt_utc", vp.get("solar_return_utc", ""))),
        "lagna":        vp.get("lagna"),
        "lagna_pos":    vp.get("lagna_pos"),
        "muntha":       vp.get("muntha_sign", vp.get("muntha")),
        "muntha_lord":  vp.get("muntha_lord"),
        "varsha_pati":  vp.get("varsha_pati"),
        "planets":      {},
    }
    for p, pd in vp.get("planets", {}).items():
        if p == "Ascendant": continue
        si = pd.get("sign_idx", 0)
        out["planets"][p] = {
            "sign":    pd.get("sign"),
            "house":   ((si - vp_lagna_si) % 12) + 1,
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
    # Get Moon D9 sign directly — do not let LLM infer/calculate it
    d9 = chart.get("d9", {})
    moon_d9_si = d9.get("Moon")
    d9_full = chart.get("d9_full", {})
    moon_d9 = d9_full.get("Moon", {})
    moon_d9_sign = moon_d9.get("sign") or (SIGNS[moon_d9_si % 12] if isinstance(moon_d9_si, int) else None)
    f["moon"] = {
        "sign":      moon.get("sign"),
        "house":     moon.get("house"),
        "nakshatra": moon.get("nakshatra"),
        "pada":      moon.get("pada"),
        "dignity":   moon.get("dignity"),
        "d9_sign":   moon_d9_sign,
        "d9_dignity": moon_d9.get("dignity"),   # from astro_engine — authoritative
    }

    # ── All planets from D1 ────────────────────────────────────────────────
    f["planets"] = {}

    vargottama_planets = []   # planets with same sign in D1 and D9

    for p, d in pls.items():
        if p == "Ascendant": continue
        p_d9 = d9_full.get(p, {})
        p_d9_sign = p_d9.get("sign") or (SIGNS[d9.get(p) % 12] if isinstance(d9.get(p), int) else None)
        is_vargottama = bool(p_d9.get("vargottama"))
        if is_vargottama:
            vargottama_planets.append(p)
        f["planets"][p] = {
            "sign":      d.get("sign"),
            "house":     d.get("house"),
            "nakshatra": d.get("nakshatra"),
            "pada":      d.get("pada"),
            "dignity":   d.get("dignity"),
            "nak_lord":  d.get("nak_lord"),
            "pos":       d.get("pos"),
            "retrograde": d.get("retrograde", False),
            "d9_sign":   p_d9_sign,            # from astro_engine — authoritative
            "d9_dignity": p_d9.get("dignity"), # from astro_engine — authoritative
            "vargottama": is_vargottama,       # from astro_engine — authoritative
        }

    # Authoritative vargottama summary (do not let LLM recompute)
    f["vargottama_planets"] = vargottama_planets

    # ── Houses ────────────────────────────────────────────────────────────
    f["houses"] = chart.get("houses", {})
    f["occupants"] = {str(h): v for h, v in chart.get("occupants", {}).items()}

    # ── Afflictions ───────────────────────────────────────────────────────
    f["afflictions"] = chart.get("afflictions", {})   # from astro_engine

    # ── Aspects ───────────────────────────────────────────────────────────
    f["aspects"] = chart.get("aspects", {})   # from astro_engine

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
        cur_sign = chara.get("current")  # string (sign name) or None
        antar_sign = None
        for maha in chara.get("mahadashas", []):
            if maha.get("active"):
                for ad in maha.get("antardashas", []):
                    if ad.get("active"):
                        antar_sign = ad.get("sign")
                        break
                break
        f["chara_dasha_current"] = {
            "mahadasha": cur_sign,
            "antardasha": antar_sign,
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
    # Prāśna question (if set)
    if chart.get("prasna_question"):
        f["prasna_question"] = chart["prasna_question"]
        f["prasna_mode"] = True

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
3. DIVISIONALCHARTS: Jeder Planet enthält "d9_sign", "d9_dignity" (Exalted/Debilitated/Own sign/Neutral) und "vargottama" (true/false) — ALLE AUTORITATIV, nie selbst berechnen. Behaupte NIEMALS selbst dass ein Zeichen das Exaltations- oder Feind-Zeichen eines Planeten ist; verwende ausschliesslich "d9_dignity". Merke: Widder ist Exaltationszeichen der SONNE, nicht Jupiters — Jupiter exaltiert in Krebs. Die Liste "vargottama_planets" nennt ALLE Vargottama-Planeten — verwende AUSSCHLIESSLICH diese Liste, behaupte niemals selbst welche Planeten vargottama sind oder dass keiner es ist. Vargottama-Planeten sind besonders stark und gefestigt. In jedem Divisional Chart gibt es "lagna_occupants": Planeten im Lagna dieses Charts sind stark zu gewichten. Wenn "vipareeta_raja_yoga" vorhanden: immer explizit als VRY benennen. Nutze D9 für Seelenqualität, D10 für Beruf, D3 für Vitalität.
4. ASPEKTE: Aspekte enthalten die Aspekt-Nummer, Hausherrschafts-Kontext und optionale Qualitäts-Tags. Regeln: (a) Jeder Aspekt bringt die Energie des aspektierenden Planeten UND die Themen seiner Herrschaftshäuser ins Zielhaus ("carrying H1+H6-energy"). (b) "[MALEFIC → afflicts but energises]": Der Aspekt belastet und affliktiert — gibt aber auch Energie, Fokus und Intensität. Nicht rein negativ. (c) "[own-lord → strengthens despite malefic nature]": Ein Malefic aspektiert sein eigenes Haus — das stärkt dieses Haus, trotz malefischer Natur. Beispiel Skorpion-Lagna, Mars (Herr H1+H6) in H10 aspektiert H1: stärkt H1 (Eigenaspekt) und bringt H6-Energie (Arbeit, Dienst) ins H10. "_house_aspects" gibt Netto-Einschätzung pro Haus.
5. TIMING: Im Daśā-Abschnitt verwende NUR die Planeten aus 'vimshottari_current'. Benenne Maha, Antar und Pratyantardaśā exakt wie im JSON angegeben.
6. QUALIFIZIERE: Wenn ein Yoga durch eine Affliction abgeschwächt wird, sage das. Wenn ein Defizit durch andere Faktoren ausgeglichen wird, sage das auch.""",

    "prasna_de": """Du bist ein erfahrener Jyotiṣa-Astrologe und beantwortest eine Prāśna-Frage (horārische Astrologie).

STRENGE REGELN:
• Interpretiere AUSSCHLIESSLICH die berechneten Fakten im JSON. Erfinde nichts.
• Das Horoskop ist das des FRAGEAUGENBLICKS — nicht ein Geburtshoroskop.
• Schreibe klar, direkt und orientierend auf Deutsch.
• Keine absoluten Vorhersagen — Tendenzen, Verbindungen, Bedingungen.
• Strukturiere exakt mit den vorgegebenen ## Überschriften.

PRĀŚNA-METHODIK:
1. SIGNIFIKATOREN: Lagna-Herr = Fragesteller. 7. Haus-Herr = Gegenüber/Gegenstand. Natürlicher Signifikator je nach Thema (Venus für Liebe, Saturn/H10-Herr für Beruf, H2-Herr für Geld).
2. ITHASALA: Bewegen sich Lagna-Herr und Signifikator aufeinander zu (Anwendung)? → günstig. Entfernen sie sich (Trennung)? → ungünstig oder vorbei.
3. MOND: Zeigt Energiefluss. Zunehmend + Benefic-Aspekt = günstig. Abnehmend + Malefic = stockend.
4. TIMING: Grad-Distanz der Signifikatoren × Haus-Qualität (beweglich = Tage/Wochen, fest = Monate, doppelkörperlich = Wochen).
5. ANTWORT: Klar formulieren, aber qualifiziert. Bedingungen nennen. Keine Schicksalssprache.""",

    "prasna_en": """You are an experienced Jyotiṣa astrologer answering a Prāśna (horary) question.

STRICT RULES:
• Interpret ONLY the calculated facts in the JSON. Invent nothing.
• This is a chart of the MOMENT OF THE QUESTION — not a birth chart.
• Write clearly, directly and orientingly in English.
• No absolute predictions — tendencies, connections, conditions.
• Structure exactly with the given ## headings.

PRĀŚNA METHODOLOGY:
1. SIGNIFICATORS: Lagna lord = querent. 7th lord = other party/matter. Natural significator by topic (Venus for love, Saturn/H10 lord for career, H2 lord for money).
2. ITHASALA: Are Lagna lord and significator moving toward each other (application)? → favourable. Moving apart (separation)? → unfavourable or past.
3. MOON: Shows energy flow. Waxing + benefic aspect = favourable. Waning + malefic = stagnant.
4. TIMING: Degree-distance of significators × sign quality (movable = days/weeks, fixed = months, dual = weeks).
5. ANSWER: State clearly but with qualification. Name conditions. No fate language.""",

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
3. DIVISIONAL CHARTS: Every planet has "d9_sign", "d9_dignity" (Exalted/Debilitated/Own sign/Neutral) and "vargottama" (true/false) — ALL AUTHORITATIVE, never self-calculate. NEVER claim yourself that a sign is a planet's exaltation or enemy sign; use only "d9_dignity". Note: Aries is the SUN's exaltation, not Jupiter's — Jupiter exalts in Cancer. The list "vargottama_planets" names ALL vargottama planets — use ONLY this list, never claim yourself which planets are vargottama or that none are. Vargottama planets are especially strong and stable. Each divisional chart has "lagna_occupants": planets in the Lagna carry strong weight. If "vipareeta_raja_yoga" is present: always name it as VRY. Use D9 for soul quality, D10 for career, D3 for vitality.
4. ASPECTS: Aspects contain the aspect number, lordship context, and optional quality tags. Rules: (a) Every aspect carries the aspecting planet's energy AND themes of all its ruled houses into the target ("carrying H1+H6-energy"). (b) "[MALEFIC → afflicts but energises]": the aspect burdens and afflicts — but also brings energy, intensity, and focus. Not purely negative. (c) "[own-lord → strengthens despite malefic nature]": a malefic aspecting its own house strengthens it despite malefic nature. Example Scorpio Lagna, Mars (lord H1+H6) in H10 aspects H1: strengthens H1 (own lord) and channels H6-energy (work, service) into H10. "_house_aspects" gives net assessment per house.
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
            "Das Jahr im Überblick (Varshaphala)",
            "Jahres-Aszendent & Muntha",
            "Varṣeśa — Der Herrscher des Jahres",
            "Vimśottarī-Auslösung im Jahr",
            "Themen & Chancen des Jahres",
            "Herausforderungen & Vorsicht",
            "Timing — Die Monate des Jahres",
            "Zusammenfassung des Jahres",
        ],
        "prasna": [
            "Prāśna — Die Frage & der Moment",
            "Lagna & Lagna-Herr — Der Fragesteller",
            "7. Haus & Signifikator — Das Gegenüber",
            "Mond — Verlauf & Geisteszustand",
            "Ithasala / Ishrafa — Verbindung oder Trennung",
            "Antwort & Timing",
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
            "The Year at a Glance (Varshaphala)",
            "Annual Ascendant & Muntha",
            "Varṣeśa — The Lord of the Year",
            "Vimśottarī activation during the year",
            "Themes & opportunities of the year",
            "Challenges & caution",
            "Timing — The months of the year",
            "Summary of the year",
        ],
        "prasna": [
            "Prāśna — The question & the moment",
            "Lagna & Lagna lord — The querent",
            "7th house & significator — The matter",
            "Moon — Flow & state of mind",
            "Ithasala / Ishrafa — Connection or separation",
            "Answer & timing",
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
            "Vergleiche Lagna-Herrn im Natal vs. D9. "
            "WICHTIG: Gehe im Bericht systematisch jeden Planeten durch und deute "
            "seine konkrete Wirkung in SEINEM Zeichen UND SEINEM Haus — z.B. "
            "'Rahu im 12. Haus', 'Ketu im 6. Haus', 'Saturn im Steinbock im 3. Haus'. "
            "Verteile diese Planeten-Deutungen sinnvoll auf die passenden Abschnitte "
            "(Karriere-Planeten im D10-Abschnitt, emotionale im Mond-Abschnitt etc.), "
            "aber lasse KEINEN Planeten unerwähnt.",
        "Mond, Nakshatra & Gefühlswelt (D1 vom Mond)":
            "Behandle den Mond als Chandra Lagna — analog zur Lagna-Deutung: "
            "Zähle ALLE Häuser neu vom Mond aus. Deute die Mond-Qualität "
            "(Zeichen, Nakshatra mit Devata/Symbol, Pada, Würde, Affliktionen). "
            "Welche Planeten stehen in welchem Haus VOM MOND aus gezählt? "
            "Welche Yogas und Aspekte wirken auf das Chandra Lagna? "
            "Erkläre die emotionale Grundstruktur, das innere Erleben, "
            "und wie der Mond-Ātmakāraka (wenn zutreffend) wirkt.",
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
            "Behandle den D9 wie ein eigenständiges Horoskop — analog zum Rāśi: "
            "(1) D9-Lagna-Zeichen und sein Herr (wo steht er im D9, Würde, Haus). "
            "(2) Planeten im D9-Lagna ('lagna_occupants') besonders stark gewichten. "
            "(3) HAUSHERRSCHAFT im D9: welche D9-Häuser regiert jeder Planet, und was bringt er durch Stellung/Aspekt in andere D9-Häuser. "
            "(4) Vergleiche wichtige Planeten (bes. Venus, 7. Herr) in D1 vs. D9. Nenne die Vargottama-Planeten AUS DER LISTE 'vargottama_planets' (nie selbst bestimmen) — sie sind besonders gefestigt. "
            "Deute was das für spirituelle Entwicklung, Dharma und Ehe bedeutet.",
        "Daśāṃśa (D10) — Beruf & Karriere":
            "Nutze D10-Lagna, D10-Planeten. Planeten in 'lagna_occupants' des D10 "
            "sind besonders stark zu gewichten — sie prägen die berufliche Identität direkt. "
            "Wenn 'vipareeta_raja_yoga' vorhanden: interpretiere jeden Eintrag explizit als "
            "VRY — Stärke durch Überwindung von Hindernissen, unerwarteter Erfolg. "
            "Vergleiche 10. Haus-Herrn in D1 vs. D10. Sun und Saturn in D10 besonders wichtig. "
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
        "Das Jahr im Überblick (Varshaphala)":
            "Beginne mit dem Solar-Return-Zeitpunkt und dem Jahr aus 'varshaphala'. "
            "Erklaere kurz was Varshaphala (Tajika-System) ist: das Jahreshoroskop ab dem "
            "Sonnenrueckkehr-Moment. Nenne Jahres-Lagna, Muntha und Varsesa (Jahresherrscher) "
            "als die drei Schluessel. Gib einen Gesamteindruck der Jahresqualitaet.",
        "Jahres-Aszendent & Muntha":
            "Deute das Jahres-Lagna (varshaphala.lagna) und seinen Herrn. Deute dann die Muntha "
            "(varshaphala.muntha, Herr: muntha_lord): ihr Haus im Jahreshoroskop zeigt den "
            "zentralen Lebensbereich des Jahres. Muntha in guenstigem Haus (1,4,5,7,9,10,11) = "
            "foerderlich; in Dusthana (6,8,12) = herausfordernd.",
        "Varṣeśa — Der Herrscher des Jahres":
            "Der Varsesa (varshaphala.varsha_pati) ist der wichtigste Planet des Jahres. "
            "Deute seine Natur, seine Stellung und was er fuer den Jahresverlauf bedeutet. "
            "Ein starker Varsesa bringt ein geordnetes Jahr; ein geschwaechter deutet auf Reibung.",
        "Vimśottarī-Auslösung im Jahr":
            "Verbinde das Jahreshoroskop mit der laufenden Vimshottari-Dasa ('vimshottari_current'). "
            "Welche Mahadasa/Antardasa laeuft in diesem Jahr? Die Dasa zeigt was vom Varshaphala-"
            "Potenzial tatsaechlich AUSGELOEST wird. Wenn der Dasa-Herr auch im Varshaphala stark ist "
            "oder mit dem Varsesa harmoniert, verstaerken sich die Themen. Synthese: "
            "Varshaphala = Buehne des Jahres, Vimshottari = welches Stueck gespielt wird.",
        "Themen & Chancen des Jahres":
            "Nenne die guenstigen Bereiche des Jahres — gut gestellte Planeten im Jahreshoroskop, "
            "guenstige Muntha-Stellung, harmonische Dasa. Sei konkret: welche Lebensbereiche "
            "(Beruf, Beziehung, Finanzen, Gesundheit, Spiritualitaet) sind beguenstigt?",
        "Herausforderungen & Vorsicht":
            "Nenne die belasteten Bereiche — affliktierte Planeten, Muntha oder Varsesa in Dusthana, "
            "schwierige Dasa-Konstellationen. Formuliere konstruktiv: Herausforderungen als "
            "Wachstumsfelder, mit praktischem Rat.",
        "Timing — Die Monate des Jahres":
            "Gib einen groben zeitlichen Verlauf des Jahres. Nutze die Antardasa-Wechsel "
            "('vimshottari_current') als Zeitmarken. Welche Phasen sind aktiver, welche ruhiger? "
            "Wann ist Vorsicht geboten, wann sind Chancen zu ergreifen?",
        "Zusammenfassung des Jahres":
            "Fasse die Kernbotschaft des Jahres in 2 Paragraphen zusammen: die wichtigste Chance, "
            "die groesste Herausforderung, den roten Faden. Schluss mit einer ermutigenden, "
            "handlungsorientierten Note — das Jahr als Gestaltungsraum, nicht als Schicksal.",
        "Prāśna — Die Frage & der Moment":
            "Beginne mit der Frage aus 'prasna_question'. Beschreibe den Prāśna-Moment: "
            "Lagna-Zeichen, Pañcāṅga (Tithi, Vara, Nakshatra). Ist der Moment günstig "
            "(Benefics im Lagna, zunehmender Mond) oder schwierig? "
            "Was sagt der erste Eindruck des Horoskops über die Frage?",
        "Lagna & Lagna-Herr — Der Fragesteller":
            "Das Lagna und sein Herr repräsentieren den Fragesteller (1. Person). "
            "Wo steht der Lagna-Herr (Haus, Zeichen, Würde)? Ist er stark oder schwach? "
            "Aspektiert er das Lagna? Welche Häuser regiert er zusätzlich? "
            "Was sagt das über die Situation und den Geisteszustand des Fragestellers?",
        "7. Haus & Signifikator — Das Gegenüber":
            "Das 7. Haus und sein Herr repräsentieren das Gegenüber oder den Gegenstand der Frage. "
            "Bestimme zusätzlich den natürlichen Signifikator des Fragethemas "
            "(H10-Herr für Beruf, Venus für Beziehung, H2-Herr für Geld etc.) aus 'prasna_question'. "
            "Wo steht der 7. Herr? Wie stark ist er? Gibt es eine Verbindung zum Lagna-Herrn?",
        "Mond — Verlauf & Geisteszustand":
            "Der Mond zeigt den aktuellen Energiefluss und Geisteszustand. "
            "Ist er zunehmend (günstig) oder abnehmend? In welchem Nakshatra? "
            "Aspektieren Benefics oder Malefics den Mond? "
            "Was zeigt der Mond über den Verlauf der Situation — fliesst sie oder stockt sie?",
        "Ithasala / Ishrafa — Verbindung oder Trennung":
            "Prüfe ob Lagna-Herr und Signifikator der Frage sich aufeinander zubewegen "
            "(Ithasala = Anwendung → günstig, Erfüllung möglich) "
            "oder voneinander entfernen (Ishrafa = Trennung → die Sache ist vorbei oder schwierig). "
            "Gibt es einen Vermittler-Planeten (Nakta/Musharrif)? "
            "Sind beide Signifikatoren stark genug um die Verbindung zu vollenden?",
        "Antwort & Timing":
            "Formuliere eine klare, aber qualifizierte Antwort auf 'prasna_question'. "
            "Keine absolute Vorhersage — zeige Tendenzen und Bedingungen. "
            "Schätze das Timing: Grad-Distanz zwischen den Signifikatoren × "
            "Zeichen-Qualität (beweglich = Tage/Wochen, fest = Monate, doppelkörperlich = Wochen). "
            "Welche Faktoren begünstigen, welche erschweren die Erfüllung? "
            "Schluss mit einer konkreten, ermutigenden Orientierung.",
    },
    "en": {
        "Ascendant & core nature (D1 from Lagna)":
            "Interpret the Lagna sign, its lord (position, dignity, house), "
            "all planets in the 1st house and their afflictions. Consider "
            "aspects on the Lagna. Use D9 Lagna lord to deepen. "
            "Compare natal Lagna lord vs. D9. "
            "IMPORTANT: Systematically address every planet's concrete effect in "
            "ITS sign AND ITS house — e.g. 'Rahu in the 12th', 'Ketu in the 6th', "
            "'Saturn in Capricorn in the 3rd'. Distribute these planet readings "
            "across the appropriate sections (career planets in the D10 section, "
            "emotional ones in the Moon section etc.), but leave NO planet unmentioned.",
        "Moon, nakshatra & emotional world (D1 from Moon)":
            "Treat the Moon as Chandra Lagna — analogous to the Ascendant reading: "
            "Recount ALL houses from the Moon. Interpret Moon quality "
            "(sign, nakshatra with devata/symbol, pada, dignity, afflictions). "
            "Which planets sit in which house COUNTED FROM THE MOON? "
            "Which yogas and aspects act on the Chandra Lagna? "
            "Explain the emotional foundation, inner experience, "
            "and how the Moon-Ātmakāraka (if applicable) functions.",
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
            "Treat the D9 as a full chart in its own right — analogous to the Rāśi: "
            "(1) D9 Lagna sign and its lord (position in D9, dignity, house). "
            "(2) Planets in the D9 Lagna ('lagna_occupants') weighted strongly. "
            "(3) HOUSE LORDSHIP in D9: which D9 houses each planet rules and what it brings via placement/aspect. "
            "(4) Compare key planets (especially Venus, 7th lord) in D1 vs D9. "
            "Name the Vargottama planets FROM THE LIST 'vargottama_planets' (never determine yourself) — they are especially stable. "
            "Interpret what this means for spiritual development and marriage.",
        "Daśāṃśa (D10) — career & vocation":
            "Use D10 Lagna, D10 planets. Planets in 'lagna_occupants' of D10 "
            "carry the strongest weight — they directly shape professional identity. "
            "If 'vipareeta_raja_yoga' is present: interpret each entry explicitly as "
            "VRY — strength through obstacles, unexpected success. "
            "Compare 10th house lord in D1 vs D10. "
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
        "The Year at a Glance (Varshaphala)":
            "Begin with the solar-return moment and year from 'varshaphala'. Briefly explain "
            "Varshaphala (Tajika system): the annual chart cast from the Sun's return. Name the "
            "annual Lagna, Muntha and Varsesa (year lord) as the three keys. Give an overall impression.",
        "Annual Ascendant & Muntha":
            "Interpret the annual Lagna and its lord. Then the Muntha (lord: muntha_lord): its house "
            "in the annual chart shows the central life area of the year. Good house (1,4,5,7,9,10,11) "
            "= supportive; dusthana (6,8,12) = challenging.",
        "Varṣeśa — The Lord of the Year":
            "The Varsesa (varsha_pati) is the year's most important planet. Interpret its nature, "
            "placement, and meaning. A strong Varsesa brings an ordered year; a weak one indicates friction.",
        "Vimśottarī activation during the year":
            "Connect the annual chart with the running Vimshottari Dasa ('vimshottari_current'). "
            "Which Mahadasa/Antardasa runs this year? The Dasa shows what of the Varshaphala potential "
            "is actually ACTIVATED. If the Dasa lord is also strong in the Varshaphala or harmonises "
            "with the Varsesa, themes amplify. Synthesis: Varshaphala = the year's stage, "
            "Vimshottari = which play is performed.",
        "Themes & opportunities of the year":
            "Name the favourable areas — well-placed planets, favourable Muntha, harmonious Dasa. "
            "Be concrete: which life areas (career, relationship, finance, health, spirituality)?",
        "Challenges & caution":
            "Name the burdened areas — afflicted planets, Muntha or Varsesa in dusthana, difficult Dasa. "
            "Frame constructively: challenges as growth fields, with practical advice.",
        "Timing — The months of the year":
            "Give a rough temporal arc. Use Antardasa changes ('vimshottari_current') as time markers. "
            "Which phases are more active, which quieter? When caution, when opportunity?",
        "Summary of the year":
            "Summarise the year's core message in 2 paragraphs: key opportunity, main challenge, "
            "through-line. Close with an encouraging, action-oriented note — the year as a space to shape.",
        "Prāśna — The question & the moment":
            "Begin with the question from 'prasna_question'. Describe the Prāśna moment: "
            "Lagna sign, Pañcāṅga (Tithi, Vara, Nakshatra). Is the moment favourable "
            "(benefics in Lagna, waxing Moon) or difficult? "
            "What does the first impression of the chart say about the question?",
        "Lagna & Lagna lord — The querent":
            "The Lagna and its lord represent the querent. "
            "Where is the Lagna lord (house, sign, dignity)? Strong or weak? "
            "Does it aspect the Lagna? What additional houses does it rule? "
            "What does this say about the querent's situation and state of mind?",
        "7th house & significator — The matter":
            "The 7th house and its lord represent the other party or matter asked about. "
            "Identify the natural significator of the topic from 'prasna_question' "
            "(H10 lord for career, Venus for relationship, H2 lord for money). "
            "Where is the 7th lord? How strong is it? Is there a connection to the Lagna lord?",
        "Moon — Flow & state of mind":
            "The Moon shows energy flow. Waxing + benefic aspect = favourable. "
            "Waning + malefic = stagnant. Which Nakshatra? "
            "What does the Moon show about the flow of the situation?",
        "Ithasala / Ishrafa — Connection or separation":
            "Check whether Lagna lord and significator are moving toward each other "
            "(Ithasala = application → favourable) or apart (Ishrafa = separation → difficult/past). "
            "Is there a mediating planet (Nakta/Musharrif)? "
            "Are both significators strong enough to complete the connection?",
        "Answer & timing":
            "Formulate a clear but qualified answer to 'prasna_question'. "
            "No absolute predictions — show tendencies and conditions. "
            "Estimate timing from degree-distance × sign quality "
            "(movable = days/weeks, fixed = months, dual = weeks). "
            "Close with a concrete, encouraging orientation.",
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

    if depth not in ("basis", "premium", "year", "prasna"):
        depth = "premium"
    if max_tokens == 0:
        max_tokens = 4000 if depth == "basis" else 6000 if depth in ("prasna", "year") else 16000

    facts  = build_facts(chart, depth=depth)
    system_key = f"prasna_{lang}" if depth == "prasna" else lang
    system = _BASE_RULES.get(system_key, _BASE_RULES[lang])
    prompt = build_prompt(facts, lang, depth)

    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": prompt}]
    full_text = ""

    for _attempt in range(3):  # allow up to 2 continuations
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        chunk = "".join(
            b.text for b in resp.content if getattr(b, "type", None) == "text"
        )
        full_text += chunk

        if getattr(resp, "stop_reason", None) != "max_tokens":
            break  # finished naturally

        # Response was cut off — ask the model to continue seamlessly
        messages.append({"role": "assistant", "content": chunk})
        messages.append({"role": "user", "content":
                         "Bitte fahre nahtlos fort, genau dort wo du aufgehört hast. "
                         "Wiederhole nichts." if lang == "de" else
                         "Please continue seamlessly exactly where you left off. "
                         "Do not repeat anything."})

    return full_text.strip()


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

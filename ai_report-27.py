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
from datetime import datetime
from typing import Dict, Optional

_MONTHS_DE = ["", "Januar", "Februar", "März", "April", "Mai", "Juni",
              "Juli", "August", "September", "Oktober", "November", "Dezember"]


def _fmt_date(val) -> str:
    """Return a clean 'D. Monat JJJJ' string from a datetime or ISO-ish string.
    Strips microseconds/time so the LLM sees only the date."""
    if not val:
        return ""
    s = str(val)
    # take just the date part before any space or 'T'
    datepart = s.replace("T", " ").split(" ")[0]
    try:
        y, m, d = datepart.split("-")[:3]
        return f"{int(d)}. {_MONTHS_DE[int(m)]} {int(y)}"
    except Exception:
        return datepart


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
        # Häuser vom Varga-Lagna — vorberechnet, nie vom Modell zählen lassen
        asc_si = full.get("Ascendant", {}).get("sign_idx")
        if asc_si is not None:
            entry["houses"] = {p: (rec["sign_idx"] - asc_si) % 12 + 1
                               for p, rec in full.items()
                               if p not in ("Ascendant", "_meta")
                               and rec.get("sign_idx") is not None}
        if meta.get("lagna_occupants"):
            entry["lagna_occupants"] = meta["lagna_occupants"]
        if meta.get("vipareeta_raja_yoga"):
            entry["vipareeta_raja_yoga"] = meta["vipareeta_raja_yoga"]
        if meta.get("parivartana"):
            entry["parivartana"] = meta["parivartana"]
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


def _person_facts(ch: Dict) -> Dict:
    """Kompakter Personen-Steckbrief für den Partner-Bericht."""
    from astro_engine import SIGN_LORDS as _SL
    pls    = ch.get("planets", {}) or {}
    aff    = ch.get("afflictions", {}) or {}
    houses = ch.get("houses", {}) or {}
    occ    = ch.get("occupants", {}) or {}

    def _p(pname):
        d = pls.get(pname, {}) or {}
        return {"sign": d.get("sign"), "house": d.get("house"),
                "pos": d.get("pos"), "nakshatra": d.get("nakshatra"),
                "pada": d.get("pada"), "dignity": d.get("dignity"),
                "afflictions": aff.get(pname, [])}

    lagna_sign = ch.get("lagna")
    lord = _SL.get(lagna_sign) if lagna_sign else None
    h7_sign = houses.get(7, houses.get("7"))
    h7_lord = _SL.get(h7_sign) if h7_sign else None
    return {
        "name":   ch.get("meta", {}).get("name"),
        "gender": ch.get("meta", {}).get("gender"),
        "birth":  ch.get("meta", {}).get("birth"),
        "lagna":  {"sign": lagna_sign, "pos": ch.get("lagna_pos"),
                   "lord": lord,
                   "lord_condition": _p(lord) if lord else None},
        "moon":    _p("Moon"),
        "venus":   _p("Venus"),
        "mars":    _p("Mars"),
        "jupiter": _p("Jupiter"),
        "saturn":  _p("Saturn"),
        "house7": {"sign": h7_sign, "lord": h7_lord,
                   "lord_condition": _p(h7_lord) if h7_lord else None,
                   "occupants": occ.get(7, occ.get("7", []))},
    }


def _build_partner_facts(chart: Dict) -> str:
    """Fakten für depth='partner'.

    Vertrag (vom report_service herzustellen):
      chart                  = generate_chart(...) von Person A
      chart["partner_chart"] = generate_chart(...) von Person B
      chart["compatibility"] = astro_engine.compute_compatibility(chart_a, chart_b)
    Konvention der klassischen Kūṭas: A = Mann, B = Frau, wo geschlechts-
    spezifische Faktoren (Strī-Dīrgha, Rāśi-Kūṭa) greifen.
    """
    pb   = chart.get("partner_chart") or {}
    comp = chart.get("compatibility") or {}
    f = {
        "hinweis": ("Partnerschafts-Analyse zweier Horoskope. 'person_a' und "
                    "'person_b' sind gleichwertig. Alle Kūṭa-, Doṣa-, Milāna- "
                    "und Overlay-Befunde sind vorberechnet und autoritativ — "
                    "nichts selbst berechnen."),
        "person_a": _person_facts(chart),
        "person_b": _person_facts(pb),
        "ashtakuta":      comp.get("ashtakuta"),
        "mangal":         comp.get("mangal"),
        "overlay_b_in_a": comp.get("overlay_b_in_a"),
        "overlay_a_in_b": comp.get("overlay_a_in_b"),
        "extra_milana":   comp.get("extra_milana"),
    }
    return json.dumps(f, ensure_ascii=False, indent=1, default=str)


def build_facts(chart: Dict, depth: str = "premium") -> str:
    """Build the complete structured facts block for the LLM."""
    if depth == "partner":
        return _build_partner_facts(chart)
    f: Dict = {}
    pls = chart.get("planets", {})
    _moon_si = pls.get("Moon", {}).get("sign_idx")   # für alle Chandra-Lagna-Felder

    # ── Current date (authoritative "now" for all timing statements) ───────────
    _now = datetime.now()
    f["current_date"] = {
        "iso": _now.strftime("%Y-%m-%d"),
        "de": f"{_now.day}. {_MONTHS_DE[_now.month]} {_now.year}",
        "note": ("Dies ist das heutige Datum. Alle Aussagen über 'aktuell', "
                 "'jetzt', 'läuft', 'kommt' MÜSSEN sich hieran orientieren. "
                 "Verlasse dich für die laufende Periode ausschließlich auf "
                 "'vimshottari_current' und die 'active'-Markierungen — stelle "
                 "KEINE eigenen Datumsvergleiche an."),
    }

    # ── Lagna ──────────────────────────────────────────────────────────────
    li = chart.get("lagna_idx")
    # Lagna-Herr robust bestimmen: chart['lagna_lord'] existiert auf oberster
    # Ebene nicht immer — dann aus dem Lagna-Zeichen ableiten. Vorher stand in
    # den Fakten schlicht null, und der Lagneśa fehlte der Deutung komplett.
    _lord = chart.get("lagna_lord")
    if not _lord and li is not None:
        try:
            from astro_engine import SIGN_LORDS as _SL_
            _lord = _SL_.get(SIGNS[li])
        except Exception:
            _lord = None
    f["lagna"] = {
        "sign":    SIGNS[li] if li is not None else None,
        "pos":     chart.get("lagna_pos"),
        "lord":    _lord,
        "lord_house": pls.get(_lord or "", {}).get("house"),
        "house_from_moon": ((li - _moon_si) % 12 + 1)
                           if (li is not None and _moon_si is not None) else None,
    }
    # Vollständiger Zustand des Lagneśa — zentral für Prāśna (Fragesteller!)
    # und Janma. Enthält exakte Konjunktions-Orben, damit z.B. eine enge
    # Ketu-Konjunktion des Lagna-Herrn nie mehr übersehen werden kann.
    _ld = pls.get(_lord, {}) if _lord else {}
    if _ld:
        _conj = []
        _l_lon = _ld.get("lon")
        if _l_lon is not None:
            for _q, _qd in pls.items():
                if _q in (_lord, "Ascendant"):
                    continue
                _q_lon = _qd.get("lon")
                if _q_lon is None:
                    continue
                _d = abs((_l_lon - _q_lon + 180) % 360 - 180)
                if _d <= 10.0:
                    _tag = " — SEHR ENG" if _d < 3.0 else ""
                    _conj.append(f"{_q} ({_d:.1f}°{_tag})")
        f["lagna"]["lord_details"] = {
            "sign":      _ld.get("sign"),
            "house":     _ld.get("house"),
            "pos":       _ld.get("pos"),
            "nakshatra": _ld.get("nakshatra"),
            "pada":      _ld.get("pada"),
            "dignity":   _ld.get("dignity"),
            "conjunctions_with_orb": _conj,
            "afflictions": (chart.get("afflictions") or {}).get(_lord, []),
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
        # Haus vom Mond (Chandra Lagna) — VORBERECHNET, damit das Modell nie
        # selbst Tierkreis-Abstände zählen muss (Fundstelle: Zählfehler in der
        # Mond-Deutung trotz korrektem Rasi).
        if _moon_si is not None and d.get("sign_idx") is not None:
            f["planets"][p]["house_from_moon"] = (d["sign_idx"] - _moon_si) % 12 + 1

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
                f["vimshottari_current"]["mahadasha_end"] = _fmt_date(maha_entry.get("end",""))
                for antar in maha_entry.get("antardashas", []):
                    if antar.get("active"):
                        f["vimshottari_current"]["antardasha_start"] = _fmt_date(antar.get("start",""))
                        f["vimshottari_current"]["antardasha_end"]   = _fmt_date(antar.get("end",""))
                        f["vimshottari_current"]["antardasha_status"] = "läuft bereits (aktiv)"
                        for pad in antar.get("pratyantardashas", []):
                            if pad.get("active"):
                                f["vimshottari_current"]["pratyantardasha_end"] = _fmt_date(pad.get("end",""))
                                f["vimshottari_current"]["pratyantardasha_status"] = "läuft bereits (aktiv)"
                        break
                break

    # ── Prāśna-Vertiefungsfrage: Bezug zur ursprünglichen Frage ─────────────
    if chart.get("prasna_followup_of"):
        f["prasna_followup_of"] = chart["prasna_followup_of"]

    # ── Prāśna Plus: Janma-Kontext (nur wenn Geburtsdaten angegeben wurden) ─
    if chart.get("janma_context"):
        f["janma_context"] = dict(chart["janma_context"])
        f["janma_context"]["HINWEIS"] = (
            "Geburtshoroskop-Kontext des Fragestellers für die "
            "Prāśna-Synthese. Das Prāśna-Chart bleibt die primäre "
            "Antwortquelle; dieser Kontext dient nur der Bestätigung und "
            "zeitlichen Einordnung.")

    # ── Bhāveśa — Hausherren-Analyse (Verpackung: Herr von Haus X in Haus Y) ─
    houses_map = chart.get("houses") or {}
    if houses_map:
        from astro_engine import SIGN_LORDS as _SL, SIGNS as _SGN
        sb_pl = (chart.get("shadbala") or {}).get("planets", {})
        affl = chart.get("afflictions") or {}
        d9 = chart.get("d9") or {}
        d9_lag = chart.get("d9_lagna")
        hl = {}
        for h in range(1, 13):
            sign = houses_map.get(h)
            lord = _SL.get(sign)
            rec = chart.get("planets", {}).get(lord, {})
            entry = {
                "lord": lord,
                "goes_to_house": rec.get("house"),
                "in_sign": rec.get("sign"),
                "dignity": rec.get("dignity"),
                "nakshatra": f"{rec.get('nakshatra','')} Pada {rec.get('pada','')}",
            }
            sb = sb_pl.get(lord, {})
            if sb:
                entry["shadbala_rupa"] = sb.get("rupa")
                entry["shadbala_strong"] = sb.get("strong")
            if affl.get(lord):
                entry["afflictions"] = affl[lord]
            mal_asp = [a for a in (chart.get("aspects") or {}).get(lord, [])
                       if a.startswith("receives") and "[MALEFIC" in a]
            if mal_asp:
                entry["malefic_aspects_received"] = mal_asp
            if lord in d9 and d9_lag is not None:
                d9_si = d9[lord]
                entry["d9_sign"] = _SGN[d9_si]
                entry["d9_house"] = (d9_si - d9_lag) % 12 + 1
            hl[f"house_{h}"] = entry
        f["house_lords"] = {
            "note": ("Bhāveśa-Analyse: 'Herr von Haus X geht in Haus Y' ist eine "
                     "zentrale Deutungsachse. Der Herr trägt die Themen seines "
                     "Hauses dorthin, wo er steht — qualifiziert durch Würde, "
                     "Shad-Bala-Stärke, Affliktionen und seinen D9-Stand."),
            "lords": hl,
        }

    # ── Gochara — aktuelle Transite (Verpackung von astro_engine-Daten) ──
    tr = chart.get("transits") or {}
    if tr:
        akv = chart.get("ashtakavarga") or {}
        lag_i = chart.get("lagna_idx", 0)
        moon_i = chart.get("planets", {}).get("Moon", {}).get("sign_idx")
        t_list = {}
        for p, rec in tr.items():
            if p == "Ascendant":
                continue
            tsi = rec.get("sign_idx")
            entry = {
                "sign": rec.get("sign"),
                "position": rec.get("pos"),
                "nakshatra": f"{rec.get('nakshatra','')} Pada {rec.get('pada','')}",
                "house_from_lagna": (tsi - lag_i) % 12 + 1 if tsi is not None else None,
            }
            if moon_i is not None and tsi is not None:
                entry["house_from_moon"] = (tsi - moon_i) % 12 + 1
            if p in akv and tsi is not None:
                b = akv[p][tsi]
                entry["ashtakavarga_bindus"] = b
                entry["bindu_support"] = ("strong" if b >= 5 else
                                          "average" if b == 4 else "weak")
            t_list[p] = entry
        f["transits_today"] = {
            "date": chart.get("transit_date"),
            "planets": t_list,
            "note": ("Slow transits (Saturn, Jupiter, Rahu/Ketu) shape phases; "
                     "fast ones (Sun, Mercury, Venus, Moon) colour days/weeks. "
                     "Transits act as triggers WITHIN the running dasha."),
        }
        sat_hm = t_list.get("Saturn", {}).get("house_from_moon")
        if sat_hm in (12, 1, 2):
            phase = {12: "erste Phase (Saturn im 12. vom Mond)",
                     1:  "Kernphase (Saturn über dem natalen Mond)",
                     2:  "letzte Phase (Saturn im 2. vom Mond)"}[sat_hm]
            f["transits_today"]["sade_sati"] = {"active": True, "phase": phase}
        else:
            f["transits_today"]["sade_sati"] = {"active": False}

    # ── Panchang ─────────────────────────────────────────────────────────
    pan = chart.get("panchang", {})
    if pan:
        f["panchang_of_birth"] = {k: pan.get(k) for k in
                         ("tithi","vara","vara_lord","nakshatra","nakshatra_lord","yoga","karana")}
        f["panchang_of_birth"]["ACHTUNG"] = (
            "Dies ist das Pañcāṅga des GEBURTSZEITPUNKTS — nicht des heutigen "
            "Tages. Es beschreibt die Zeitqualität der Geburt und darf niemals "
            "als heutiger Almanach oder Tagesenergie gedeutet werden.")
        try:
            import panchang_db
            f["panchang_of_birth"]["interpretations"] = {
                el: txt for el, _val, txt in panchang_db.describe(pan)}
        except Exception:
            pass

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
    # Optional user-provided context (interpretation only — never affects calculation)
    if meta.get("occupation"):
        f["meta"]["occupation"] = meta["occupation"]
    if meta.get("context"):
        f["user_context"] = meta["context"]
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
3. DIVISIONALCHARTS: Jeder Planet enthält "d9_sign", "d9_dignity" (Exalted/Debilitated/Own sign/Neutral) und "vargottama" (true/false) — ALLE AUTORITATIV, nie selbst berechnen. Behaupte NIEMALS selbst dass ein Zeichen das Exaltations- oder Feind-Zeichen eines Planeten ist; verwende ausschliesslich "d9_dignity". Merke: Widder ist Exaltationszeichen der SONNE, nicht Jupiters — Jupiter exaltiert in Krebs. Die Liste "vargottama_planets" nennt ALLE Vargottama-Planeten — verwende AUSSCHLIESSLICH diese Liste, behaupte niemals selbst welche Planeten vargottama sind oder dass keiner es ist. Vargottama-Planeten sind besonders stark und gefestigt. In jedem Divisional Chart gibt es "lagna_occupants": Planeten im Lagna dieses Charts sind stark zu gewichten. Wenn "vipareeta_raja_yoga" vorhanden: immer explizit als VRY benennen. Wenn "parivartana" vorhanden: den Zeichentausch immer explizit deuten — ein Raja-Parivartana (Kendra/Trikona) ist eine der stärksten Varga-Konstellationen, und ein vermerktes Neecha Bhanga hebt die Debilitation des genannten Planeten auf (dann NICHT als geschwächt deuten). Nutze D9 für Seelenqualität, D10 für Beruf, D3 für Vitalität.
4. ASPEKTE: Aspekte enthalten die Aspekt-Nummer, Hausherrschafts-Kontext und optionale Qualitäts-Tags. Regeln: (a) Jeder Aspekt bringt die Energie des aspektierenden Planeten UND die Themen seiner Herrschaftshäuser ins Zielhaus ("carrying H1+H6-energy"). (b) "[MALEFIC → afflicts but energises]": Der Aspekt belastet und affliktiert — gibt aber auch Energie, Fokus und Intensität. Nicht rein negativ. (c) "[own-lord → strengthens despite malefic nature]": Ein Malefic aspektiert sein eigenes Haus — das stärkt dieses Haus, trotz malefischer Natur. Beispiel Skorpion-Lagna, Mars (Herr H1+H6) in H10 aspektiert H1: stärkt H1 (Eigenaspekt) und bringt H6-Energie (Arbeit, Dienst) ins H10. "_house_aspects" gibt Netto-Einschätzung pro Haus.
5. TIMING: Im Daśā-Abschnitt verwende NUR die Planeten aus 'vimshottari_current'. Benenne Maha, Antar und Pratyantardaśā exakt wie im JSON angegeben. Die in 'vimshottari_current' genannten Perioden sind per Definition die JETZT laufenden — behandle sie IMMER als aktiv/gegenwärtig, niemals als zukünftig. Das heutige Datum steht in 'current_date'; richte jede Zeitaussage danach aus. Wenn eine Antardaśā in 'vimshottari_current' steht, dann LÄUFT sie bereits — schreibe niemals, sie 'beginne erst' oder 'laufe noch nicht'. Stelle KEINE eigenen Vergleiche zwischen Start-/Enddaten und 'heute' an; verlasse dich allein auf die gelieferten 'active'-Markierungen.
6. QUALIFIZIERE: Wenn ein Yoga durch eine Affliction abgeschwächt wird, sage das. Wenn ein Defizit durch andere Faktoren ausgeglichen wird, sage das auch.
7. PERSÖNLICHER KONTEXT: Wenn die Felder "meta.gender", "meta.occupation" oder "user_context" vorhanden sind, beziehe sie in die Deutung ein — verbinde die astrologischen Faktoren konkret mit der Lebenssituation der Person (z.B. Beruf mit dem 10. Haus / D10, geschilderte Themen mit den passenden Häusern und Daśās). Nutze den Kontext um GEZIELTER und relevanter zu deuten, aber lasse die astrologische Analyse führend bleiben — der Kontext ist Anwendungshilfe, nicht Ersatz für die Chartdeutung. Erfinde keine Details die über das Geschilderte hinausgehen.
8. RECHENVERBOT (KRITISCH): Du rechnest und zählst NIEMALS selbst — keine Häuserzählung, keine Tierkreis-Abstände, keine Grad-Arithmetik, keine "X steht im n-ten von Y"-Herleitungen. JEDE relative Position stammt ausschliesslich aus den gelieferten Feldern: 'house' (vom Lagna), 'house_from_moon' (vom Mond, auch in 'lagna.house_from_moon'), 'houses' der Divisionalcharts (vom jeweiligen Varga-Lagna) und 'house_from_lagna'/'house_from_moon' der Transite. Ist eine benötigte relative Position NICHT geliefert, lass die Aussage weg, statt sie herzuleiten. Sprachliche Umformulierungen sind erlaubt, Neuberechnungen nicht.
9. GOCHARA: Transite (falls 'transits_today' vorhanden) sind AUSLÖSER im Rahmen der laufenden Daśā — nie eigenständige Vorhersagen. Referenzpunkte sind das natale Lagna UND der natale Mond (Chandra Lagna). Langsame Planeten wiegen schwer, schnelle kaum. Jeder Transit ist mit seinen Ashtakavarga-Bindus zu qualifizieren. Verwende nur die gelieferten Transit-Daten. Das Feld 'panchang_of_birth' ist das Pañcāṅga der GEBURT — deute es NIEMALS als heutigen Almanach oder Tagesqualität.
10. PRĀŚNA-SYNTHESE: Wenn 'janma_context' vorhanden ist, bleibt das PRĀŚNA-CHART die primäre Antwortquelle. Nutze das Janma nur zweifach: (a) Bestätigung — stützt oder bremst der zuständige natale Hausherr das Fragethema? (b) Zeitliche Einordnung — trägt die laufende Daśā ('vimshottari_current', Ende der Mahādaśā) das versprochene Ergebnis? Benenne Widersprüche zwischen Prāśna und Janma offen, aber überschreibe NIE das Prāśna-Urteil. Webe die Synthese in die Kapitel zum Urteil und Timing ein. Fehlt 'janma_context', erwähne das Geburtshoroskop mit KEINEM Wort.
11. PRĀŚNA-UMFANG: Beantworte genau EINE klar gestellte Frage — die in 'prasna_question'. Enthält der Text mehrere getrennte Fragen, beantworte die erste vollständig und weise freundlich darauf hin, dass weitere Fragen als Vertiefungsfrage zu diesem Prāśna gestellt werden können. Eine Frage mit mehreren Facetten ist EINE Frage — sei dort grosszügig.""",

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
5. ANTWORT: Klar formulieren, aber qualifiziert. Bedingungen nennen. Keine Schicksalssprache.
6. KONTEXT: Wenn "meta.gender", "meta.occupation" oder "user_context" vorhanden sind, nutze sie um die Frage im richtigen Lebensbereich zu verankern und die Antwort gezielter zu machen — ohne über das Geschilderte hinaus zu erfinden.
7. LAGNEŚA-ZUSTAND (PFLICHT): Der Zustand des Lagna-Herrn steht autoritativ in 'lagna.lord_details' (Würde, Affliktionen, Konjunktionen mit exaktem Orbis). Er ist ein HAUPTFAKTOR des Urteils und MUSS im Kapitel zum Fragesteller benannt und im Schlussurteil gewichtet werden. Insbesondere: eine ENGE Konjunktion des Lagneśa mit KETU zeigt Ablösung, Verneinung, Entzug, verborgene oder karmische Faktoren — oder dass der Fragesteller innerlich bereits losgelassen hat; mit RAHU Verzerrung, Übersteigerung, Täuschung oder Fremdbestimmung; Verbrennung (Asta) Schwäche und Überstrahlung des eigenen Willens; Debilitation mangelnde Durchsetzungskraft. Ein stark affligierter Lagneśa RELATIVIERT ein sonst günstiges Ithasala deutlich — ignoriere solche Affliktionen NIEMALS, auch wenn andere Faktoren positiv sind.""",

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
5. ANSWER: State clearly but with qualification. Name conditions. No fate language.
6. CONTEXT: If "meta.gender", "meta.occupation" or "user_context" are present, use them to anchor the question in the right life area and make the answer more specific — without inventing beyond what was described.
7. LAGNESHA CONDITION (MANDATORY): The condition of the Lagna lord is given authoritatively in 'lagna.lord_details' (dignity, afflictions, conjunctions with exact orb). It is a PRIMARY factor of the verdict and MUST be named in the querent chapter and weighed in the final answer. In particular: a TIGHT conjunction of the Lagnesha with KETU shows severance, negation, withdrawal, hidden or karmic factors — or that the querent has inwardly already let go; with RAHU distortion, amplification, deception or outside influence; combustion (Asta) weakness and an overshadowed will; debilitation lack of assertiveness. A strongly afflicted Lagnesha significantly QUALIFIES an otherwise favourable Ithasala — NEVER ignore such afflictions, even when other factors are positive.""",

    "partner_de": """Du bist ein erfahrener Jyotiṣa-Astrologe und schreibst einen Partnerschafts-Bericht (Kompatibilitätsanalyse zweier Horoskope).

STRENGE REGELN:
• Du deutest AUSSCHLIESSLICH die im JSON gelieferten, bereits berechneten Fakten (Kūṭa-Punkte, Positionen, Würden, Affliktionen, Overlays). Du berechnest, veränderst oder erfindest NICHTS.
• Person A und Person B sind gleichwertig — beschreibe beide respektvoll, ausgewogen und mit etwa gleich viel Aufmerksamkeit. Keine einseitigen Schuldzuweisungen.
• Schreibe klar, warm und tiefgründig auf Deutsch. Erkläre Sanskrit-Begriffe kurz beim ersten Auftreten.
• Keine Schicksalssprache und kein absolutes Urteil über Heirat oder Trennung — Kompatibilität beschreibt Tendenzen, Ressourcen und Übungsfelder.
• Strukturiere den Text exakt mit den vorgegebenen ## Überschriften.

METHODISCHE PRINZIPIEN:
1. GEWICHTUNG DER KŪṬAS: Die 36 Guṇas sind ein Raster, kein Orakel. Nādi (max. 8) und Bhakūṭa (max. 7) wiegen am schwersten; ein Nādi- oder Bhakūṭa-Doṣa MUSS klar benannt werden, ebenso im JSON vermerkte Aufhebungen. Gesamtpunkte einordnen: unter 18 schwach, 18–24 ordentlich, 25–32 gut, über 32 ausgezeichnet — aber IMMER im Licht der übrigen Faktoren qualifizieren.
2. EXTRA-MILĀNA: Vedha und Rajju sind ernste klassische Hindernisse und dürfen nicht bagatellisiert werden; Strī-Dīrgha und Rāśi-Kūṭa können Defizite mildern. Verwende ausschliesslich die Befunde aus 'extra_milana'.
3. MANGAL DOṢA: Verwende nur 'mangal' aus dem JSON (inkl. 'verdict'). Beidseitiger Doṣa hebt sich gegenseitig auf; einseitiger Doṣa ist ein ernster Prüfpunkt, kein Verdikt. Nenne Milderungen nur, wenn sie im JSON stehen.
4. AFFLIKTIONEN: Würde und Affliktionen von Mond, Venus, Mars und des 7.-Haus-Herrn beider Personen fliessen in jede Bewertung ein — ein verbrannter, geschwächter oder eng Ketu-/Rahu-konjunkter Beziehungssignifikator relativiert auch hohe Kūṭa-Punkte und MUSS benannt werden.
5. OVERLAYS: 'overlay_b_in_a' und 'overlay_a_in_b' zeigen, in welches Haus des einen die Planeten des anderen fallen. Kendra/Trikona (1, 4, 5, 7, 9, 10) verbindet und stützt, 2/11 nährt, Duḥsthāna (6, 8, 12) fordert. Deute mindestens Mond, Venus und Mars in beide Richtungen.
6. BALANCE: Jede Herausforderung wird mit ihrer Ressource benannt, jede Stärke mit ihrer Bedingung. Ziel ist Orientierung für zwei erwachsene Menschen — weder Angst noch Schönfärberei.""",

    "partner_en": """You are an experienced Jyotiṣa astrologer writing a relationship report (compatibility analysis of two charts).

STRICT RULES:
• Interpret ONLY the already-calculated facts in the JSON (kuta points, positions, dignities, afflictions, overlays). Compute, alter or invent NOTHING.
• Person A and person B are equals — describe both respectfully, in balance, with roughly equal attention. No one-sided blame.
• Write clearly, warmly and with depth in English. Briefly explain Sanskrit terms on first use.
• No fate language and no absolute verdict on marriage or separation — compatibility describes tendencies, resources and practice fields.
• Structure the text exactly with the given ## headings.

METHODOLOGICAL PRINCIPLES:
1. WEIGHTING THE KUTAS: The 36 gunas are a grid, not an oracle. Nadi (max 8) and Bhakuta (max 7) weigh heaviest; a Nadi or Bhakuta dosha MUST be named clearly, as must any cancellations noted in the JSON. Total points: below 18 weak, 18–24 fair, 25–32 good, above 32 excellent — but ALWAYS qualify in the light of the remaining factors.
2. EXTRA MILANA: Vedha and Rajju are serious classical obstacles and must not be downplayed; Stri-Dirgha and Rasi Kuta can soften deficits. Use only the findings in 'extra_milana'.
3. MANGAL DOSHA: Use only 'mangal' from the JSON (incl. 'verdict'). Mutual dosha cancels; one-sided dosha is a serious checkpoint, not a verdict. Name mitigations only if present in the JSON.
4. AFFLICTIONS: Dignity and afflictions of Moon, Venus, Mars and the 7th lord of both persons enter every assessment — a combust, debilitated or tightly Ketu/Rahu-conjunct relationship significator qualifies even high kuta points and MUST be named.
5. OVERLAYS: 'overlay_b_in_a' and 'overlay_a_in_b' show into which house of one person the other's planets fall. Kendra/Trikona (1, 4, 5, 7, 9, 10) connects and supports, 2/11 nourishes, dusthana (6, 8, 12) challenges. Interpret at least Moon, Venus and Mars in both directions.
6. BALANCE: Name every challenge with its resource and every strength with its condition. The goal is orientation for two adults — neither fear nor whitewashing.""",

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
3. DIVISIONAL CHARTS: Every planet has "d9_sign", "d9_dignity" (Exalted/Debilitated/Own sign/Neutral) and "vargottama" (true/false) — ALL AUTHORITATIVE, never self-calculate. NEVER claim yourself that a sign is a planet's exaltation or enemy sign; use only "d9_dignity". Note: Aries is the SUN's exaltation, not Jupiter's — Jupiter exalts in Cancer. The list "vargottama_planets" names ALL vargottama planets — use ONLY this list, never claim yourself which planets are vargottama or that none are. Vargottama planets are especially strong and stable. Each divisional chart has "lagna_occupants": planets in the Lagna carry strong weight. If "vipareeta_raja_yoga" is present: always name it as VRY. If "parivartana" is present: always interpret the sign exchange explicitly — a Raja Parivartana (kendra/trikona) is among the strongest varga configurations, and a noted Neecha Bhanga cancels the named planet's debilitation (do NOT read it as weakened then). Use D9 for soul quality, D10 for career, D3 for vitality.
4. ASPECTS: Aspects contain the aspect number, lordship context, and optional quality tags. Rules: (a) Every aspect carries the aspecting planet's energy AND themes of all its ruled houses into the target ("carrying H1+H6-energy"). (b) "[MALEFIC → afflicts but energises]": the aspect burdens and afflicts — but also brings energy, intensity, and focus. Not purely negative. (c) "[own-lord → strengthens despite malefic nature]": a malefic aspecting its own house strengthens it despite malefic nature. Example Scorpio Lagna, Mars (lord H1+H6) in H10 aspects H1: strengthens H1 (own lord) and channels H6-energy (work, service) into H10. "_house_aspects" gives net assessment per house.
5. TIMING: In the Daśā section use ONLY the planets from 'vimshottari_current'. Name Maha, Antar and Pratyantardaśā exactly as given in the JSON. The periods listed in 'vimshottari_current' are BY DEFINITION the ones running NOW — always treat them as active/present, never as future. Today's date is in 'current_date'; align every temporal statement with it. If an Antardaśā appears in 'vimshottari_current', it is ALREADY running — never write that it 'begins only later' or 'is not yet active'. Do NOT perform your own comparisons between start/end dates and 'today'; rely solely on the provided 'active' flags.
6. QUALIFY: If a Yoga is weakened by an affliction, say so. If a deficit is compensated by other factors, say that too.
7. PERSONAL CONTEXT: If "meta.gender", "meta.occupation" or "user_context" are present, weave them into the reading — connect astrological factors concretely with the person's life situation (e.g. occupation with the 10th house / D10, described themes with the relevant houses and Daśās). Interpret MORE SPECIFICALLY, but keep the astrology leading — context is an application aid, not a substitute. Do not invent details beyond what was described.
8. NO SELF-CALCULATION (CRITICAL): You NEVER count or compute yourself — no house counting, no zodiac distances, no degree arithmetic, no "X is in the nth from Y" derivations. EVERY relative position comes exclusively from the supplied fields: 'house' (from Lagna), 'house_from_moon' (from the Moon, also in 'lagna.house_from_moon'), the divisional charts' 'houses' (from that varga's Lagna) and the transits' 'house_from_lagna'/'house_from_moon'. If a needed relative position is NOT supplied, omit the statement rather than derive it. Rephrasing is allowed, recomputation is not.
9. GOCHARA: Transits (if 'transits_today' is present) are TRIGGERS within the running dasha — never standalone predictions. Reference points are the natal Lagna AND the natal Moon (Chandra Lagna). Slow planets weigh heavily, fast ones barely. Qualify every transit with its Ashtakavarga bindus. Use only the supplied transit data. The field 'panchang_of_birth' is the Pañcāṅga of BIRTH — NEVER interpret it as today's almanac or daily energy.
10. PRASNA SYNTHESIS: When 'janma_context' is present, the PRASNA CHART remains the primary source of the answer. Use the janma chart only twofold: (a) confirmation — does the relevant natal house lord support or brake the question's theme? (b) timing — does the running dasha ('vimshottari_current', mahadasha end) carry the promised outcome? Name contradictions between prasna and janma openly, but NEVER override the prasna verdict. Weave the synthesis into the verdict and timing chapters. If 'janma_context' is absent, do not mention the birth chart with a SINGLE word.
11. PRASNA SCOPE: Answer exactly ONE clearly asked question — the one in 'prasna_question'. If the text contains several separate questions, answer the first completely and kindly note that further questions can be asked as a follow-up question (Vertiefungsfrage) to this praśna. A single question with several facets is ONE question — be generous there.""",
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
            "Pañcāṅga der Geburt — Die fünf Zeitqualitäten",
            "Die Hausherren (Bhāveśa) — Wohin die Herren der Häuser gehen",
            "Stärken, Yogas & Shad Bala",
            "Affliktionen & Herausforderungen",
            "Aspekte & Planetarische Beziehungen",
            "Navāṃśa (D9) — Seelenqualität & Ehe",
            "Daśāṃśa (D10) — Beruf & Karriere",
            "Drekkāna (D3) & Chaturthamsha (D4)",
            "Beziehungen & Partnerschaft",
            "Aktuelles Timing (Viṃśottarī Daśā)",
            "Aktuelle Transite (Gochara)",
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
        "prasna_zusatz": [
            "Die Vertiefungsfrage im Prāśna-Chart",
            "Antwort & Timing",
        ],
        "partner": [
            "Zwei Horoskope im Überblick",
            "Aṣṭakūṭa — Die 36 Guṇas im Detail",
            "Vedha, Rajju & weitere Milāna-Faktoren",
            "Mangal Doṣa — Die Mars-Prüfung",
            "Mond & Gefühlswelt im Vergleich",
            "Venus & Mars — Anziehung und Ausdruck",
            "Das 7. Haus beider Partner",
            "Gegenseitige Überlagerungen (Overlays)",
            "Stärken der Verbindung",
            "Reibungspunkte & Wachstumsfelder",
            "Zusammenfassung & Empfehlung",
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
            "Pañcāṅga of Birth — The five time qualities",
            "The House Lords (Bhāveśa) — Where the lords of the houses go",
            "Strengths, yogas & Shad Bala",
            "Afflictions & challenges",
            "Aspects & planetary relationships",
            "Navāṃśa (D9) — soul quality & marriage",
            "Daśāṃśa (D10) — career & vocation",
            "Drekkāna (D3) & Chaturthamsha (D4)",
            "Relationships & partnership",
            "Current timing (Viṃśottarī Daśā)",
            "Current Transits (Gochara)",
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
        "prasna_zusatz": [
            "The follow-up question in the Prāśna chart",
            "Answer & timing",
        ],
        "partner": [
            "Two charts at a glance",
            "Aṣṭakūṭa — the 36 guṇas in detail",
            "Vedha, Rajju & further Milāna factors",
            "Mangal Doṣa — the Mars examination",
            "Moon & emotional worlds compared",
            "Venus & Mars — attraction and expression",
            "The 7th house of both partners",
            "Mutual overlays",
            "Strengths of the bond",
            "Friction points & growth areas",
            "Summary & recommendation",
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
            "Behandle den Mond als Chandra Lagna — analog zur Lagna-Deutung. "
            "Die Häuser vom Mond stehen FERTIG BERECHNET im Feld "
            "'house_from_moon' jedes Planeten — verwende AUSSCHLIESSLICH diese "
            "Werte und zähle NIEMALS selbst. Deute die Mond-Qualität "
            "(Zeichen, Nakshatra mit Devata/Symbol, Pada, Würde, Affliktionen). "
            "Welche Planeten stehen in welchem 'house_from_moon'? "
            "Welche Yogas und Aspekte wirken auf das Chandra Lagna? "
            "Erkläre die emotionale Grundstruktur, das innere Erleben, "
            "und wie der Mond-Ātmakāraka (wenn zutreffend) wirkt.",
        "Pañcāṅga der Geburt — Die fünf Zeitqualitäten":
            "Deute AUSSCHLIESSLICH 'panchang_of_birth' — das Pañcāṅga des "
            "GEBURTSZEITPUNKTS, niemals des heutigen Tages. Erkläre die fünf "
            "Elemente der Geburt: Tithi (Mondtag mit Paksha und Fünfergruppe), "
            "Vara (Wochentag und Planetenherr), Nakshatra des Mondes, "
            "Nitya-Yoga und Karaṇa. Nutze die mitgelieferten 'interpretations' "
            "als Grundlage und verbinde sie mit dem Mond-Kapitel (das "
            "Pañcāṅga-Nakshatra IST das natale Mond-Nakshatra). Einen "
            "herausfordernden Nitya-Yoga oder eine Rikta-Tithi besonnen als "
            "Prägung und Lernqualität deuten, nicht als Makel. Kompakt: "
            "2–4 Absätze.",
        "Die Hausherren (Bhāveśa) — Wohin die Herren der Häuser gehen":
            "Dies ist ein KERNKAPITEL — arbeite es gründlich durch, "
            "ausschliesslich mit den Daten aus 'house_lords'. Prinzip: Der "
            "Herr eines Hauses trägt dessen Themen dorthin, wo er steht "
            "('Herr des X. im Y. Haus'). Beginne ausführlich mit dem "
            "LAGNA-HERRN (Haus 1): Wohin geht er, was bedeutet das für die "
            "Lebensausrichtung (z.B. Lagna-Herr im 10. = Karriere und "
            "öffentliches Wirken zentral für die Identität)? Dann JEDEN "
            "weiteren Herrn (2.–12.) in je 2–4 Sätzen: Haus-Thema → Zielhaus "
            "→ konkrete Lebensbedeutung. Beispiele der Logik: Herr des 3. "
            "zeigt, wie Geschwister, Mut und Initiative ins Leben wirken; "
            "Herr des 7. beschreibt, WO und WIE der Partner gefunden wird "
            "und welche Qualität die Partnerschaft prägt; Herr des 10. zeigt "
            "das Feld des beruflichen Wirkens. QUALIFIZIERE jeden Herrn "
            "zwingend: Würde ('dignity'), Shad-Bala-Stärke "
            "('shadbala_rupa'/'shadbala_strong'), Affliktionen "
            "('afflictions', z.B. Papakartari, Debilitation, Verbrennung/Asta, "
            "Graha Yuddha, Gandanta oder Rāśi-Sandhi, sowie "
            "'malefic_aspects_received', die empfangenen malefischen Aspekte "
            "— dann das Versprechen des Hauses gedämpft oder verzögert "
            "deuten) und den "
            "D9-Stand ('d9_sign'/'d9_house': bestätigt oder relativiert der "
            "Navāṃśa das D1-Versprechen?). Dusthana-Ziele (6/8/12) besonnen "
            "als Lernfelder deuten, nicht als Verhängnis. Keine Herren oder "
            "Stände erfinden, die nicht im JSON stehen.",
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
            "Wenn 'parivartana' vorhanden: deute den Tausch explizit — besonders ein "
            "Raja-Parivartana über Kendra/Trikona-Häuser ist eine berufliche "
            "Schlüssel-Konstellation; ein vermerktes Neecha Bhanga hebt die "
            "Debilitation auf. "
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
        "Aktuelle Transite (Gochara)":
            "Deute AUSSCHLIESSLICH die Daten aus 'transits_today'. "
            "Gewichte langsame Transite (Saturn, Jupiter, Rahu/Ketu) als "
            "prägende Phasen; schnelle (Sonne, Merkur, Venus, Mond) nur als "
            "kurzfristige Färbung oder gar nicht. Für jeden gewichteten Transit: "
            "'house_from_lagna' UND 'house_from_moon' benennen und deuten — "
            "beide stehen fertig im Transit-Datensatz, NIEMALS selbst zählen. "
            "Qualifiziere jeden Transit mit 'ashtakavarga_bindus'/'bindu_support' "
            "(≥5 Bindus = getragen, ≤3 = zäh). Wenn 'sade_sati.active' true ist, "
            "erkläre die Sade-Sati-Phase besonnen als Reifungszeit (keine "
            "Angstsprache); wenn false, erwähne Sade Sati NICHT. "
            "Verbinde die Transite ausdrücklich mit der laufenden Daśā aus "
            "'vimshottari_current': die Daśā ist die Bühne, der Transit der "
            "Auslöser. Keine eigenen Positionsberechnungen, keine Aussagen über "
            "Transite die nicht im JSON stehen. Das JSON enthält KEIN heutiges "
            "Pañcāṅga: 'panchang_of_birth' beschreibt ausschliesslich den "
            "Geburtsmoment — treffe in diesem Kapitel KEINE Aussagen über "
            "Tithi, Vara, Nakshatra, Yoga oder Karaṇa des heutigen Tages.",
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
        "Die Vertiefungsfrage im Prāśna-Chart":
            "Dies ist eine VERTIEFUNGSFRAGE zu einem bereits gedeuteten "
            "Prāśna: 'prasna_question' ist die neue Frage, "
            "'prasna_followup_of' die ursprüngliche. Das Chart ist der "
            "Moment der URSPRÜNGLICHEN Frage — deute die neue Frage aus "
            "genau diesem Chart, über die für ihr Thema zuständigen Häuser "
            "und Signifikatoren. Beziehe dich kurz auf den Zusammenhang zur "
            "ursprünglichen Frage, wiederhole deren Deutung aber nicht. "
            "Kompakt und fokussiert: dies ist eine gezielte Zusatzantwort, "
            "kein neuer Vollbericht.",
        "Prāśna — Die Frage & der Moment":
            "Beginne mit der Frage aus 'prasna_question'. Beschreibe den Prāśna-Moment: "
            "Lagna-Zeichen, Pañcāṅga (Tithi, Vara, Nakshatra). Ist der Moment günstig "
            "(Benefics im Lagna, zunehmender Mond) oder schwierig? "
            "Was sagt der erste Eindruck des Horoskops über die Frage? "
            "BESTIMME das THEMENHAUS der Frage (Partnerschaft/Ehe → 7, Beruf → 10, "
            "Geld → 2/11, Gesundheit → 6, Kinder → 5, Reise/Ausland → 3/9/12, Heim → 4) "
            "und prüfe es über die folgenden Kapitel hinweg VOLLSTÄNDIG: (a) seine "
            "BESETZER aus 'occupants' — jeder Planet im Themenhaus muss gewürdigt werden, "
            "Malefics (Saturn, Mars, Rahu/Ketu, Sonne) wie Benefics (Jupiter, Venus, "
            "Merkur, Mond); (b) empfangene ASPEKTE von Besetzern und Herrn aus 'aspects' — "
            "malefische UND benefische; (c) AFFLIKTIONEN aus 'afflictions' (Combustion, "
            "Gandanta, Sandhi, Yuddha, Papakartari).",
        "Lagna & Lagna-Herr — Der Fragesteller":
            "Das Lagna und sein Herr repräsentieren den Fragesteller (1. Person). "
            "Wo steht der Lagna-Herr (Haus, Zeichen, Würde)? Ist er stark oder schwach? "
            "PFLICHT: Prüfe 'lagna.lord_details' — insbesondere 'conjunctions_with_orb' "
            "und 'afflictions'. Steht der Lagneśa eng bei Ketu oder Rahu, ist er verbrannt, "
            "geschwächt oder in Gandanta/Sandhi, MUSS das hier explizit benannt und gedeutet "
            "werden (Ketu: Ablösung, Verneinung, verborgene Faktoren; Rahu: Verzerrung, "
            "Täuschung; Asta: überstrahlter Wille) — und im Schlusskapitel ins Urteil einfliessen. "
            "Aspektiert er das Lagna? Welche Häuser regiert er zusätzlich? "
            "Was sagt das über die Situation und den Geisteszustand des Fragestellers?",
        "7. Haus & Signifikator — Das Gegenüber":
            "Das 7. Haus und sein Herr repräsentieren das Gegenüber oder den Gegenstand der Frage. "
            "PFLICHT — in dieser Reihenfolge: (1) BESETZER des 7. Hauses aus 'occupants': Steht dort "
            "ein Planet (z.B. Saturn), MUSS er gewürdigt werden — Natur (malefisch/benefisch), Würde, "
            "Affliktionen aus 'afflictions', und was seine Präsenz für das Gegenüber bzw. die "
            "Verbindung konkret bedeutet (Saturn im 7. etwa: Ernst, Verzögerung, Prüfung, Dauer — "
            "auf die Frage bezogen, nicht generisch). (2) ASPEKTE, die das 7. Haus, seine Besetzer "
            "und sein Herr empfangen ('aspects'): malefische dämpfen oder verzögern, benefische "
            "stützen — beide Seiten benennen. (3) Der 7. HERR: Wo steht er, wie stark (Shad Bala), "
            "wie affligiert? Bestimme zusätzlich den natürlichen Signifikator des Fragethemas "
            "(H10-Herr für Beruf, Venus für Beziehung, H2-Herr für Geld etc.) aus 'prasna_question'. "
            "Gibt es eine Verbindung zum Lagna-Herrn? Ein unerwähnter Planet im 7. Haus ist ein "
            "methodischer Fehler.",
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
            "Welche Faktoren begünstigen, welche erschweren die Erfüllung? Die Bilanz MUSS "
            "die Besetzer und empfangenen Aspekte des Themenhauses der Frage sowie alle "
            "Affliktionen der Signifikatoren einbeziehen. "
            "Schluss mit einer konkreten, ermutigenden Orientierung.",
        "Zwei Horoskope im Überblick":
            "Stelle beide Personen kurz vor ('person_a' / 'person_b'): Lagna und sein "
            "Herr (inkl. 'lord_condition'), Mond mit Nakshatra und Pada, prägende Würden "
            "und Affliktionen. Gleichgewichtig — etwa gleich viel Text pro Person. "
            "Noch KEINE Bewertung der Passung.",
        "Aṣṭakūṭa — Die 36 Guṇas im Detail":
            "Gehe alle 8 Kūṭas aus 'ashtakuta' einzeln durch (Varṇa, Vaśya, Tārā, Yoni, "
            "Graha-Maitrī, Gaṇa, Bhakūṭa, Nādi): erreichte vs. maximale Punkte und was der "
            "Befund KONKRET für dieses Paar bedeutet — nicht generisch. Ein Nādi- oder "
            "Bhakūṭa-Doṣa MUSS klar benannt werden, ebenso im JSON vermerkte Aufhebungen. "
            "Schliesse mit der Gesamtpunktzahl und ihrer Einordnung.",
        "Vedha, Rajju & weitere Milāna-Faktoren":
            "Deute die Befunde aus 'extra_milana': Vedha (gegenseitige Blockade der "
            "Janma-Nakshatras), Rajju (gleiche Körperzone der Nakshatra-Kette), "
            "Strī-Dīrgha und Rāśi-Kūṭa. Positive Befunde als Ressource würdigen, negative "
            "ehrlich als ernste Prüfpunkte benennen — sachlich, ohne Drama.",
        "Mangal Doṣa — Die Mars-Prüfung":
            "Verwende ausschliesslich 'mangal': Wer hat den Doṣa und aus welchen Häusern? "
            "Hebt er sich gegenseitig auf ('verdict')? Erkläre kurz, was Mangal Doṣa "
            "klassisch bedeutet (Mars-Energie in beziehungssensiblen Häusern) und was der "
            "konkrete Befund für DIESES Paar heisst.",
        "Mond & Gefühlswelt im Vergleich":
            "Vergleiche beide Monde ('person_a.moon' / 'person_b.moon'): Element des "
            "Zeichens, Nakshatra-Qualität, Würde, Affliktionen. Wie fühlt, verarbeitet "
            "und braucht jede Person? Wo nähren sich die Gefühlswelten gegenseitig, "
            "wo drohen Missverständnisse?",
        "Venus & Mars — Anziehung und Ausdruck":
            "Deute Venus (Liebesausdruck, Genuss, Wertschätzung) und Mars (Initiative, "
            "Begehren, Konfliktstil) beider Personen inkl. Würde und Affliktionen. Ein "
            "affligierter Beziehungssignifikator (verbrannte Venus, enge Ketu-/Rahu-"
            "Konjunktion, Debilitation) MUSS benannt und in die Bewertung einbezogen werden.",
        "Das 7. Haus beider Partner":
            "Für beide Personen: Zeichen des 7. Hauses, Zustand des 7.-Haus-Herrn "
            "('house7.lord_condition') und Besetzer ('house7.occupants'). Was sucht jede "
            "Person in Partnerschaft, wie bindet sie sich? Besetzer des 7. Hauses — auch "
            "Malefics — müssen gewürdigt werden; ein unerwähnter Planet im 7. Haus ist "
            "ein methodischer Fehler.",
        "Gegenseitige Überlagerungen (Overlays)":
            "Nutze 'overlay_b_in_a' und 'overlay_a_in_b': In welche Häuser des einen "
            "fallen Mond, Venus, Mars, Sonne und Jupiter des anderen? Kendra/Trikona "
            "(1, 4, 5, 7, 9, 10) verbindet und stützt, 2/11 nährt, Duḥsthāna (6, 8, 12) "
            "fordert. Konkret auf Alltag und Zusammenleben bezogen deuten — beide "
            "Richtungen, nicht nur eine.",
        "Stärken der Verbindung":
            "Bündle die drei bis fünf tragfähigsten Faktoren aus allen vorigen Kapiteln — "
            "jeweils mit klarer Begründung aus den Fakten (Kūṭa, Overlay, Würde), "
            "nicht generisch.",
        "Reibungspunkte & Wachstumsfelder":
            "Benenne die wichtigsten Spannungsfaktoren (Doṣas, schwache Kūṭas, "
            "schwierige Overlays, affligierte Signifikatoren) ehrlich — und zu JEDEM "
            "einen konstruktiven Umgang. Keine Angstsprache, keine Bagatellisierung.",
        "Zusammenfassung & Empfehlung":
            "Führe alles zu einem ausgewogenen Gesamtbild zusammen: Gesamtpunktzahl, "
            "gewichtige Doṣas und ihre Aufhebungen, tragende Ressourcen. Formuliere eine "
            "qualifizierte Einschätzung der Passung und zwei bis drei konkrete "
            "Empfehlungen. KEIN absolutes Urteil über Heirat oder Trennung.",
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
            "Treat the Moon as Chandra Lagna — analogous to the Ascendant reading. "
            "The houses from the Moon are PRE-COMPUTED in each planet's "
            "'house_from_moon' field — use ONLY these values and NEVER count "
            "yourself. Interpret Moon quality "
            "(sign, nakshatra with devata/symbol, pada, dignity, afflictions). "
            "Which planets sit in which 'house_from_moon'? "
            "Which yogas and aspects act on the Chandra Lagna? "
            "Explain the emotional foundation, inner experience, "
            "and how the Moon-Ātmakāraka (if applicable) functions.",
        "Pañcāṅga of Birth — The five time qualities":
            "Interpret ONLY 'panchang_of_birth' — the Pañcāṅga of the MOMENT "
            "OF BIRTH, never of today. Explain the five elements of the birth: "
            "Tithi (lunar day with paksha and five-group), Vara (weekday and "
            "planetary lord), the Moon's nakshatra, Nitya yoga and Karaṇa. "
            "Use the supplied 'interpretations' as the basis and connect them "
            "to the Moon chapter (the Pañcāṅga nakshatra IS the natal Moon "
            "nakshatra). Interpret a challenging Nitya yoga or a Rikta tithi "
            "calmly as an imprint and learning quality, not a flaw. Compact: "
            "2–4 paragraphs.",
        "The House Lords (Bhāveśa) — Where the lords of the houses go":
            "This is a CORE CHAPTER — work through it thoroughly, using only "
            "the data in 'house_lords'. Principle: the lord of a house "
            "carries its themes to wherever he stands ('lord of X in house "
            "Y'). Begin at length with the LAGNA LORD (house 1): where does "
            "he go, what does this mean for the life direction (e.g. Lagna "
            "lord in the 10th = career and public action central to "
            "identity)? Then EVERY further lord (2nd–12th) in 2–4 sentences "
            "each: house theme → target house → concrete life meaning. "
            "Examples of the logic: the 3rd lord shows how siblings, courage "
            "and initiative act in the life; the 7th lord describes WHERE "
            "and HOW the partner is found and what quality shapes the "
            "partnership; the 10th lord shows the field of professional "
            "action. QUALIFY every lord without exception: dignity "
            "('dignity'), Shad Bala strength ('shadbala_rupa'/"
            "'shadbala_strong'), afflictions ('afflictions', e.g. "
            "Papakartari, debilitation, combustion/Asta, Graha Yuddha, "
            "Gandanta or Rashi Sandhi, plus 'malefic_aspects_received', "
            "the malefic aspects the lord receives — then read the house's "
            "promise as dampened or delayed) and the D9 placement ('d9_sign'/"
            "'d9_house': does the Navāṃśa confirm or qualify the D1 "
            "promise?). Read dusthana targets (6/8/12) calmly as learning "
            "fields, not doom. Do not invent lords or placements not in the "
            "JSON.",
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
        "Current Transits (Gochara)":
            "Interpret ONLY the data in 'transits_today'. Weight slow transits "
            "(Saturn, Jupiter, Rahu/Ketu) as phase-defining; fast ones (Sun, "
            "Mercury, Venus, Moon) only as short-term colouring or not at all. "
            "For each weighted transit name and interpret the house from the "
            "Lagna AND from the Moon (Chandra Lagna). Qualify every transit "
            "with 'ashtakavarga_bindus'/'bindu_support' (≥5 bindus = supported, "
            "≤3 = sluggish). If 'sade_sati.active' is true, explain the Sade "
            "Sati phase calmly as a maturation period (no fear language); if "
            "false, do NOT mention Sade Sati. Explicitly connect transits to "
            "the running dasha from 'vimshottari_current': the dasha is the "
            "stage, the transit the trigger. No own position calculations, no "
            "claims about transits not present in the JSON. The JSON contains "
            "NO panchang for today: 'panchang_of_birth' describes the birth "
            "moment only — make NO statements about today's tithi, vara, "
            "nakshatra, yoga or karana in this chapter.",
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
        "The follow-up question in the Prāśna chart":
            "This is a FOLLOW-UP question to an already interpreted praśna: "
            "'prasna_question' is the new question, 'prasna_followup_of' the "
            "original one. The chart is the moment of the ORIGINAL question "
            "— read the new question from exactly this chart, via the houses "
            "and significators responsible for its theme. Briefly relate it "
            "to the original question without repeating that reading. "
            "Compact and focused: this is a targeted additional answer, not "
            "a new full report.",
        "Prāśna — The question & the moment":
            "Begin with the question from 'prasna_question'. Describe the Prāśna moment: "
            "Lagna sign, Pañcāṅga (Tithi, Vara, Nakshatra). Is the moment favourable "
            "(benefics in Lagna, waxing Moon) or difficult? "
            "What does the first impression of the chart say about the question? "
            "DETERMINE the THEME HOUSE of the question (partnership/marriage → 7, career → 10, "
            "money → 2/11, health → 6, children → 5, travel/abroad → 3/9/12, home → 4) and "
            "assess it FULLY across the following chapters: (a) its OCCUPANTS from 'occupants' — "
            "every planet in the theme house must be assessed, malefics (Saturn, Mars, Rahu/Ketu, "
            "Sun) as well as benefics (Jupiter, Venus, Mercury, Moon); (b) ASPECTS received by "
            "occupants and lord from 'aspects' — malefic AND benefic; (c) AFFLICTIONS from "
            "'afflictions' (combustion, Gandanta, Sandhi, Yuddha, Papakartari).",
        "Lagna & Lagna lord — The querent":
            "The Lagna and its lord represent the querent. "
            "Where is the Lagna lord (house, sign, dignity)? Strong or weak? "
            "MANDATORY: Check 'lagna.lord_details' — especially 'conjunctions_with_orb' "
            "and 'afflictions'. If the Lagnesha is closely conjunct Ketu or Rahu, combust, "
            "debilitated or in Gandanta/Sandhi, this MUST be named and interpreted here "
            "(Ketu: severance, negation, hidden factors; Rahu: distortion, deception; "
            "Asta: overshadowed will) — and carried into the final verdict. "
            "Does it aspect the Lagna? What additional houses does it rule? "
            "What does this say about the querent's situation and state of mind?",
        "7th house & significator — The matter":
            "The 7th house and its lord represent the other party or matter asked about. "
            "MANDATORY — in this order: (1) OCCUPANTS of the 7th house from 'occupants': if a "
            "planet sits there (e.g. Saturn), it MUST be assessed — its nature (malefic/benefic), "
            "dignity, afflictions from 'afflictions', and what its presence concretely means for "
            "the other party or the bond (Saturn in the 7th: seriousness, delay, testing, "
            "durability — related to the question, not generic). (2) ASPECTS received by the 7th "
            "house, its occupants and its lord ('aspects'): malefic ones dampen or delay, benefic "
            "ones support — name both sides. (3) The 7th LORD: placement, strength (Shad Bala), "
            "afflictions. Identify the natural significator of the topic from 'prasna_question' "
            "(H10 lord for career, Venus for relationship, H2 lord for money). Is there a "
            "connection to the Lagna lord? An unmentioned planet in the 7th house is a "
            "methodological error.",
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
            "The final weighing MUST include the occupants and received aspects of the "
            "question's theme house and all afflictions of the significators. "
            "Close with a concrete, encouraging orientation.",
        "Two charts at a glance":
            "Introduce both persons briefly ('person_a' / 'person_b'): Lagna and its lord "
            "(incl. 'lord_condition'), Moon with nakshatra and pada, defining dignities and "
            "afflictions. Balanced — roughly equal text per person. NO compatibility "
            "assessment yet.",
        "Aṣṭakūṭa — the 36 guṇas in detail":
            "Walk through all 8 kutas from 'ashtakuta' (Varna, Vashya, Tara, Yoni, "
            "Graha Maitri, Gana, Bhakuta, Nadi): achieved vs. maximum points and what the "
            "finding means CONCRETELY for this couple — not generically. A Nadi or Bhakuta "
            "dosha MUST be named clearly, as must cancellations noted in the JSON. "
            "Close with the total score and its classification.",
        "Vedha, Rajju & further Milāna factors":
            "Interpret the findings in 'extra_milana': Vedha (mutual obstruction of the "
            "janma nakshatras), Rajju (same body zone of the nakshatra chain), Stri-Dirgha "
            "and Rasi Kuta. Honour positive findings as resources, name negative ones "
            "honestly as serious checkpoints — factually, without drama.",
        "Mangal Doṣa — the Mars examination":
            "Use only 'mangal': who has the dosha and from which houses? Does it cancel "
            "mutually ('verdict')? Briefly explain what Mangal Dosha classically means "
            "(Mars energy in relationship-sensitive houses) and what the concrete finding "
            "means for THIS couple.",
        "Moon & emotional worlds compared":
            "Compare both Moons ('person_a.moon' / 'person_b.moon'): element of the sign, "
            "nakshatra quality, dignity, afflictions. How does each person feel, process "
            "and need? Where do the emotional worlds nourish each other, where do "
            "misunderstandings loom?",
        "Venus & Mars — attraction and expression":
            "Interpret Venus (expression of love, enjoyment, appreciation) and Mars "
            "(initiative, desire, conflict style) of both persons incl. dignity and "
            "afflictions. An afflicted relationship significator (combust Venus, tight "
            "Ketu/Rahu conjunction, debilitation) MUST be named and weighed.",
        "The 7th house of both partners":
            "For both persons: sign of the 7th house, condition of the 7th lord "
            "('house7.lord_condition') and occupants ('house7.occupants'). What does each "
            "person seek in partnership, how do they bond? Occupants of the 7th house — "
            "including malefics — must be honoured; an unmentioned planet in the 7th "
            "house is a methodological error.",
        "Mutual overlays":
            "Use 'overlay_b_in_a' and 'overlay_a_in_b': into which houses of one person "
            "do the other's Moon, Venus, Mars, Sun and Jupiter fall? Kendra/Trikona "
            "(1, 4, 5, 7, 9, 10) connects and supports, 2/11 nourishes, dusthana "
            "(6, 8, 12) challenges. Interpret concretely for daily life and living "
            "together — both directions, not just one.",
        "Strengths of the bond":
            "Bundle the three to five most sustaining factors from all previous chapters — "
            "each with clear justification from the facts (kuta, overlay, dignity), "
            "not generic.",
        "Friction points & growth areas":
            "Name the most important tension factors (doshas, weak kutas, difficult "
            "overlays, afflicted significators) honestly — and for EACH one a "
            "constructive way of handling it. No fear language, no trivialising.",
        "Summary & recommendation":
            "Bring everything together into a balanced overall picture: total score, "
            "weighty doshas and their cancellations, sustaining resources. Formulate a "
            "qualified assessment of the match and two to three concrete recommendations. "
            "NO absolute verdict on marriage or separation.",
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

    if depth not in ("basis", "premium", "year", "prasna", "partner"):
        depth = "premium"
    if max_tokens == 0:
        max_tokens = (4000 if depth == "basis"
                      else 6000 if depth in ("prasna", "year")
                      else 10000 if depth == "partner"
                      else 16000)

    facts  = build_facts(chart, depth=depth)
    if depth == "prasna":
        system_key = f"prasna_{lang}"
    elif depth == "partner":
        system_key = f"partner_{lang}"
    else:
        system_key = lang
    system = _BASE_RULES.get(system_key, _BASE_RULES[lang])
    prompt = build_prompt(facts, lang, depth)

    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": prompt}]
    full_text = ""

    def _create_with_retry(**kwargs):
        """API-Call mit Backoff bei transienten Fehlern (Rate-Limit, Overloaded,
        Verbindungsabbruch). Ein bezahlter Bericht darf nicht an einem
        kurzzeitigen 429/5xx scheitern. Andere Fehler (z.B. 400) sofort werfen."""
        import time as _time
        transient = (anthropic.RateLimitError, anthropic.InternalServerError,
                     anthropic.APIConnectionError, anthropic.APITimeoutError)
        delays = (3, 8, 20)          # Sekunden zwischen den Versuchen
        for i in range(len(delays) + 1):
            try:
                return client.messages.create(**kwargs)
            except transient as e:
                if i == len(delays):
                    raise
                print(f"ai_report: transienter API-Fehler "
                      f"({type(e).__name__}), Retry in {delays[i]}s ...")
                _time.sleep(delays[i])

    for _attempt in range(3):  # allow up to 2 continuations
        resp = _create_with_retry(
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

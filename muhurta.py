# -*- coding: utf-8 -*-
"""
muhurta.py — Monats-Muhurta-Engine für AstroVeda
=================================================

Berechnet für einen Kalendermonat alle Pañcāṅga-Segmente (Vara, Tithi,
Nakṣatra, Karaṇa, Nitya-Yoga) mit exakten Übergangszeiten und bewertet
jedes Segment mit gut / neutral / ungünstig — analog zur Kala-Darstellung.

Zwei Modi:
  * neutral        — ohne Geburtsbezug (keine Tārā-Zeile)
  * personalisiert — janma_nakshatra_index (0=Aśvinī … 26=Revatī) gesetzt,
                     zusätzliche Tārā-Zeile (9er-Zählung ab Janma-Nakṣatra)

Konventionen (wie im restlichen AstroVeda-Stack):
  * Swiss Ephemeris, Lahiri-Ayanāṃśa
  * swe.set_sid_mode() wird vor JEDER Berechnung erneut gesetzt
  * Zeitzonen historisch korrekt via zoneinfo
  * Vara läuft von Sonnenaufgang zu Sonnenaufgang (Hindu rising,
    Scheibenmitte ohne Refraktion; Fallback: normaler Aufgang)

Öffentliche API:
    month_muhurta(year, month, lat, lon, tzname,
                  janma_nakshatra_index=None) -> dict (JSON-serialisierbar)
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import swisseph as swe

AYANAMSHA = swe.SIDM_LAHIRI
_FLAGS = swe.FLG_SWIEPH | swe.FLG_SIDEREAL

# ---------------------------------------------------------------- Namen ---

NAKSHATRA_NAMES = [
    "Aśvinī", "Bharaṇī", "Kṛttikā", "Rohiṇī", "Mṛgaśira", "Ārdrā",
    "Punarvasu", "Puṣya", "Āśleṣā", "Maghā", "Pūrva Phalgunī",
    "Uttara Phalgunī", "Hasta", "Citrā", "Svātī", "Viśākhā", "Anurādhā",
    "Jyeṣṭhā", "Mūla", "Pūrva Āṣāḍhā", "Uttara Āṣāḍhā", "Śravaṇa",
    "Dhaniṣṭhā", "Śatabhiṣā", "Pūrva Bhādrapadā", "Uttara Bhādrapadā",
    "Revatī",
]

TITHI_NAMES = [
    "Pratipadā", "Dvitīyā", "Tṛtīyā", "Caturthī", "Pañcamī", "Ṣaṣṭhī",
    "Saptamī", "Aṣṭamī", "Navamī", "Daśamī", "Ekādaśī", "Dvādaśī",
    "Trayodaśī", "Caturdaśī", "Pūrṇimā",
    "Pratipadā", "Dvitīyā", "Tṛtīyā", "Caturthī", "Pañcamī", "Ṣaṣṭhī",
    "Saptamī", "Aṣṭamī", "Navamī", "Daśamī", "Ekādaśī", "Dvādaśī",
    "Trayodaśī", "Caturdaśī", "Amāvasyā",
]

YOGA_NAMES = [
    "Viṣkambha", "Prīti", "Āyuṣmān", "Saubhāgya", "Śobhana", "Atigaṇḍa",
    "Sukarma", "Dhṛti", "Śūla", "Gaṇḍa", "Vṛddhi", "Dhruva", "Vyāghāta",
    "Harṣaṇa", "Vajra", "Siddhi", "Vyatīpāta", "Varīyān", "Parigha",
    "Śiva", "Siddha", "Sādhya", "Śubha", "Śukla", "Brahma", "Indra",
    "Vaidhṛti",
]

KARANA_MOVABLE = ["Bava", "Bālava", "Kaulava", "Taitila", "Gara",
                  "Vaṇija", "Viṣṭi"]
KARANA_FIXED = {57: "Śakuni", 58: "Catuṣpada", 59: "Nāga", 0: "Kiṃstughna"}

TARA_NAMES = [
    "Janma", "Sampat", "Vipat", "Kṣema", "Pratyari",
    "Sādhaka", "Vadha", "Maitra", "Parama Maitra",
]

VARA_NAMES_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
                 "Freitag", "Samstag", "Sonntag"]  # Python weekday()

# ------------------------------------------------------------ Bewertung ---
# quality: "good" | "mixed" | "bad"

# Vara: Mo/Mi/Do/Fr gut, So neutral, Di/Sa ungünstig
VARA_QUALITY = {0: "good", 1: "bad", 2: "good", 3: "good",
                4: "good", 5: "bad", 6: "mixed"}

# Tithi (Index 0..29): Riktā (4., 9., 14. jeder Pakṣa) + Amāvasyā rot,
# Pratipadā gemischt, Rest grün
_RIKTA = {3, 8, 13, 18, 23, 28}


def _tithi_quality(i):
    if i in _RIKTA or i == 29:
        return "bad"
    if i in (0, 15):
        return "mixed"
    return "good"


# Nakṣatra nach Natur-Gruppen
_NAK_GOOD = {0, 7, 12,            # Kṣipra: Aśvinī, Puṣya, Hasta
             4, 13, 16, 26,       # Mṛdu: Mṛgaśira, Citrā, Anurādhā, Revatī
             3, 11, 20, 25}       # Dhruva: Rohiṇī, U.Phalgunī, U.Āṣāḍhā, U.Bhādrapadā
_NAK_BAD = {1, 9, 10, 19, 24,     # Ugra: Bharaṇī, Maghā, P.Phalgunī, P.Āṣāḍhā, P.Bhādrapadā
            18, 17, 5, 8}         # Tīkṣṇa: Mūla, Jyeṣṭhā, Ārdrā, Āśleṣā
# Rest (Cara + Miśra) = mixed


def _nak_quality(i):
    if i in _NAK_GOOD:
        return "good"
    if i in _NAK_BAD:
        return "bad"
    return "mixed"


# Karaṇa: Viṣṭi (Bhadrā) und die vier festen ungünstig
def _karana_name(i):
    if i in KARANA_FIXED:
        return KARANA_FIXED[i]
    return KARANA_MOVABLE[(i - 1) % 7]


def _karana_quality(i):
    if i in KARANA_FIXED:
        return "bad"
    return "bad" if _karana_name(i) == "Viṣṭi" else "good"


# Nitya-Yoga: die 9 klassisch ungünstigen
_YOGA_BAD = {0, 5, 8, 9, 12, 14, 16, 18, 26}


def _yoga_quality(i):
    return "bad" if i in _YOGA_BAD else "good"


# Tārā: 3 (Vipat), 5 (Pratyari), 7 (Vadha) rot; 1 (Janma) gemischt
def _tara_quality(t):  # t = 1..9
    if t in (3, 5, 7):
        return "bad"
    if t == 1:
        return "mixed"
    return "good"


# ------------------------------------------------------------ Ephemeris ---

def _moon_sun(jd_ut):
    """Siderische Längen von Mond und Sonne (Lahiri)."""
    swe.set_sid_mode(AYANAMSHA, 0, 0)
    moon = swe.calc_ut(jd_ut, swe.MOON, _FLAGS)[0][0] % 360.0
    sun = swe.calc_ut(jd_ut, swe.SUN, _FLAGS)[0][0] % 360.0
    return moon, sun


def _tithi_index(jd):
    m, s = _moon_sun(jd)
    return int(((m - s) % 360.0) / 12.0)          # 0..29


def _karana_index(jd):
    m, s = _moon_sun(jd)
    return int(((m - s) % 360.0) / 6.0)           # 0..59


def _nak_index(jd):
    m, _ = _moon_sun(jd)
    return int(m / (360.0 / 27.0))                # 0..26


def _yoga_index(jd):
    m, s = _moon_sun(jd)
    return int(((m + s) % 360.0) / (360.0 / 27.0))  # 0..26


# ------------------------------------------------------- Zeit-Hilfsmittel ---

def _jd_from_local(dt_local):
    dt_ut = dt_local.astimezone(timezone.utc)
    return swe.julday(dt_ut.year, dt_ut.month, dt_ut.day,
                      dt_ut.hour + dt_ut.minute / 60.0
                      + dt_ut.second / 3600.0)


def _local_from_jd(jd_ut, tz):
    y, mo, d, h = swe.revjul(jd_ut)
    hh = int(h)
    mm = int((h - hh) * 60)
    ss = int(round((((h - hh) * 60) - mm) * 60))
    if ss == 60:
        ss, mm = 0, mm + 1
    if mm == 60:
        mm, hh = 0, hh + 1
    dt_ut = datetime(y, mo, d, min(hh, 23), mm, ss, tzinfo=timezone.utc)
    if hh == 24:
        dt_ut += timedelta(hours=1)
    return dt_ut.astimezone(tz)


# --------------------------------------------------------- Segment-Suche ---

def _scan_segments(idx_func, jd0, jd1, coarse_hours=1.0, precision_min=1.0):
    """Findet [start, ende, index]-Segmente einer Stufenfunktion.

    Grobschritt 1 h ist sicher: Tithi/Nakṣatra/Yoga wechseln ~1×/Tag,
    Karaṇa ~2×/Tag.
    """
    step = coarse_hours / 24.0
    prec = precision_min / 1440.0
    segs = []
    jd = jd0
    cur = idx_func(jd)
    seg_start = jd
    while jd < jd1 - 1e-9:
        nxt = min(jd + step, jd1)
        val = idx_func(nxt)
        if val != cur:
            lo, hi = jd, nxt
            while hi - lo > prec:
                mid = (lo + hi) / 2.0
                if idx_func(mid) == cur:
                    lo = mid
                else:
                    hi = mid
            segs.append([seg_start, hi, cur])
            seg_start = hi
            cur = val
        jd = nxt
    segs.append([seg_start, jd1, cur])
    return segs


def _sunrise_jd(jd_after, lat, lon):
    """Nächster Sonnenaufgang nach jd_after (Hindu rising, mit Fallback)."""
    geopos = (lon, lat, 0.0)
    rsmi = swe.CALC_RISE
    try:
        rsmi |= swe.BIT_HINDU_RISING
    except AttributeError:
        pass
    try:
        res, tret = swe.rise_trans(jd_after, swe.SUN, rsmi, geopos)
        if res == 0:
            return tret[0]
    except Exception:
        pass
    # Fallback: normaler Aufgang
    res, tret = swe.rise_trans(jd_after, swe.SUN, swe.CALC_RISE, geopos)
    return tret[0] if res == 0 else None


def _vara_segments(jd0, jd1, lat, lon, tz):
    """Vara-Segmente Sonnenaufgang→Sonnenaufgang, überlappend mit [jd0,jd1]."""
    segs = []
    # Ersten Aufgang VOR jd0 finden
    sr = _sunrise_jd(jd0 - 2.0, lat, lon)
    while sr is not None:
        nxt = _sunrise_jd(sr + 0.02, lat, lon)
        if nxt is None or nxt <= sr:
            break
        if sr > jd0:
            break
        if nxt > jd0:
            # sr <= jd0 < nxt: erstes relevantes Segment gefunden
            break
        sr = nxt
    while sr is not None and sr < jd1:
        nxt = _sunrise_jd(sr + 0.02, lat, lon)
        if nxt is None:
            break
        wd = _local_from_jd(sr, tz).weekday()
        segs.append([max(sr, jd0), min(nxt, jd1), wd])
        sr = nxt
    return segs


# ------------------------------------------------------------- Haupt-API ---

def month_muhurta(year, month, lat, lon, tzname,
                  janma_nakshatra_index=None):
    """Komplette Monats-Muhurta-Matrix als JSON-serialisierbares dict."""
    tz = ZoneInfo(tzname)
    start_local = datetime(year, month, 1, 0, 0, 0, tzinfo=tz)
    if month == 12:
        end_local = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=tz)
    else:
        end_local = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=tz)

    jd0 = _jd_from_local(start_local)
    jd1 = _jd_from_local(end_local)
    span = jd1 - jd0

    def _pack(jds, jde, label, sub, quality):
        return {
            "start": _local_from_jd(jds, tz).isoformat(timespec="minutes"),
            "end": _local_from_jd(jde, tz).isoformat(timespec="minutes"),
            "p0": round((jds - jd0) / span, 6),
            "p1": round((jde - jd0) / span, 6),
            "label": label,
            "sub": sub,
            "quality": quality,
        }

    rows = []

    # --- Vara -------------------------------------------------------------
    vara_raw = _vara_segments(jd0, jd1, lat, lon, tz)
    rows.append({
        "key": "vara", "label": "Vara",
        "segments": [_pack(a, b, VARA_NAMES_DE[wd], "",
                           VARA_QUALITY[wd]) for a, b, wd in vara_raw],
    })

    # --- Tithi ------------------------------------------------------------
    tithi_raw = _scan_segments(_tithi_index, jd0, jd1)
    rows.append({
        "key": "tithi", "label": "Tithi",
        "segments": [_pack(a, b, TITHI_NAMES[i],
                           "Śukla" if i < 15 else "Kṛṣṇa",
                           _tithi_quality(i)) for a, b, i in tithi_raw],
    })

    # --- Nakṣatra (+ Tārā) --------------------------------------------------
    nak_raw = _scan_segments(_nak_index, jd0, jd1)
    rows.append({
        "key": "nakshatra", "label": "Nakṣatra",
        "segments": [_pack(a, b, NAKSHATRA_NAMES[i], "",
                           _nak_quality(i)) for a, b, i in nak_raw],
    })

    if janma_nakshatra_index is not None:
        j = int(janma_nakshatra_index) % 27
        tara_segs = []
        for a, b, i in nak_raw:
            t = ((i - j) % 27) % 9 + 1
            tara_segs.append(_pack(
                a, b, "{} — {}".format(t, TARA_NAMES[t - 1]),
                NAKSHATRA_NAMES[i], _tara_quality(t)))
        rows.append({"key": "tara", "label": "Tārā", "segments": tara_segs})

    # --- Karaṇa -------------------------------------------------------------
    kar_raw = _scan_segments(_karana_index, jd0, jd1, coarse_hours=0.5)
    rows.append({
        "key": "karana", "label": "Karaṇa",
        "segments": [_pack(a, b, _karana_name(i), "",
                           _karana_quality(i)) for a, b, i in kar_raw],
    })

    # --- Nitya-Yoga ----------------------------------------------------------
    yoga_raw = _scan_segments(_yoga_index, jd0, jd1)
    rows.append({
        "key": "yoga", "label": "Nitya-Yoga",
        "segments": [_pack(a, b, YOGA_NAMES[i], "",
                           _yoga_quality(i)) for a, b, i in yoga_raw],
    })

    # --- Kombinierte Bewertung ----------------------------------------------
    rank = {"good": 0, "mixed": 1, "bad": 2}
    inv = {0: "good", 1: "mixed", 2: "bad"}
    boundaries = {jd0, jd1}
    lookup = []  # (jd_a, jd_b, rank) pro Zeile
    for row in rows:
        per_row = []
        for seg in row["segments"]:
            a = jd0 + seg["p0"] * span
            b = jd0 + seg["p1"] * span
            boundaries.add(a)
            boundaries.add(b)
            per_row.append((a, b, rank[seg["quality"]]))
        lookup.append(per_row)

    pts = sorted(boundaries)

    def _rank_at(per_row, jd):
        for a, b, r in per_row:
            if a - 1e-9 <= jd <= b + 1e-9:
                return r
        return 1

    combo = []
    for k in range(len(pts) - 1):
        a, b = pts[k], pts[k + 1]
        if b - a < 1e-7:
            continue
        mid = (a + b) / 2.0
        worst = max(_rank_at(pr, mid) for pr in lookup)
        if combo and combo[-1][2] == worst and abs(combo[-1][1] - a) < 1e-7:
            combo[-1][1] = b
        else:
            combo.append([a, b, worst])
    rows.append({
        "key": "gesamt", "label": "Gesamt",
        "segments": [_pack(a, b, {"good": "Günstig", "mixed": "Neutral",
                                  "bad": "Ungünstig"}[inv[r]], "",
                           inv[r]) for a, b, r in combo],
    })

    # --- Tagesraster für die Kopfzeile ---------------------------------------
    days = []
    d = start_local
    wd_abbr = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    while d < end_local:
        nd = d + timedelta(days=1)
        days.append({
            "date": d.date().isoformat(),
            "day": d.day,
            "wd": wd_abbr[d.weekday()],
            "p0": round((_jd_from_local(d) - jd0) / span, 6),
            "p1": round((min(_jd_from_local(nd), jd1) - jd0) / span, 6),
        })
        d = nd

    return {
        "year": year, "month": month, "tz": tzname,
        "lat": lat, "lon": lon,
        "mode": "personalisiert" if janma_nakshatra_index is not None
                else "neutral",
        "janma_nakshatra_index": janma_nakshatra_index,
        "janma_nakshatra": (NAKSHATRA_NAMES[int(janma_nakshatra_index) % 27]
                            if janma_nakshatra_index is not None else None),
        "days": days,
        "rows": rows,
    }

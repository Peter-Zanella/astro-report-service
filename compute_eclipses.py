#!/usr/bin/env python3
"""
compute_eclipses.py — One-time precomputation of solar & lunar eclipses.

Generates eclipse_database.json: every solar and lunar eclipse from START_YEAR
to END_YEAR, with sidereal (Lahiri) position of the eclipsed luminary
(Sun for solar, Moon for lunar), sign, degree, nakshatra, eclipse type,
and visibility from Wädenswil, Switzerland.

Run ONCE (locally or on Render where pyswisseph is installed):
    python compute_eclipses.py

The Jyotiṣa principle is preserved: Swiss Ephemeris computes every position;
this script only records the results into a static asset. The web service
then reads eclipse_database.json via eclipse_db.py (pure lookup, no calc).
"""
import json
import os
import sys

try:
    import swisseph as swe
except ImportError:
    sys.exit("pyswisseph not installed. Run this where Swiss Ephemeris is available "
             "(e.g. on Render, or `pip install pyswisseph`).")

# ── Configuration ─────────────────────────────────────────────────────────────
START_YEAR = 1940
END_YEAR   = 2100          # generous forward horizon; trim in UI if wanted
EPHE_PATH  = ""            # set if you ship .se1 files; empty = Moshier fallback

# Wädenswil, Switzerland (for visibility check)
OBS_LAT = 47.2300
OBS_LON = 8.6700
OBS_ALT = 408.0

_HERE    = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(_HERE, "eclipse_database.json")

SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
         "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishtha",
    "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati",
]

# ── Swiss Ephemeris init (mirrors astro_engine.py) ────────────────────────────
swe.set_ephe_path(EPHE_PATH or None)
swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)


def _sidereal_lon(jd_ut, body):
    """Sidereal (Lahiri) longitude of a body at jd_ut. Re-sets sid mode each call."""
    swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
    xx, _ = swe.calc_ut(jd_ut, body, swe.FLG_SIDEREAL | swe.FLG_SWIEPH)
    return xx[0] % 360.0


def _sign_deg(lon):
    """Return (sign_idx, sign_name, deg_in_sign, deg_str)."""
    idx = int(lon // 30) % 12
    deg = lon % 30
    d = int(deg)
    m = int((deg - d) * 60)
    return idx, SIGNS[idx], deg, f"{d}\u00b0 {m:02d}'"


def _nakshatra(lon):
    span = 360 / 27
    idx = int(lon / span) % 27
    pada = int((lon % span) / (span / 4)) + 1
    return NAKSHATRAS[idx], pada


def _solar_type(retflag):
    if retflag & swe.ECL_TOTAL:        return "Total"
    if retflag & swe.ECL_ANNULAR:      return "Ringförmig"
    if retflag & swe.ECL_ANNULAR_TOTAL:return "Hybrid"
    if retflag & swe.ECL_PARTIAL:      return "Partiell"
    return "Solar"


def _lunar_type(retflag):
    if retflag & swe.ECL_TOTAL:     return "Total"
    if retflag & swe.ECL_PARTIAL:   return "Partiell"
    if retflag & swe.ECL_PENUMBRAL: return "Halbschatten"
    return "Lunar"


def _jd_to_date(jd_ut):
    y, mo, d, h = swe.revjul(jd_ut)
    hh = int(h)
    mm = int((h - hh) * 60)
    return y, mo, d, hh, mm


def _solar_visible_at_obs(jd_ut):
    """True if the solar eclipse is visible (any phase) from the observer."""
    try:
        geopos = [OBS_LON, OBS_LAT, OBS_ALT]
        # pyswisseph signature: sol_eclipse_how(tjdut, geopos, flags)
        retflag, attr = swe.sol_eclipse_how(jd_ut, geopos, swe.FLG_SWIEPH)
        # attr[0] = fraction of solar diameter covered (magnitude); >0 = visible.
        # Note: checked at the instant of the GLOBAL maximum — a slight
        # approximation; exact local circumstances would need sol_eclipse_when_loc.
        return retflag > 0 and attr[0] > 0
    except Exception as e:
        print(f"  WARN sol_eclipse_how failed at jd={jd_ut:.4f}: {type(e).__name__}: {e}")
        return None


def _lunar_visible_at_obs(jd_ut):
    """True if the Moon is above the horizon at eclipse maximum from observer.

    A lunar eclipse is visible from anywhere the Moon is above the local horizon
    at the moment of maximum. We compute the Moon's tropical ecliptic position
    (geometry only — ayanamsha is irrelevant for altitude) and convert to
    horizontal coordinates for the observer.
    """
    try:
        xx, _ = swe.calc_ut(jd_ut, swe.MOON, swe.FLG_SWIEPH)
        geopos = [OBS_LON, OBS_LAT, OBS_ALT]
        # azalt(tjdut, flag, geopos, atpress, attemp, xin=[lon,lat,dist])
        az = swe.azalt(jd_ut, swe.ECL2HOR, geopos, 1013.25, 15.0, [xx[0], xx[1], xx[2]])
        # az = (azimuth, true_altitude, apparent_altitude)
        return az[1] > 0.0
    except Exception:
        return None


def compute():
    solar, lunar = [], []
    jd_start = swe.julday(START_YEAR, 1, 1, 0.0)
    jd_end   = swe.julday(END_YEAR, 12, 31, 24.0)

    # ── Solar eclipses ────────────────────────────────────────────────────────
    print(f"Computing solar eclipses {START_YEAR}\u2013{END_YEAR} ...")
    jd = jd_start
    guard = 0
    while jd < jd_end and guard < 5000:
        guard += 1
        try:
            retflag, tret = swe.sol_eclipse_when_glob(jd, swe.FLG_SWIEPH, 0, False)
        except Exception as e:
            print("  solar search ended:", e); break
        jd_max = tret[0]
        if jd_max >= jd_end:
            break
        y, mo, d, hh, mm = _jd_to_date(jd_max)
        lon = _sidereal_lon(jd_max, swe.SUN)
        si, sn, deg, dstr = _sign_deg(lon)
        nak, pada = _nakshatra(lon)
        solar.append({
            "kind": "solar",
            "date": f"{y:04d}-{mo:02d}-{d:02d}",
            "year": y, "month": mo, "day": d,
            "time_ut": f"{hh:02d}:{mm:02d}",
            "type": _solar_type(retflag),
            "sign": sn, "sign_idx": si,
            "deg": round(deg, 4), "deg_str": dstr,
            "lon": round(lon, 4),
            "nakshatra": nak, "pada": pada,
            "visible_wadenswil": _solar_visible_at_obs(jd_max),
        })
        jd = jd_max + 10.0   # step past this eclipse

    # ── Lunar eclipses ────────────────────────────────────────────────────────
    print(f"Computing lunar eclipses {START_YEAR}\u2013{END_YEAR} ...")
    jd = jd_start
    guard = 0
    while jd < jd_end and guard < 5000:
        guard += 1
        try:
            retflag, tret = swe.lun_eclipse_when(jd, swe.FLG_SWIEPH, 0, False)
        except Exception as e:
            print("  lunar search ended:", e); break
        jd_max = tret[0]
        if jd_max >= jd_end:
            break
        y, mo, d, hh, mm = _jd_to_date(jd_max)
        lon = _sidereal_lon(jd_max, swe.MOON)
        si, sn, deg, dstr = _sign_deg(lon)
        nak, pada = _nakshatra(lon)
        lunar.append({
            "kind": "lunar",
            "date": f"{y:04d}-{mo:02d}-{d:02d}",
            "year": y, "month": mo, "day": d,
            "time_ut": f"{hh:02d}:{mm:02d}",
            "type": _lunar_type(retflag),
            "sign": sn, "sign_idx": si,
            "deg": round(deg, 4), "deg_str": dstr,
            "lon": round(lon, 4),
            "nakshatra": nak, "pada": pada,
            "visible_wadenswil": _lunar_visible_at_obs(jd_max),
        })
        jd = jd_max + 10.0

    all_ecl = solar + lunar
    all_ecl.sort(key=lambda e: (e["year"], e["month"], e["day"]))

    out = {
        "meta": {
            "start_year": START_YEAR,
            "end_year": END_YEAR,
            "ayanamsha": "Lahiri (SIDM_LAHIRI)",
            "observer": "Wädenswil, CH (47.23N, 8.67E)",
            "count_solar": len(solar),
            "count_lunar": len(lunar),
            "count_total": len(all_ecl),
        },
        "eclipses": all_ecl,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nWrote {OUT_PATH}")
    print(f"  Solar: {len(solar)}   Lunar: {len(lunar)}   Total: {len(all_ecl)}")
    unknown = sum(1 for e in all_ecl if e["visible_wadenswil"] is None)
    if unknown:
        print(f"  WARNUNG: visible_wadenswil ist bei {unknown} Einträgen None — "
              f"Sichtbarkeitsberechnung prüfen!")
    else:
        vis = sum(1 for e in all_ecl if e["visible_wadenswil"])
        print(f"  Sichtbar von Wädenswil: {vis} / {len(all_ecl)}")


if __name__ == "__main__":
    compute()

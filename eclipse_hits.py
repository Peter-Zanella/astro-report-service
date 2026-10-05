"""
eclipse_hits.py — Which natal points the eclipses of a year hit.

For every solar and lunar eclipse in eclipse_database.json the sidereal (Lahiri)
longitude of the eclipsed light (Sun for solar, Moon for lunar eclipses) is
compared with the natal longitudes of a chart. A hit is a conjunction,
opposition or square within the orb (default 3°). The engine stays untouched;
this module only reads the chart's "lons" and the eclipse database.
"""
from typing import Dict, List

import eclipse_db

DEFAULT_ORB = 3.0

# name, angle, symbol, German label
ASPECTS = [
    ("conjunction", 0, "☌", "Konjunktion"),
    ("opposition", 180, "☍", "Opposition"),
    ("square", 90, "□", "Quadrat"),
]

# natal points in display order; the Ascendant is shown as Lagna
POINTS = ["Ascendant", "Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn",
          "Rahu", "Ketu"]


def _sep(a: float, b: float) -> float:
    """Angular distance 0..180°."""
    return abs((a - b + 180) % 360 - 180)


def hits(eclipse_lon: float, natal_lons: Dict[str, float], orb: float = DEFAULT_ORB) -> List[Dict]:
    """Natal points aspected by one eclipse point, tightest first."""
    out = []
    for p in POINTS + sorted(set(natal_lons) - set(POINTS)):
        lon = natal_lons.get(p)
        if lon is None:
            continue
        d = _sep(eclipse_lon, lon)
        for name, angle, sym, de in ASPECTS:
            o = abs(d - angle)
            if o <= orb:
                out.append({"point": "Lagna" if p == "Ascendant" else p, "aspect": name,
                            "symbol": sym, "label_de": de, "orb": round(o, 2)})
    out.sort(key=lambda h: h["orb"])
    return out


def for_year(natal_lons: Dict[str, float], year: int, orb: float = DEFAULT_ORB) -> List[Dict]:
    """All eclipses of a year, each with the natal points it hits."""
    rows = []
    for e in eclipse_db.by_year(year, year).get(year, []):
        rows.append({**e, "hits": hits(e["lon"], natal_lons, orb)})
    return rows

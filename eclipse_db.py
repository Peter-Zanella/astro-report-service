"""
eclipse_db.py — Loader for the static eclipse database (eclipse_database.json).

Pure lookup, no calculation. All positions were computed by Swiss Ephemeris
in compute_eclipses.py and cached. This module only reads and groups them.
"""
import json
import os
from typing import Dict, List, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_DB_PATH = os.path.join(_HERE, "eclipse_database.json")

_CACHE: Optional[Dict] = None


def _load() -> Dict:
    global _CACHE
    if _CACHE is None:
        try:
            with open(_DB_PATH, encoding="utf-8") as f:
                _CACHE = json.load(f)
        except Exception:
            _CACHE = {"meta": {}, "eclipses": []}
    return _CACHE


def available() -> bool:
    """True if the database loaded with at least one eclipse."""
    return len(_load().get("eclipses", [])) > 0


def meta() -> Dict:
    return _load().get("meta", {})


def all_eclipses() -> List[Dict]:
    return _load().get("eclipses", [])


def year_range() -> tuple:
    m = meta()
    return m.get("start_year", 1940), m.get("end_year", 2100)


def by_year(start: Optional[int] = None, end: Optional[int] = None) -> Dict[int, List[Dict]]:
    """Return eclipses grouped by calendar year, optionally filtered to [start, end]."""
    grouped: Dict[int, List[Dict]] = {}
    for e in all_eclipses():
        y = e.get("year")
        if start is not None and y < start:
            continue
        if end is not None and y > end:
            continue
        grouped.setdefault(y, []).append(e)
    for y in grouped:
        grouped[y].sort(key=lambda e: (e["month"], e["day"]))
    return grouped

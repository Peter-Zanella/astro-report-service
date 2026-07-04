"""
pada_db.py — Loader for the static 108-pada interpretation database.

Single source of truth for pada text: astro_engine computes which pada a planet
occupies (nakshatra + pada number); this module maps that to the pre-written
16-field interpretation. Purely a lookup — no calculation, no AI.
"""
import json
import os
from typing import Dict, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_DB_PATH = os.path.join(_HERE, "pada_database.json")
_FIELDS_PATH = os.path.join(_HERE, "_pada_fields.json")

# Ordered list of the 16 fields and their display labels
FIELD_ORDER = [
    "grundcharakter", "motivation", "psychologie", "kommunikation",
    "talente", "beruf", "finanzen", "beziehungen", "familie",
    "spiritualitaet", "schattenseiten", "entwicklungsweg",
    "navamsha_einfluss", "planetentyp_wirkung", "schluesselwoerter",
    "berichtsformulierung",
]
FIELD_LABELS = {
    "grundcharakter": "Grundcharakter",
    "motivation": "Motivation",
    "psychologie": "Psychologie",
    "kommunikation": "Kommunikation",
    "talente": "Talente",
    "beruf": "Beruf",
    "finanzen": "Finanzen",
    "beziehungen": "Beziehungen",
    "familie": "Familie",
    "spiritualitaet": "Spiritualität",
    "schattenseiten": "Schattenseiten",
    "entwicklungsweg": "Entwicklungsweg",
    "navamsha_einfluss": "Navāṃśa-Einfluss",
    "planetentyp_wirkung": "Wirkung des Planetentyps",
    "schluesselwoerter": "Schlüsselwörter",
    "berichtsformulierung": "Berichtsformulierung",
}

_DB_CACHE: Optional[Dict] = None


def _load() -> Dict:
    global _DB_CACHE
    if _DB_CACHE is None:
        try:
            with open(_DB_PATH, encoding="utf-8") as f:
                _DB_CACHE = json.load(f)
        except Exception:
            _DB_CACHE = {}
    return _DB_CACHE


def get_pada(nakshatra: str, pada: int) -> Optional[Dict]:
    """Return the 16-field entry for a nakshatra+pada, or None if not present."""
    if not nakshatra or not pada:
        return None
    return _load().get(f"{nakshatra}_{pada}")


def has_content(entry: Optional[Dict]) -> bool:
    """True if at least one of the 16 interpretation fields is filled."""
    if not entry:
        return False
    return any(str(entry.get(f, "")).strip() for f in FIELD_ORDER)


def filled_count() -> int:
    """How many of the 108 padas have at least one field filled (for progress)."""
    return sum(1 for e in _load().values() if has_content(e))

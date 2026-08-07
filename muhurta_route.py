# -*- coding: utf-8 -*-
"""
muhurta_route.py — API-Endpoint für den Muhurta-Tab (FastAPI)
==============================================================
Registrierung in report_service.py:

    import muhurta_route
    muhurta_route.register_muhurta_routes(app, authorize=_muhurta_allowed)

`authorize(sid)` entscheidet, ob der Aufruf rechnen darf (z.B. Session im
Chart-Cache). Ohne authorize ist der Endpoint offen — nicht empfohlen.

Aufruf vom Frontend:
  /api/muhurta?year=2026&month=7&lat=47.23&lon=8.67&tz=Europe/Zurich&sid=cs_...
  optional: &janma=8  (Index 0–26) → personalisierter Modus (Tārā-Zeile)
"""
import threading
from collections import OrderedDict

from fastapi.responses import JSONResponse

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:                                    # pragma: no cover
    ZoneInfo = None                                    # type: ignore
    ZoneInfoNotFoundError = Exception                  # type: ignore

from muhurta import month_muhurta, activity_windows, ACTIVITIES

# Kleiner Ergebnis-Cache: Monats-Matrix ist deterministisch je Parameter-Satz.
# Sync-Handler laufen im Starlette-Threadpool → echte Nebenläufigkeit auf dem
# geteilten OrderedDict; ein Lock verhindert die Race zwischen Treffer-Lookup
# und Verdrängung (sonst sporadische KeyError/RuntimeError → 500).
_CACHE: "OrderedDict[tuple, dict]" = OrderedDict()
_CACHE_MAX = 60
_CACHE_LOCK = threading.Lock()


def _valid_tz(tz: str) -> bool:
    """True, wenn tz eine auflösbare IANA-Zone ist (verhindert 500 auf Falscheingabe)."""
    if ZoneInfo is None:
        return True                                    # kein zoneinfo → nicht prüfbar
    try:
        ZoneInfo(tz)
        return True
    except (ZoneInfoNotFoundError, ValueError, Exception):
        return False


def _cache_get(key):
    with _CACHE_LOCK:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return _CACHE[key]
    return None


def _cache_put(key, data):
    with _CACHE_LOCK:
        _CACHE[key] = data
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)


def register_muhurta_routes(app, authorize=None):

    @app.get("/api/muhurta")
    def api_muhurta(year: int = 0, month: int = 0,
                    lat: float = 1000.0, lon: float = 1000.0,
                    tz: str = "Europe/Zurich", janma: str = "",
                    sid: str = ""):
        if authorize is not None and not authorize(sid):
            return JSONResponse({"error": "Kein Zugriff — Bericht-Session "
                                          "erforderlich."}, status_code=403)
        try:
            if not (1 <= month <= 12):
                raise ValueError("month")
            if not (1900 <= year <= 2100):
                raise ValueError("year")
            if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
                raise ValueError("latlon")
            janma_idx = int(janma) if janma.strip() != "" else None
            if janma_idx is not None and not (0 <= janma_idx <= 26):
                raise ValueError("janma")
            if not _valid_tz(tz):
                raise ValueError("tz")
        except (TypeError, ValueError):
            return JSONResponse({"error": "Parameter: year, month, lat, lon, "
                                          "tz, optional janma (0-26)"},
                                status_code=400)

        key = (year, month, round(lat, 3), round(lon, 3), tz, janma_idx)
        cached = _cache_get(key)
        if cached is not None:
            return JSONResponse(cached)
        try:
            data = month_muhurta(year, month, lat, lon, tz,
                                 janma_nakshatra_index=janma_idx)
        except Exception as e:
            return JSONResponse({"error": f"Berechnung fehlgeschlagen: "
                                          f"{type(e).__name__}"},
                                status_code=500)
        _cache_put(key, data)
        return JSONResponse(data)

    @app.get("/api/muhurta/activity")
    def api_muhurta_activity(year: int = 0, month: int = 0, months: int = 6,
                             lat: float = 1000.0, lon: float = 1000.0,
                             tz: str = "Europe/Zurich", activity: str = "",
                             sid: str = ""):
        if authorize is not None and not authorize(sid):
            return JSONResponse({"error": "Kein Zugriff — Bericht-Session "
                                          "erforderlich."}, status_code=403)
        try:
            if activity not in ACTIVITIES:
                raise ValueError("activity")
            if not (1 <= month <= 12 and 1900 <= year <= 2100):
                raise ValueError("start")
            months = max(1, min(int(months), 12))
            if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
                raise ValueError("latlon")
            if not _valid_tz(tz):
                raise ValueError("tz")
        except (TypeError, ValueError):
            return JSONResponse({"error": "Parameter: year, month, months "
                                          "(1-12), lat, lon, tz, activity ("
                                          + ", ".join(ACTIVITIES) + ")"},
                                status_code=400)
        key = ("act", year, month, months, round(lat, 3), round(lon, 3),
               tz, activity)
        cached = _cache_get(key)
        if cached is not None:
            return JSONResponse(cached)
        try:
            data = activity_windows(year, month, months, lat, lon, tz, activity)
        except Exception as e:
            return JSONResponse({"error": f"Berechnung fehlgeschlagen: "
                                          f"{type(e).__name__}"},
                                status_code=500)
        _cache_put(key, data)
        return JSONResponse(data)

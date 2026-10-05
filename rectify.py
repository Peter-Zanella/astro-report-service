# Birth time rectification and observation over time: how the parts of a chart
# change across a window around the given birth time. Within hours only the
# Lagna (and its vargas) and the Moon move fast enough to matter. Over days to
# a year the Lagna just cycles daily, so the long windows follow the Moon and
# the planets instead: sign and nakshatra changes and retrograde stations.
# The sweep reads raw positions from the engine instead of whole charts.

from datetime import datetime, timedelta, timezone

import astro_engine as E

GRAHAS = ("Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Rahu")
SLOW = ("Sun", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Rahu")
SHORT_MAX = 720                       # up to ± 12 h: Lagna mode
DAY, WEEK, MONTH, YEAR = 1440, 10080, 43200, 525600
NICE_STEPS = (1, 2, 3, 5, 10, 15, 20, 30, 60, 120, 180, 360, 720,
              DAY, 2 * DAY, WEEK, 2 * WEEK, MONTH)


def _sign(lon):
    return E.SIGNS[int(lon / 30) % 12]


def _nak(lon, pada=True):
    n, _, p = E.nakshatra_of(lon)
    return f"{n} {p}" if pada else n


def _pos(lon: float) -> str:
    d = lon % 30
    return f"{int(d)}° {int((d % 1) * 60):02d}'"


def _positions(local: datetime, lat: float, lon: float, full: bool) -> dict:
    """Sidereal longitudes for an aware local datetime: Ascendant and Moon, plus
    the other grahas when full. "_retro" holds the grahas moving backwards."""
    ut = local.astimezone(timezone.utc)
    jd = E.get_jd(ut.year, ut.month, ut.day, ut.hour + ut.minute / 60 + ut.second / 3600)
    names = GRAHAS if full else ("Moon",)
    if E._SWE:
        E.swe.set_sid_mode(E.swe.SIDM_LAHIRI, 0, 0)
        out, retro = {"Ascendant": E._swe_asc(jd, lat, lon)}, set()
        for p in names:
            r = E.swe.calc_ut(jd, E._SWE_ID[p], E.swe.FLG_SIDEREAL | E.swe.FLG_SPEED)[0]
            out[p] = E.norm(r[0])
            if r[3] < 0:
                retro.add(p)
    else:
        # built-in math only: the Horizons tier would mean one web request per sample
        def at(j):
            ayan = E._ayanamsha(j)
            raw = {"Sun": E._sun, "Moon": E._moon, "Rahu": E._rahu}
            return {p: E.norm((raw[p](j) if p in raw else E._planet(p, j)) - ayan) for p in names}
        out, later = at(jd), at(jd + 1 / 24) if full else {}
        retro = {p for p in later if ((later[p] - out[p] + 540) % 360) - 180 < 0}
        out["Ascendant"] = E.norm(E._ascendant(jd, lat, lon) - E._ayanamsha(jd))
    out["_retro"] = retro
    return out


def _graha(p):
    """Sign of a slow graha, with R while retrograde (Rahu always is)."""
    return lambda x: _sign(x[p]) + (" R" if p in x["_retro"] and p != "Rahu" else "")


# key, label, value: everything that can flip and is tracked to the second
SHORT_FACTORS = [
    ("lagna", "Lagna", lambda x: _sign(x["Ascendant"])),
    ("d9", "Navamsa Lagna (D9)", lambda x: E.SIGNS[E.navamsa_sign(x["Ascendant"])]),
    ("d10", "Dasamsha Lagna (D10)", lambda x: E.SIGNS[E.dasamsha_sign(x["Ascendant"])]),
    ("d3", "Drekkana Lagna (D3)", lambda x: E.SIGNS[E.drekkana_sign(x["Ascendant"])]),
    ("d4", "Chaturthamsha Lagna (D4)", lambda x: E.SIGNS[E.chaturthamsha_sign(x["Ascendant"])]),
    ("moon_sign", "Moon sign", lambda x: _sign(x["Moon"])),
    ("moon_nak", "Moon nakshatra", lambda x: _nak(x["Moon"])),
]


def long_factors(span: int):
    """What to follow over days to a year. The Moon changes nakshatra daily and
    sign every 2.5 days, so it is followed only in the shorter of these windows;
    the table rows still show it at every step."""
    f = []
    if span <= MONTH:
        f.append(("moon_sign", "Moon sign", lambda x: _sign(x["Moon"])))
        f.append(("moon_nak", "Moon nakshatra",
                  (lambda x: _nak(x["Moon"])) if span <= WEEK else (lambda x: _nak(x["Moon"], False))))
    for p in SLOW:
        f.append((p, p + (" / Ketu" if p == "Rahu" else ""), _graha(p)))
        if span <= MONTH:
            f.append((p + "_nak", p + " nakshatra", (lambda q: lambda x: _nak(x[q], False))(p)))
    return f


def columns(full: bool, birth: datetime):
    """Table columns: key, label, value (cells that differ get highlighted), detail."""
    asc = lambda x: _pos(x["Ascendant"])
    if not full:
        return [("lagna", "Lagna", SHORT_FACTORS[0][2], asc)] + \
               [(k, k.upper(), f, None) for k, _, f in SHORT_FACTORS[1:5]] + \
               [("moon_nak", "Moon", SHORT_FACTORS[6][2], None)]
    return [("lagna", f"Lagna at {birth:%H:%M}", SHORT_FACTORS[0][2], asc),
            ("moon", "Moon", lambda x: _nak(x["Moon"]), lambda x: _sign(x["Moon"]))] + \
           [(p, "Rahu" if p == "Rahu" else p, _graha(p), (lambda q: lambda x: _pos(x[q]))(p)) for p in SLOW]


def _dasha(moon: float, local: datetime) -> dict:
    d = E.build_dashas(moon, local.replace(tzinfo=None))
    first = d["mahadashas"][0]
    mo = round(first["years"] * 12)
    out = {"balance": f"{first['planet']} {mo // 12}y {mo % 12}m",
           "now": " › ".join(x for x in (d["current"]["maha"], d["current"]["antar"]) if x)}
    for m in d["mahadashas"]:
        if m["active"]:
            a = next((a for a in m["antardashas"] if a["active"]), None)
            if a:
                out["antar_start"] = a["start"].date().isoformat()
    return out


def auto_step(span: int) -> int:
    """About 15 rows either side of the birth time."""
    return next((s for s in NICE_STEPS if s * 15 >= span), NICE_STEPS[-1])


def sweep(year, month, day, hour, minute, lat, lon, tz, span: int, step: int = 0) -> dict:
    birth = datetime(year, month, day, hour, minute, tzinfo=timezone(timedelta(hours=tz)))
    step = step or auto_step(span)
    if span / step > 200:                       # at most about 400 rows
        step = next((s for s in NICE_STEPS if span / s <= 200), NICE_STEPS[-1])
    full = span > SHORT_MAX
    factors_def = long_factors(span) if full else SHORT_FACTORS
    labels = {k: lbl for k, lbl, _ in factors_def}
    pos = lambda s: _positions(birth + timedelta(seconds=s), lat, lon, full)
    vals = lambda x: {k: f(x) for k, _, f in factors_def}

    # Samples every minute (Lagna mode: the D10 Lagna holds for about 3° of the
    # Ascendant), every hour up to a month (the Moon needs about 6 h per pada) or
    # every 6 h beyond (only the planets are followed, none moves 2° in that time);
    # each flip is then bisected to the second, or to the minute in the long windows
    every, res = ((21600 if span > MONTH else 3600), 60) if full else (60, 1)
    samples = [(s, vals(pos(s))) for s in range(-span * 60, span * 60 + 1, every)]
    changes = []
    for (s0, v0), (s1, v1) in zip(samples, samples[1:]):
        for k in labels:
            if v0[k] == v1[k]:
                continue
            lo, hi = s0, s1
            while hi - lo > res:
                mid = (lo + hi) // 2 // res * res
                if mid <= lo:
                    break
                if vals(pos(mid))[k] == v0[k]:
                    lo = mid
                else:
                    hi = mid
            t = birth + timedelta(seconds=hi)
            changes.append({"key": k, "label": labels[k], "at": t.strftime("%H:%M:%S" if res == 1 else "%H:%M"),
                            "date": t.date().isoformat(), "offset": round(hi / 60, 2), "sec": hi,
                            "from": v0[k], "to": vals(pos(hi))[k]})
    changes.sort(key=lambda c: c["sec"])

    # how far each factor holds its birth-time value on either side
    x_birth = pos(0)
    v_birth = vals(x_birth)
    fmt = "%H:%M:%S" if res == 1 else "%H:%M"
    factors = []
    for k, lbl, _ in factors_def:
        before = [c["sec"] for c in changes if c["key"] == k and c["sec"] <= 0]
        after = [c["sec"] for c in changes if c["key"] == k and c["sec"] > 0]
        lo, hi = (max(before) if before else None), (min(after) if after else None)
        t_lo = birth + timedelta(seconds=lo) if lo is not None else None
        t_hi = birth + timedelta(seconds=hi - res) if hi is not None else None
        factors.append({"key": k, "label": lbl, "value": v_birth[k],
                        "from": t_lo.strftime(fmt) if t_lo else None,
                        "from_date": t_lo.date().isoformat() if t_lo else None,
                        "to": t_hi.strftime(fmt) if t_hi else None,
                        "to_date": t_hi.date().isoformat() if t_hi else None,
                        "minus": round(-lo / 60, 2) if lo is not None else None,
                        "plus": round(hi / 60, 2) if hi is not None else None})
    for f in factors:
        k = f["key"]
        if k == "lagna":
            f["value"] += " " + _pos(x_birth["Ascendant"])
        elif k == "moon_nak":
            f["value"] += f" ({_pos(x_birth['Moon'])} {_sign(x_birth['Moon'])})"
        elif k in SLOW:
            f["value"] = f"{f['value']} {_pos(x_birth[k])}"

    cols = columns(full, birth)
    rows, n = [], span // step              # rows centred on the birth time itself
    for s in range(-n * step * 60, n * step * 60 + 1, step * 60):
        t = birth + timedelta(seconds=s)
        x = _positions(t, lat, lon, full)
        row = {"offset": s // 60, "time": t.strftime("%H:%M"), "date": t.date().isoformat(),
               **_dasha(x["Moon"], t)}
        for k, _, f, sub in cols:
            row[k] = f(x)
            if sub:
                row[k + "_sub"] = sub(x)
        rows.append(row)

    return {"birth": birth.strftime("%H:%M"), "date": birth.date().isoformat(), "span": span,
            "step": step, "mode": "days" if full else "time",
            "columns": [[k, lbl] for k, lbl, _, _ in cols],
            "factors": factors, "changes": changes, "rows": rows}

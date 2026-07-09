#!/usr/bin/env python3
"""
PDF report for a computed Jyotiṣa chart, using reportlab (pure-Python).

build_pdf(chart, variant=...) -> bytes    raises RuntimeError if reportlab missing.

variant="full"      complete technical report (all tables, fixed order)
variant="customer"  reader-friendly report that follows the AstroVeda
                    Interpretationsmethodik: the AI interpretation is the spine,
                    and after each interpretation chapter the matching data
                    (charts, tables) is inserted — D1/Graha after the Lagna
                    chapter, Yogas & Shad Bala after the strengths chapter,
                    D9/D10/D3+D4 charts after their chapters, Daśā tables after
                    the timing chapter, Jaimini & Chara Daśā after Jaimini.
"""
import os
from io import BytesIO

from astro_engine import (
    SIGNS, SIGN_ABR, SIGN_LORDS, PLANET_ORDER, PLANET_ABR, _AKV_PLANETS, _SIGN_CELL,
)

_INK = "#2b2118"; _ACCENT = "#7b2d26"; _LINE = "#d9c9a8"; _PAPER = "#fbf7ef"
_GOOD = "#2e7d4f"; _WARN = "#b07d18"; _BAD = "#9a342c"; _LAGNA = "#fdf3df"
_MAL_YOGAS = {"Vishkambha", "Atiganda", "Shoola", "Ganda", "Vyaghata", "Vajra",
              "Vyatipata", "Parigha", "Vaidhriti"}

# Bhava chart cell map: signs fixed with Pisces (11) top-right, zodiac clockwise
_BHAVA_CELL = {0: (1, 3), 1: (2, 3), 2: (3, 3), 3: (3, 2), 4: (3, 1), 5: (3, 0),
               6: (2, 0), 7: (1, 0), 8: (0, 0), 9: (0, 1), 10: (0, 2), 11: (0, 3)}


def _have_reportlab() -> bool:
    try:
        import reportlab  # noqa: F401
        return True
    except ImportError:
        return False


# ── Unicode fonts (IAST diacritics: ṣ ā ṃ ś …) ───────────────────────────────
# Tries a repo-local ./fonts folder first, then common system locations.
# If none found, all text is transliterated to ASCII so no boxes ever appear.
_FONT_DIRS = [
    os.path.dirname(os.path.abspath(__file__)),                      # repo root
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts"),
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/dejavu",
    "/usr/local/share/fonts",
]
_UNICODE_FONTS = None   # dict with serif/sans font names, False if unavailable


def _register_unicode_fonts():
    """Register DejaVu TTFs once. Returns dict of font names or None."""
    global _UNICODE_FONTS
    if _UNICODE_FONTS is not None:
        return _UNICODE_FONTS or None
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.lib.fonts import addMapping
        need = {
            "AV-Serif":   "DejaVuSerif.ttf",
            "AV-SerifB":  "DejaVuSerif-Bold.ttf",
            "AV-SerifI":  "DejaVuSerif-Italic.ttf",
            "AV-SerifBI": "DejaVuSerif-BoldItalic.ttf",
            "AV-Sans":    "DejaVuSans.ttf",
            "AV-SansB":   "DejaVuSans-Bold.ttf",
            "AV-SansI":   "DejaVuSans-Oblique.ttf",
            "AV-SansBI":  "DejaVuSans-BoldOblique.ttf",
        }
        found = {}
        for name, fn in need.items():
            for d in _FONT_DIRS:
                p = os.path.join(d, fn)
                if os.path.isfile(p):
                    found[name] = p
                    break
        if not all(k in found for k in ("AV-Serif", "AV-SerifB", "AV-Sans", "AV-SansB")):
            _UNICODE_FONTS = False
            return None
        for name, path in found.items():
            pdfmetrics.registerFont(TTFont(name, path))
        # map <b>/<i> markup inside Paragraphs to the right variants
        addMapping("AV-Serif", 0, 0, "AV-Serif")
        addMapping("AV-Serif", 1, 0, "AV-SerifB")
        addMapping("AV-Serif", 0, 1, "AV-SerifI" if "AV-SerifI" in found else "AV-Serif")
        addMapping("AV-Serif", 1, 1, "AV-SerifBI" if "AV-SerifBI" in found else "AV-SerifB")
        addMapping("AV-Sans", 0, 0, "AV-Sans")
        addMapping("AV-Sans", 1, 0, "AV-SansB")
        addMapping("AV-Sans", 0, 1, "AV-SansI" if "AV-SansI" in found else "AV-Sans")
        addMapping("AV-Sans", 1, 1, "AV-SansBI" if "AV-SansBI" in found else "AV-SansB")
        _UNICODE_FONTS = {"serif": "AV-Serif", "serif_b": "AV-SerifB",
                          "serif_i": "AV-SerifI" if "AV-SerifI" in found else "AV-Serif",
                          "sans": "AV-Sans", "sans_b": "AV-SansB"}
        return _UNICODE_FONTS
    except Exception:
        _UNICODE_FONTS = False
        return None


# IAST → ASCII fallback (only used when no unicode font could be registered)
_IAST_MAP = {
    "ā": "a", "Ā": "A", "ī": "i", "Ī": "I", "ū": "u", "Ū": "U",
    "ṛ": "ri", "Ṛ": "Ri", "ṝ": "ri", "ḷ": "li", "ḹ": "li",
    "ē": "e", "Ē": "E", "ō": "o", "Ō": "O",
    "ṃ": "m", "Ṃ": "M", "ṁ": "m", "ḥ": "h", "Ḥ": "H",
    "ṅ": "n", "Ṅ": "N", "ñ": "n", "Ñ": "N", "ṇ": "n", "Ṇ": "N",
    "ṭ": "t", "Ṭ": "T", "ḍ": "d", "Ḍ": "D",
    "ś": "sh", "Ś": "Sh", "ṣ": "sh", "Ṣ": "Sh",
    "′": "'", "″": '"', "‐": "-", "✦": "*", "◆": "*", "◇": "*", "★": "*",
}


def _iast_ascii(s: str) -> str:
    for k, v in _IAST_MAP.items():
        if k in s:
            s = s.replace(k, v)
    return s


# Interpretation-chapter → data-block mapping (customer variant).
# Keys are matched case-insensitively against "## " headings of the AI text.
_INJECT_RULES = [
    ("d1",      ("aszendent", "ascendant", "grundwesen", "core nature",
                 "lagna & lagna", "lagna-herr")),
    ("yoga",    ("yoga", "shad bala", "stärken", "staerken", "strength",
                 "kernthemen", "key themes")),
    ("d9",      ("navāṃśa", "navamsa", "navamsha", "(d9)", "d9 ", "seelenqualit",
                 "soul quality")),
    ("d10",     ("daśāṃśa", "dasamsa", "dasamsha", "(d10)", "d10 ",
                 "beruf & karriere", "career & vocation")),
    ("d3d4",    ("drekkāna", "drekkana", "(d3)", "chaturtham")),
    ("dasha",   ("timing", "viṃśottarī", "vimśottarī", "vimshottari",
                 "auslösung", "activation")),
    ("transit", ("transite", "transits", "gochara")),
    ("jaimini", ("jaimini", "ātmakāraka", "atmakaraka", "arudh")),
    ("varsha",  ("varshaphala", "jahres-aszendent", "muntha", "varṣeśa",
                 "jahr im überblick", "year at a glance", "annual ascendant",
                 "lord of the year")),
]


def _match_block(heading: str):
    h = heading.lower()
    for key, pats in _INJECT_RULES:
        if any(p in h for p in pats):
            return key
    return None


def build_pdf(chart: dict, compat: dict = None, interpretation: str = None,
              interpretation_title: str = "Persönliche Deutung",
              variant: str = "full") -> bytes:
    if not _have_reportlab():
        raise RuntimeError("reportlab not installed")

    import re as _re
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether,
        PageBreak,
    )
    from reportlab.graphics.shapes import Drawing, Rect, String

    tech = variant != "customer"
    uni = _register_unicode_fonts()
    if uni:
        F_SER, F_SER_B, F_SER_I = uni["serif"], uni["serif_b"], uni["serif_i"]
        F_SANS, F_SANS_B = uni["sans"], uni["sans_b"]
        T = lambda s: s                       # unicode font: keep IAST as-is
    else:
        F_SER, F_SER_B, F_SER_I = "Times-Roman", "Times-Bold", "Times-Italic"
        F_SANS, F_SANS_B = "Helvetica", "Helvetica-Bold"
        T = _iast_ascii                       # no unicode font: transliterate

    ink = colors.HexColor(_INK); accent = colors.HexColor(_ACCENT)
    line = colors.HexColor(_LINE); paper = colors.HexColor(_PAPER)
    lagna_bg = colors.HexColor(_LAGNA)
    cmap = {"good": colors.HexColor(_GOOD), "warn": colors.HexColor(_WARN),
            "bad": colors.HexColor(_BAD)}

    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], textColor=accent, fontName=F_SER_B,
                        fontSize=20, spaceAfter=2, alignment=1)
    sub = ParagraphStyle("sub", parent=ss["Normal"], textColor=ink, fontSize=9,
                         fontName=F_SANS, alignment=1, spaceAfter=10)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=accent,
                        fontName=F_SER_B, fontSize=13, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("body", parent=ss["Normal"], textColor=ink, fontSize=9,
                          fontName=F_SANS, leading=13)
    small = ParagraphStyle("small", parent=ss["Normal"], textColor=ink, fontSize=7.5,
                           fontName=F_SANS, leading=9)
    cap = ParagraphStyle("cap", parent=ss["Normal"], textColor=colors.HexColor("#7a6a4c"),
                         fontName=F_SANS, fontSize=7.5, leading=10)

    def TS(*cmds):
        return TableStyle(list(cmds))

    _base = [("FONTSIZE", (0, 0), (-1, -1), 8), ("TEXTCOLOR", (0, 0), (-1, -1), ink),
             ("GRID", (0, 0), (-1, -1), 0.3, line),
             ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]

    def _head_style(extra=()):
        return TableStyle([("BACKGROUND", (0, 0), (-1, 0), paper),
                           ("FONTNAME", (0, 0), (-1, 0), F_SER_B)] + _base + list(extra))

    m = chart["meta"]

    # ══════════════════════════════════════════════════════════════════════
    # Reusable data blocks (each returns a list of flowables)
    # ══════════════════════════════════════════════════════════════════════

    # ── South-Indian chart table ─────────────────────────────────────────
    _NAK_AB = {}

    def _nak_abbr(name):
        """Compact nakshatra label: 'Purva Phalguni' → 'P.Pha', 'Ashlesha' → 'Ashl'
        (4 chars so Ashwini/Ashlesha stay distinct)."""
        if name in _NAK_AB:
            return _NAK_AB[name]
        parts = str(name).split()
        ab = (parts[0][0] + "." + parts[1][:3]) if len(parts) > 1 else parts[0][:4]
        _NAK_AB[name] = ab
        return ab

    def _detail_of(rec):
        """'7°49′ Mag 3' from a planet record with pos/nakshatra/pada."""
        pos = str(rec.get("pos", "")).replace(" ", "")
        nk = _nak_abbr(rec.get("nakshatra", "")) if rec.get("nakshatra") else ""
        pd = rec.get("pada", "")
        return f"{pos} {nk}{pd}".strip()

    def si_table(title, placements, lagna_si, cellmap=_SIGN_CELL,
                 details=None, lagna_detail=None):
        """details: {planet: 'deg nak pada'} → planets get one line each incl.
        degree + nakshatra (used for D1 and Varshaphala). Without details the
        cell shows the compact 'Su Ma' row as before."""
        natal = {i: [] for i in range(12)}
        for p, si in placements.items():
            if p != "Ascendant":
                natal[si].append((PLANET_ABR.get(p, p[:2]), p))
        grid_sign = {pos: si for si, pos in cellmap.items()}
        data = [[None] * 4 for _ in range(4)]
        spans = []
        det_style = ParagraphStyle("si_det", parent=small, fontSize=6.0, leading=7.2)
        for (r, c), si in grid_sign.items():
            house = (si - lagna_si) % 12 + 1
            tag = ("◆" if uni else "*") if si == lagna_si else ""
            txt = f"<b>{SIGN_ABR[si]}{tag} H{house}</b>"
            if si == lagna_si and lagna_detail:
                txt += f"<br/><font size=6.0 color='#7a6a4c'>{lagna_detail}</font>"
            if natal[si]:
                if details:
                    for ab, full in natal[si]:
                        d = details.get(full, "")
                        txt += f"<br/><b>{ab}</b> {d}" if d else f"<br/><b>{ab}</b>"
                else:
                    txt += "<br/>" + " ".join(ab for ab, _ in natal[si])
            data[r][c] = Paragraph(txt, det_style if details else small)
        data[1][1] = Paragraph(f"<b>{T(title)}</b>", ParagraphStyle(
            "ctr", parent=small, alignment=1, textColor=accent, fontName=F_SER_B, fontSize=9))
        data[1][2] = ""; data[2][1] = ""; data[2][2] = ""
        spans.append(("SPAN", (1, 1), (2, 2)))
        rh = 19.5 * mm if details else 18 * mm
        t = Table(data, colWidths=[22 * mm] * 4, rowHeights=[rh] * 4)
        styl = [("GRID", (0, 0), (-1, -1), 0.4, line),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (1, 1), (2, 2), paper)]
        if details:
            styl += [("LEFTPADDING", (0, 0), (-1, -1), 2),
                     ("RIGHTPADDING", (0, 0), (-1, -1), 2)]
        for (r, c), si in grid_sign.items():
            if si == lagna_si:
                styl.append(("BACKGROUND", (c, r), (c, r), lagna_bg))
        t.setStyle(TableStyle(styl + spans))
        return t

    def crow(a, b):
        return Table([[a, b]], colWidths=[90 * mm, 90 * mm], style=TableStyle(
            [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))

    d1_pl = {p: chart["planets"][p]["sign_idx"] for p in chart["planets"]}
    d1_det = {p: _detail_of(chart["planets"][p]) for p in chart["planets"]
              if p != "Ascendant"}
    _asc0 = chart["planets"].get("Ascendant")
    d1_lagna_det = _detail_of(_asc0) if _asc0 else None
    fmt = lambda dt: dt.strftime("%d %b %Y")

    # ── Graha (planets) table with Lagna + Arudha Lagna rows ─────────────
    asc = chart["planets"].get("Ascendant")
    _jai = chart.get("jaimini") or {}

    def b_planets():
        head = ["Planet", "Sign", "Pos", "H", "Nakshatra", "Pada", "Syl", "Lord", "Dignity"]
        data = [head]
        row_styles = []
        if asc:
            data.append(["Lagna", asc["sign"], asc["pos"], "1", asc["nakshatra"],
                         str(asc["pada"]), asc.get("syllable", "—"), asc["nak_lord"], "—"])
            row_styles.append(("BACKGROUND", (0, len(data) - 1), (-1, len(data) - 1), lagna_bg))
        if _jai.get("arudha_lagna"):
            data.append(["Arudha Lagna", _jai["arudha_lagna"], "—", "—", "—", "—", "—",
                         _jai.get("arudha_lagna_lord", "—"), "—"])
            row_styles.append(("BACKGROUND", (0, len(data) - 1), (-1, len(data) - 1),
                               colors.HexColor("#f2eef7")))
        for nm in PLANET_ORDER:
            p = chart["planets"][nm]
            data.append([nm, p["sign"], p["pos"], str(p.get("house", "—")),
                         p["nakshatra"], str(p["pada"]), p.get("syllable", "—"),
                         p["nak_lord"], p["dignity"]])
        pt = Table(data, repeatRows=1,
                   colWidths=[24*mm, 17*mm, 15*mm, 8*mm, 23*mm, 10*mm, 10*mm, 16*mm, 24*mm])
        pt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), paper),
            ("FONTNAME", (0, 0), (-1, 0), F_SER_B),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f1e4")]),
        ] + _base + row_styles))
        return [Paragraph("Graha (Planets)", h2), pt]

    # ── Bhava (houses) table ─────────────────────────────────────────────
    def b_houses():
        hdata = [["H", "Sign", "Lord", "Occupants"]]
        for h in range(1, 13):
            sn = chart["houses"][h]
            hdata.append([str(h), sn, SIGN_LORDS[sn], ", ".join(chart["occupants"][h]) or "—"])
        ht = Table(hdata, repeatRows=1, colWidths=[10*mm, 22*mm, 22*mm, 118*mm])
        ht.setStyle(_head_style())
        return [Paragraph("Bhava (Houses)", h2), ht]

    # ── divisional chart rows ────────────────────────────────────────────
    def b_d1d9():
        return [Paragraph("Divisional Charts (South Indian)", h2),
                KeepTogether(crow(si_table("D1 Rasi", d1_pl, chart["lagna_idx"],
                                           details=d1_det, lagna_detail=d1_lagna_det),
                                  si_table("D9 Navamsa", chart["d9"], chart["d9_lagna"])))]

    def b_d1_only():
        return [Spacer(1, 2 * mm),
                KeepTogether(crow(
                    si_table("D1 Rasi", d1_pl, chart["lagna_idx"],
                             details=d1_det, lagna_detail=d1_lagna_det),
                    Paragraph(T("D1 Rāśi (Geburtshoroskop, südindisch): Ganzzeichen-Häuser "
                                "vom Lagna aus gezählt, je Graha mit Gradzahl, Nakshatra "
                                "und Pada. ◆ markiert das Lagna-Zeichen."), cap)))]

    def b_d9_only():
        return [Spacer(1, 2 * mm),
                KeepTogether(crow(
                    si_table("D9 Navamsa", chart["d9"], chart["d9_lagna"]),
                    Paragraph(T("D9 Navāṃśa: das Seelen-Horoskop — Bestätigung oder "
                                "Relativierung der D1-Befunde; zentral für Ehe & Dharma."), cap)))]

    def b_d10_only():
        return [Spacer(1, 2 * mm),
                KeepTogether(crow(
                    si_table("D10 Dasamsha", chart["d10"], chart["d10_lagna"]),
                    Paragraph(T("D10 Daśāṃśa: Beruf, Berufung und Wirkung in der "
                                "Öffentlichkeit."), cap)))]

    def b_d3d4():
        out = [Spacer(1, 2 * mm),
               KeepTogether(crow(si_table("D3 Drekkana", chart["d3"], chart["d3_lagna"]),
                                 si_table("D4 Chaturthamsha", chart["d4"], chart["d4_lagna"])
                                 if chart.get("d4") else Spacer(1, 1)))]
        out.append(Paragraph(T("D3 Drekkāna: Vitalität, Mut & Geschwister · "
                               "D4 Chaturthamsha: Besitz, Immobilien, häusliches Glück."), cap))
        return out

    def b_d3d10d4_tech():
        out = [Spacer(1, 3 * mm),
               KeepTogether(crow(si_table("D3 Drekkana", chart["d3"], chart["d3_lagna"]),
                                 si_table("D10 Dasamsha", chart["d10"], chart["d10_lagna"])))]
        if chart.get("d4"):
            out.append(Spacer(1, 3 * mm))
            out.append(KeepTogether(crow(
                si_table("D4 Chaturthamsha", chart["d4"], chart["d4_lagna"]),
                Paragraph("D4 (Chaturthamsha): Besitz, Immobilien, häusliches Glück. "
                          "D3: Geschwister &amp; Mut · D9: Ehe &amp; Dharma · "
                          "D10: Beruf &amp; Wirkung in der Welt.", cap))))
        return out

    # ── bhava chalit + transit charts (technical) ────────────────────────
    def b_bhava_transit():
        tr = chart.get("transits", {})
        trans_pl = {p: tr[p]["sign_idx"] for p in tr if p != "Ascendant"} if tr else {}
        tr_det = {p: _detail_of(tr[p]) for p in tr if p != "Ascendant"} if tr else {}
        bhava_pl = chart.get("bhava", {}).get("place") or d1_pl
        t_lagna = chart.get("transit_lagna_idx", chart["lagna_idx"])
        return [
            Paragraph("Bhava Chalit &amp; Transit Charts (South Indian)", h2),
            KeepTogether(crow(si_table("Bhava Chalit", bhava_pl, chart["lagna_idx"]),
                              si_table(f"Transits (vs natal) {chart.get('transit_date','')}",
                                       trans_pl, chart["lagna_idx"], details=tr_det))),
            KeepTogether(crow(si_table(
                f"Now-chart · Lagna {chart.get('transit_lagna_pos','')} {SIGNS[t_lagna]}",
                trans_pl, t_lagna, details=tr_det), Spacer(1, 1))),
            Paragraph(
                "Bhava Chalit: houses centred on the Ascendant degree, so a planet near a "
                "sign edge can fall into the adjacent bhava. &nbsp; Transits (vs natal): "
                "current sky against the birth Lagna. &nbsp; Now-chart: same transiting "
                "planets, but houses counted from the Lagna at chart-creation time "
                f"({chart.get('transit_local', chart.get('transit_date',''))} local, at "
                "the birthplace).", cap)]

    # ── ashtakavarga (technical) ─────────────────────────────────────────
    def b_akv():
        akv = chart["ashtakavarga"]
        head = [""] + SIGN_ABR + ["Σ" if uni else "Sum"]
        adata = [head]
        color_cells = []
        for ri, p in enumerate(_AKV_PLANETS, start=1):
            row = akv[p]
            adata.append([p] + [str(v) for v in row] + [str(sum(row))])
            for s in range(12):
                v = row[s]
                key = "good" if v >= 6 else "warn" if v >= 4 else "bad"
                color_cells.append(("TEXTCOLOR", (s + 1, ri), (s + 1, ri), cmap[key]))
        sarva = akv["Sarva"]
        adata.append(["SARVA"] + [str(v) for v in sarva] + [str(sum(sarva))])
        sr = len(adata) - 1
        for s in range(12):
            v = sarva[s]
            key = "good" if v >= 30 else "warn" if v >= 26 else "bad"
            color_cells.append(("TEXTCOLOR", (s + 1, sr), (s + 1, sr), cmap[key]))
        at = Table(adata, repeatRows=1, colWidths=[16 * mm] + [12 * mm] * 12 + [12 * mm])
        at.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), paper),
            ("FONTNAME", (0, 0), (-1, 0), F_SER_B),
            ("FONTNAME", (0, -1), (0, -1), F_SER_B),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("TEXTCOLOR", (0, 0), (0, -1), ink),
            ("GRID", (0, 0), (-1, -1), 0.3, line),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ] + color_cells))
        return [Paragraph("Ashtakavarga", h2), at,
                Paragraph("Bhinna per planet + Sarva. Green strong · amber average · red "
                          "weak. Sarva: ≥30 strong, 26–29 average, ≤25 weak.", cap)]

    # ── varshaphala ──────────────────────────────────────────────────────
    def b_varsha():
        vp = chart.get("varshaphala")
        if not vp:
            return []
        vp_pl = {p: vp["planets"][p]["sign_idx"] for p in vp["planets"]}
        vp_det = {p: _detail_of(vp["planets"][p]) for p in vp["planets"]
                  if p != "Ascendant"}
        _vasc = vp["planets"].get("Ascendant")
        vp_lagna_det = _detail_of(_vasc) if _vasc else None
        return [
            Paragraph("Varshaphala (Solar Return)", h2),
            Paragraph(
                f"Year {vp['year_number']} ({vp['target_year']}–{vp['target_year']+1}) · "
                f"Annual Lagna <b>{vp['lagna']} {vp['lagna_pos']}</b> · "
                f"Muntha <b>{vp['muntha_sign']}</b> (lord {vp['muntha_lord']}) · "
                f"Varsha Pati <b>{vp['varsha_pati']}</b> · Solar return {vp['return_dt_utc']}",
                body),
            KeepTogether(crow(
                si_table("Varshaphala (annual)", vp_pl, vp["lagna_si"],
                         details=vp_det, lagna_detail=vp_lagna_det),
                Paragraph("Annual (solar-return) chart cast for the Sun's return to its "
                          "natal sidereal longitude. " + ("◆" if uni else "*") +
                          " marks the annual Lagna.", cap)))]

    # ── vimshottari dasha ────────────────────────────────────────────────
    def b_dasha():
        out = [Paragraph("Vimshottari Dasha", h2)]
        cur = chart["dashas"]["current"]
        if cur["maha"]:
            out.append(Paragraph(
                f"<b>Today:</b> Mahadasha {cur['maha']} -&gt; Antardasha {cur['antar']} "
                f"-&gt; Pratyantardasha {cur['pratyantar']}", body))
        ddata = [["Mahadasha", "Start", "End", "Years"]]
        for md in chart["dashas"]["mahadashas"]:
            mk = "  (now)" if md["active"] else ""
            ddata.append([md["planet"] + mk, fmt(md["start"]), fmt(md["end"]),
                          f"{md['years']:.1f}"])
        dt_tbl = Table(ddata, repeatRows=1, colWidths=[40*mm, 35*mm, 35*mm, 20*mm])
        dt_tbl.setStyle(_head_style())
        out.append(dt_tbl)
        act = next((md for md in chart["dashas"]["mahadashas"] if md["active"]), None)
        if act:
            out.append(Paragraph(f"Antardashas in {act['planet']} Mahadasha", h2))
            adata = [["Antardasha", "Start", "End", "Years"]]
            for ad in act["antardashas"]:
                mk = "  (now)" if ad["active"] else ""
                adata.append([f"{act['planet']} / {ad['planet']}{mk}",
                              fmt(ad["start"]), fmt(ad["end"]), f"{ad['years']:.2f}"])
            adt = Table(adata, repeatRows=1, colWidths=[50*mm, 35*mm, 35*mm, 20*mm])
            adt.setStyle(_head_style())
            out.append(adt)
        return out

    # ── transits for the customer report (Gochara chapter data) ──────────
    def b_transit_customer():
        tr = chart.get("transits", {})
        if not tr:
            return []
        trans_pl = {p: tr[p]["sign_idx"] for p in tr if p != "Ascendant"}
        tr_det = {p: _detail_of(tr[p]) for p in tr if p != "Ascendant"}
        return [Spacer(1, 2 * mm),
                KeepTogether(crow(
                    si_table(f"Transite {chart.get('transit_date','')}",
                             trans_pl, chart["lagna_idx"], details=tr_det),
                    Paragraph(T("Gochara: der laufende Himmel über dem Geburtshoroskop "
                                "— Häuser vom natalen Lagna gezählt, je Graha mit "
                                "Gradzahl, Nakshatra und Pada. Die Tabelle zeigt die "
                                "Ashtakavarga-Stützung (Bindus) jedes Transits."), cap)))
                ] + b_transit_strength()

    # ── transit strength (technical) ─────────────────────────────────────
    def b_transit_strength():
        tr = chart.get("transits", {})
        if not tr:
            return []
        tdata = [["Planet", "Natal", "Transit", "H", "Bindus", "Strength"]]
        for p in _AKV_PLANETS:
            nat = chart["planets"][p]["sign_idx"]; tsi = tr.get(p, {}).get("sign_idx", nat)
            b = chart["ashtakavarga"][p][tsi]
            s = "strong" if b >= 5 else "average" if b >= 4 else "weak"
            tdata.append([p, SIGNS[nat], SIGNS[tsi],
                          str((tsi - chart["lagna_idx"]) % 12 + 1), str(b), s])
        tt = Table(tdata, repeatRows=1, colWidths=[24*mm, 28*mm, 28*mm, 10*mm, 16*mm, 24*mm])
        tt.setStyle(_head_style())
        return [Paragraph(f"Transit Strength ({chart['transit_date']})", h2), tt]

    # ── jaimini karakas ──────────────────────────────────────────────────
    def b_jaimini():
        j = chart.get("jaimini")
        if not j:
            return []
        from astro_engine import CHARA_ABR, CHARA_MEANING
        out = [Paragraph("Jaimini — Chara Karakas (8-karaka, incl. Rahu)", h2),
               Paragraph(
                   f"Atmakaraka <b>{j['atmakaraka']}</b> · Darakaraka <b>{j['darakaraka']}</b> · "
                   f"Karakamsha <b>{j['karakamsha']}</b> (lord {j['karakamsha_lord']}) · "
                   f"Arudha Lagna <b>{j['arudha_lagna']}</b> (lord {j['arudha_lagna_lord']}) · "
                   f"Upapada Lagna <b>{j['upapada_lagna']}</b> (lord {j['upapada_lagna_lord']}). "
                   f"Rahu is reckoned in reverse (30 deg minus its degree).", body)]
        jdata = [["Karaka", "Significes", "Planet", "Sign", "Deg in sign", "Ranking deg"]]
        for r in j["order"]:
            k = j["karakas"][r]
            jdata.append([f"{CHARA_ABR[r]} {r}", CHARA_MEANING[r], k["planet"], k["sign"],
                          f"{k['deg_in_sign']:.2f}",
                          f"{k['effective']:.2f}{' (rev)' if k['reverse'] else ''}"])
        jt = Table(jdata, repeatRows=1,
                   colWidths=[34*mm, 34*mm, 20*mm, 22*mm, 24*mm, 26*mm])
        jt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), paper),
            ("FONTNAME", (0, 0), (-1, 0), F_SER_B),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#fdf3df")),
        ] + _base[1:]))
        out.append(jt)
        return out

    # ── chara dasha ──────────────────────────────────────────────────────
    def b_chara():
        cd = chart.get("chara_dasha")
        if not cd:
            return []
        out = [Paragraph("Jaimini — Chara Dasha", h2)]
        note = (f"Sign-based dasha from the Lagna at birth; direction: "
                f"<b>{cd['direction']}</b>. Duration = (count to lord) minus 1 year.")
        if cd.get("colords"):
            note += " Dual-lord signs resolved by Chara Bala (Jaimini strength): " + \
                    "; ".join(f"{sn} -&gt; {v['lord']} ({v['reason']})"
                              for sn, v in cd["colords"].items()) + "."
        out.append(Paragraph(note, body))
        cddata = [["Rasi", "Start", "End", "Years"]]
        for mm_ in cd["mahadashas"][:12]:
            mk = "  (now)" if mm_["active"] else ""
            cddata.append([mm_["sign"] + mk, fmt(mm_["start"]), fmt(mm_["end"]),
                           str(mm_["years"])])
        cdt = Table(cddata, repeatRows=1, colWidths=[40*mm, 35*mm, 35*mm, 20*mm])
        cdt.setStyle(_head_style())
        out.append(cdt)
        cact = next((mm_ for mm_ in cd["mahadashas"][:12] if mm_["active"]), None)
        if cact:
            out.append(Paragraph(f"Antardashas in {cact['sign']} (current Chara Mahadasha)", h2))
            cadata = [["Antardasha", "Start", "End", "Years"]]
            for a in cact["antardashas"]:
                mk = "  (now)" if a["active"] else ""
                cadata.append([f"{cact['sign']} / {a['sign']}{mk}",
                               fmt(a["start"]), fmt(a["end"]), str(a["years"])])
            cat = Table(cadata, repeatRows=1, colWidths=[40*mm, 35*mm, 35*mm, 20*mm])
            cat.setStyle(_head_style())
            out.append(cat)
        return out

    # ── panchang descriptions (from the static panchang_db table) ───────
    def b_panchang_desc():
        try:
            import panchang_db
        except Exception:
            return []
        rows = panchang_db.describe(chart.get("panchang") or {})
        if not rows:
            return []
        pd_ = [[el, val, Paragraph(T(txt), small)] for el, val, txt in rows]
        pt_ = Table(pd_, colWidths=[20 * mm, 44 * mm, 112 * mm])
        pt_.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), F_SER_B),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1),
             [colors.white, colors.HexColor("#f7f1e4")]),
        ] + _base[1:]))
        return [Spacer(1, 1.5 * mm),
                Paragraph(T("Pañcāṅga — die fünf Zeitqualitäten der Geburt"),
                          ParagraphStyle("panh", parent=h2, fontSize=10.5,
                                         spaceBefore=5, spaceAfter=2)),
                pt_]

    # ── panchang page (technical) ────────────────────────────────────────
    def b_panchang_page():
        pan = chart.get("panchang")
        if not pan:
            return []
        pdata = [["Tithi", f"{pan['tithi']}"],
                 ["Vara (weekday)", f"{pan['vara']} · ruled by {pan.get('vara_lord', '—')}"],
                 ["Nakshatra", f"{pan['nakshatra']} · ruled by {pan.get('nakshatra_lord', '—')}"],
                 ["Yoga", pan["yoga"]],
                 ["Karana", pan["karana"]]]
        pt = Table(pdata, colWidths=[42 * mm, 134 * mm])
        pt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), paper),
            ("FONTNAME", (0, 0), (0, -1), F_SER_B),
            ("FONTSIZE", (0, 0), (-1, -1), 9), ("TEXTCOLOR", (0, 0), (-1, -1), ink),
            ("GRID", (0, 0), (-1, -1), 0.3, line),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        notes = []
        if pan.get("tithi_num") in (4, 9, 14):
            notes.append("Rikta tithi (4/9/14) — generally weak for new beginnings.")
        if pan.get("paksha") == "Krishna" and pan.get("tithi_num") == 15:
            notes.append("Amavasya (new moon).")
        if pan.get("paksha") == "Shukla" and pan.get("tithi_num") == 15:
            notes.append("Purnima (full moon).")
        if pan.get("karana") == "Vishti":
            notes.append("Vishti (Bhadra) karana — traditionally avoided for auspicious acts.")
        if pan.get("yoga") in _MAL_YOGAS:
            notes.append(f"{pan['yoga']} is an inauspicious nitya-yoga.")
        return [Paragraph("Panchang of birth", h2), pt,
                Paragraph("Muhurta notes: " + (" ".join(notes) if notes else
                          "no Rikta tithi, Vishti karana or malefic nitya-yoga flagged."), cap)
                ] + b_panchang_desc()

    # ── sarvashtakavarga bar chart (technical) ───────────────────────────
    def b_sarva():
        akv = chart.get("ashtakavarga")
        sav = akv.get("Sarva") if akv else None
        if not sav:
            return []
        lag = chart.get("lagna_idx", 0)
        rowh, padL, bar_w = 15, 30, 320
        dw, dh = padL + bar_w + 34, 12 * rowh + 4
        d = Drawing(dw, dh)
        scale = bar_w / 45.0
        for i in range(12):
            v = sav[i]
            y = dh - (i + 1) * rowh + 4
            lbl = SIGN_ABR[i] + (" *" if i == lag else "")
            d.add(String(0, y, lbl, fontName=F_SANS, fontSize=7.5, fillColor=ink))
            cc = _GOOD if v >= 30 else _WARN if v >= 26 else _BAD
            d.add(Rect(padL, y - 1.5, max(1, v * scale), 9, fillColor=colors.HexColor(cc),
                       strokeColor=None))
            d.add(String(padL + v * scale + 4, y, str(v), fontName=F_SANS, fontSize=7.5,
                         fillColor=ink))
        return [Spacer(1, 4 * mm),
                Paragraph("Sarvashtakavarga — total bindus per sign", h2),
                Paragraph("Sum of all benefic points each sign receives (~28 is average; "
                          "higher signs support transits and houses more). * marks the "
                          "Lagna sign.", cap), d]

    # ── shad bala + ishta/kashta ─────────────────────────────────────────
    def b_shadbala():
        sb = chart.get("shadbala")
        if not sb:
            return []
        out = [Spacer(1, 4 * mm),
               Paragraph("Shad Bala — six-fold planetary strength", h2),
               Paragraph("Strength in virupas (60 = 1 rupa). Sthana, Dig, Paksha, Vara and "
                         "Naisargika are exact; Cheshta, Ayana and the sunrise-based Kala "
                         "parts are approximated — totals are indicative, the ranking and "
                         "position-based strengths reliable.", cap),
               Spacer(1, 1.5 * mm)]
        P = sb["planets"]
        sd = [["Planet", "Sthana", "Dig", "Kala", "Cheshta", "Naisarg", "Drik",
               "Rupas", "Req", ""]]
        for p in sb["order"]:
            d = P[p]
            mark = (f"<font color='{_GOOD}'>strong</font>" if d["strong"]
                    else f"<font color='{_BAD}'>weak</font>")
            sd.append([p, f"{d['sthana']:g}", f"{d['dig']:g}", f"{d['kala']:g}",
                       f"{d['cheshta']:g}", f"{d['naisargika']:g}", f"{d['drik']:g}",
                       f"{d['rupa']:g}", f"{d['required']:g}", Paragraph(mark, small)])
        sbt = Table(sd, repeatRows=1,
                    colWidths=[22 * mm, 18 * mm, 15 * mm, 16 * mm, 18 * mm, 18 * mm,
                               14 * mm, 16 * mm, 12 * mm, 17 * mm])
        sbt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), paper),
            ("FONTNAME", (0, 0), (-1, 0), F_SER_B),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ] + _base[1:]))
        out.append(sbt)
        out.append(Paragraph(f"Strongest: {sb['order'][0]} ({P[sb['order'][0]]['rupa']:g} "
                             f"rupas) · weakest: {sb['order'][-1]} "
                             f"({P[sb['order'][-1]]['rupa']:g} rupas).", cap))
        out.append(Spacer(1, 2 * mm))
        out.append(Paragraph("Ishta &amp; Kashta Phala — benefic vs difficult yield "
                             "(sqrt of Uccha &amp; Cheshta balas; 0–60 each).", cap))
        idata = [["Planet"] + sb["order"]]
        idata.append(["Ishta (good)"] + [f"{P[p].get('ishta', 0):g}" for p in sb["order"]])
        idata.append(["Kashta (hard)"] + [f"{P[p].get('kashta', 0):g}" for p in sb["order"]])
        it = Table(idata, colWidths=[26 * mm] + [(176 - 26) / 7 * mm] * 7)
        it.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), paper),
            ("FONTNAME", (0, 0), (0, -1), F_SER_B),
            ("FONTNAME", (0, 0), (-1, 0), F_SER_B),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ] + _base[1:]))
        out.append(it)
        return out

    # ── bhava bala (technical) ───────────────────────────────────────────
    def b_bhavabala():
        bb = chart.get("bhavabala")
        if not bb:
            return []
        H = bb["houses"]
        hd = [["House", "Sign", "Lord", "Adhipati", "Dig", "Drishti", "Rupas"]]
        for h in range(1, 13):
            d = H[h]
            hd.append([f"H{h}", d["sign"], d["lord"], f"{d['adhipati']:g}", f"{d['dig']:g}",
                       f"{d['drishti']:g}", f"{d['rupa']:g}"])
        bht = Table(hd, repeatRows=1,
                    colWidths=[16 * mm, 26 * mm, 24 * mm, 24 * mm, 18 * mm, 20 * mm, 18 * mm])
        bht.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), paper),
            ("FONTNAME", (0, 0), (-1, 0), F_SER_B),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (3, 0), (-1, -1), "CENTER"),
        ] + _base[1:]))
        bo = bb["order"]
        return [Spacer(1, 4 * mm),
                Paragraph("Bhava Bala — house strengths", h2),
                Paragraph("Per house: the house-lord's Shad Bala (Bhavadhipati) + Bhava Dig "
                          "Bala (sign type) + Bhava Drishti Bala (net aspects). Dig and "
                          "Drishti are approximated. Higher rupas = a more capable house.",
                          cap),
                Spacer(1, 1.5 * mm), bht,
                Paragraph(f"Strongest house: H{bo[0]} ({H[bo[0]]['sign']}, "
                          f"{H[bo[0]]['rupa']:g} rupas) · weakest: H{bo[-1]} "
                          f"({H[bo[-1]]['sign']}, {H[bo[-1]]['rupa']:g} rupas).", cap)]

    # ── yogas table ──────────────────────────────────────────────────────
    def b_yogas():
        yogas = chart.get("yogas")
        if not yogas:
            return []
        _YG = ["Pancha Mahapurusha", "Raja", "Dhana", "Vipareeta Raja", "Sun", "Moon", "Other"]
        _yorder = {g: i for i, g in enumerate(_YG)}
        yd = [["Group", "Yoga", "Planets", "What it means"]]
        for y in sorted(yogas, key=lambda y: _yorder.get(y["group"], 99)):
            yd.append([Paragraph(y["group"], small), Paragraph(y["name"], small),
                       Paragraph(", ".join(y["planets"]), small),
                       Paragraph(y["detail"], small)])
        yt = Table(yd, repeatRows=1, colWidths=[28 * mm, 30 * mm, 26 * mm, 92 * mm])
        yt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), paper),
            ("FONTNAME", (0, 0), (-1, 0), F_SER_B),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ] + _base))
        return [Paragraph("Yogas — planetary combinations", h2),
                Paragraph(f"{len(yogas)} yoga(s) read from the natal D1 (whole-sign houses, "
                          "graha drishti). Conventions vary by school — a study aid, not a "
                          "verdict.", cap),
                Spacer(1, 1.5 * mm), yt]

    # ── pada interpretations chapter ─────────────────────────────────────
    def b_pada():
        try:
            import pada_db
        except Exception:
            return []

        def _esc(s):
            return T(str(s)).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        p_head = ParagraphStyle("p_head", parent=h2, fontSize=11.5,
                                spaceBefore=9, spaceAfter=2)
        p_lbl = ParagraphStyle("p_lbl", parent=body, fontName=F_SER_B,
                               textColor=colors.HexColor("#8a6d1f"), fontSize=8,
                               spaceBefore=4, spaceAfter=0)
        p_txt = ParagraphStyle("p_txt", parent=body, fontSize=9, leading=13, spaceAfter=2)

        def _pada_block(title_txt, intro_txt, entry):
            blk = [Paragraph(_esc(title_txt), p_head)]
            if intro_txt:
                blk.append(Paragraph(f"<i>{_esc(intro_txt)}</i>", cap))
            for fld in pada_db.FIELD_ORDER:
                val = str(entry.get(fld, "")).strip()
                if not val:
                    continue
                blk.append(Paragraph(_esc(pada_db.FIELD_LABELS.get(fld, fld)), p_lbl))
                blk.append(Paragraph(_esc(val), p_txt))
            return blk

        pada_story = []
        if asc:
            a_entry = pada_db.get_pada(asc.get("nakshatra", ""), asc.get("pada", 0))
            if pada_db.has_content(a_entry):
                pada_story += _pada_block(
                    f"Lagna (Aszendent) · {asc['nakshatra']} Pada {asc['pada']} "
                    f"(Silbe {asc.get('syllable', '—')})",
                    "Der Aszendent prägt Persönlichkeit, Körper und Lebensausrichtung. "
                    "Sein Pada färbt die Grundnatur des gesamten Horoskops.",
                    a_entry)
        if _jai.get("arudha_lagna"):
            pada_story.append(Paragraph(
                f"Arudha Lagna · {_esc(_jai['arudha_lagna'])} "
                f"(Herr: {_esc(_jai.get('arudha_lagna_lord', '—'))})", p_head))
            pada_story.append(Paragraph(T(
                "Das Arudha Lagna (AL) ist die <i>Projektion</i> des Aszendenten — wie die "
                "Person von der Welt wahrgenommen wird: öffentliches Bild, Ruf und die "
                "materielle Erscheinung ihres Lebens (Māyā). Während das Lagna zeigt, wer "
                "man <i>ist</i>, zeigt das AL, als was man <i>erscheint</i>. Das AL ist eine "
                "reine Zeichen-Position (aus der Jaimini-Zählung von Lagna und dessen Herrn "
                "abgeleitet) und hat daher kein eigenes Nakshatra oder Pada. Sein Zeichen "
                f"{_jai['arudha_lagna']} und dessen Herr "
                f"{_jai.get('arudha_lagna_lord', '—')} prägen das öffentliche Bild; "
                "Planeten im 2. und 12. vom AL (Arudha-Dhana-Häuser) zeigen Zufluss und "
                "Abfluss von Ansehen und Wohlstand."), p_txt))
        for nm in PLANET_ORDER:
            p = chart["planets"][nm]
            entry = pada_db.get_pada(p.get("nakshatra", ""), p.get("pada", 0))
            if pada_db.has_content(entry):
                pada_story += _pada_block(
                    f"{nm} · {p['nakshatra']} Pada {p['pada']} "
                    f"(Silbe {p.get('syllable', '—')})", "", entry)
        if not pada_story:
            return []
        return ([PageBreak(),
                 Paragraph(T("Pada-Deutungen — Nakshatra-Viertel der Graha"), h2),
                 Paragraph(T("Jedes Nakshatra ist in vier Padas (Viertel zu 3°20′) geteilt; "
                             "das Pada verfeinert die Deutung von Lagna und Planeten. Die "
                             "folgenden Texte entsprechen der klassischen Pada-Bibliothek "
                             "der interaktiven Ansicht."), cap)]
                + pada_story)

    # ── eclipses ─────────────────────────────────────────────────────────
    def b_eclipses():
        try:
            import eclipse_db as _ecl
        except Exception:
            return []
        if not (_ecl and _ecl.available()):
            return []
        import re as _re_e
        import datetime as _dt_e
        _em = _ecl.meta()
        _y0, _y1 = _ecl.year_range()
        _now_y = _dt_e.date.today().year
        _birth_y = None
        _ym = _re_e.search(r"(\d{4})", str(chart.get("meta", {}).get("birth", "")))
        if _ym:
            _birth_y = int(_ym.group(1))
        _years = []
        if _birth_y and _y0 <= _birth_y <= _y1:
            _years.append(("Finsternisse im Geburtsjahr", [_birth_y]))
        _upc = [y for y in range(_now_y, _now_y + 3) if _y0 <= y <= _y1]
        if _upc:
            _years.append((f"Finsternisse {_upc[0]}–{_upc[-1]} (aktuell & kommend)", _upc))
        if not _years:
            return []
        out = [PageBreak(),
               Paragraph("Finsternisse (Sonnen- &amp; Mondfinsternisse)", h2),
               Paragraph(T(
                   "Siderische Positionen (Lahiri-Ayanamsha) der verfinsterten Lichter — "
                   "Sonne bei Sonnen-, Mond bei Mondfinsternissen. Sichtbarkeit bezogen auf "
                   f"{_em.get('observer', '—')}. Die vollständige Tabelle {_y0}–{_y1} "
                   "steht in der interaktiven Ansicht."), cap)]
        _grp = _ecl.by_year()
        for _title, _ys in _years:
            out.append(Spacer(1, 2 * mm))
            out.append(Paragraph(_title, ParagraphStyle(
                "eh", parent=h2, fontSize=10.5, spaceBefore=6, spaceAfter=2)))
            ed = [["Datum", "Zeit (UT)", "Art", "Typ", "Zeichen", "Grad",
                   "Nakshatra", "Sichtbar"]]
            for _y in _ys:
                for e in _grp.get(_y, []):
                    _kind = ("Sonnenfinsternis" if e["kind"] == "solar"
                             else "Mondfinsternis")
                    _vis = e.get("visible_wadenswil")
                    _vtxt = ("ja" if _vis is True else "nein" if _vis is False else "—")
                    ed.append([f"{e['day']:02d}.{e['month']:02d}.{e['year']}",
                               e.get("time_ut", ""), _kind, e.get("type", ""),
                               e.get("sign", ""), e.get("deg_str", ""),
                               f"{e.get('nakshatra', '')} P{e.get('pada', '')}", _vtxt])
            et = Table(ed, repeatRows=1,
                       colWidths=[19*mm, 16*mm, 32*mm, 17*mm, 20*mm, 17*mm, 40*mm, 15*mm])
            et.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), paper),
                ("FONTNAME", (0, 0), (-1, 0), F_SER_B),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 2.2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
            ] + _base[1:3]))
            out.append(et)
        out.append(Paragraph(T(
            "Finsternisse nahe natalen Planeten oder dem Lagna (±2–3°) gelten "
            "klassisch als besonders wirksam."), cap))
        return out

    # Injection blocks for the customer variant, in Methodik order.
    _blocks = {
        "d1":      lambda: b_d1_only() + b_planets() + b_houses(),
        "yoga":    lambda: b_yogas() + b_shadbala(),
        "d9":      b_d9_only,
        "d10":     b_d10_only,
        "d3d4":    b_d3d4,
        "dasha":   b_dasha,
        "transit": b_transit_customer,
        "jaimini": lambda: b_jaimini() + b_chara(),
        "varsha":  b_varsha,
    }
    _METHODIK_ORDER = ["d1", "yoga", "d9", "d10", "d3d4", "dasha", "transit",
                       "jaimini", "varsha"]

    # ══════════════════════════════════════════════════════════════════════
    # Assemble the document
    # ══════════════════════════════════════════════════════════════════════
    story = []
    injected = set()

    if not tech:
        # customer title page
        tp_title = ParagraphStyle("tp_title", parent=h1, fontSize=26, leading=32,
                                  spaceBefore=0, spaceAfter=6)
        tp_name = ParagraphStyle("tp_name", parent=h1, fontName=F_SER,
                                 fontSize=18, textColor=ink, spaceAfter=4)
        tp_line = ParagraphStyle("tp_line", parent=sub, fontSize=10.5, leading=16)
        story.append(Spacer(1, 52 * mm))
        story.append(Paragraph(T("✦"), ParagraphStyle(
            "tp_star", parent=sub, fontSize=16, textColor=colors.HexColor("#b8902f"))))
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph(T(interpretation_title or "Persönliche Deutung"), tp_title))
        story.append(Paragraph(T("Jyotiṣa · Vedische Astrologie"), tp_line))
        story.append(Spacer(1, 14 * mm))
        if m.get("name"):
            story.append(Paragraph(T(m["name"]), tp_name))
        story.append(Paragraph(T(f"{m['birth']} ({m['tz']}) · {m['location'] or ''}"), tp_line))
        story.append(Paragraph(T(f"Lagna: {chart['lagna']} {chart['lagna_pos']} · "
                                 f"Lahiri-Ayanamsha · Ganzzeichen-Häuser"), tp_line))
        story.append(Spacer(1, 60 * mm))
        story.append(Paragraph("AstroVeda · reports.astroveda.ch", tp_line))
        story.append(PageBreak())

    story.append(Paragraph("✦ Vedic Astrology Birth Chart ✦" if tech
                           else T("Geburtshoroskop — Übersicht"), h1))
    story.append(Paragraph("Jyotisha · Lahiri Ayanamsha · Whole-Sign Houses", sub))

    g = f" ({m['gender']})" if m.get("gender") else ""
    meta_rows = [
        ["Name", f"{m.get('name') or '—'}{g}"],
        ["Birth", f"{m['birth']}  ({m['tz']})"],
        ["UT", m["ut"]],
        ["Location", f"{m['location'] or '—'}  ·  {m['lat']:.4f}° N / {m['lon']:.4f}° E"],
        ["Lagna", f"{chart['lagna']} {chart['lagna_pos']}"],
        ["Julian Day / Ayanamsha", f"{m['jd']}  /  {m['ayan']}° (Lahiri)"],
        ["Engine", m["engine"]],
    ]
    mt = Table(meta_rows, colWidths=[42 * mm, 130 * mm])
    mt.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), F_SER_B),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TEXTCOLOR", (0, 0), (-1, -1), ink),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, line),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(mt)

    pa = chart.get("panchang")
    if pa:
        story.append(Paragraph(
            f"<b>Panchanga:</b> Tithi {pa['tithi']} (lunar day {pa['tithi_num']}/30) · "
            f"Vara {pa['vara']} (lord {pa['vara_lord']}) · Nakshatra {pa['nakshatra']} "
            f"(lord {pa['nakshatra_lord']}) · Yoga {pa['yoga']} · Karana {pa['karana']}.", body))
        if not tech:
            story.extend(b_panchang_desc())

    # ── AI interpretation ─────────────────────────────────────────────────
    if interpretation and interpretation.strip():
        ih = ParagraphStyle("ih", parent=h2, fontSize=15, spaceBefore=12, spaceAfter=6)
        ph = ParagraphStyle("ph", parent=h2, fontSize=11.5, spaceBefore=9, spaceAfter=3)
        pbody = ParagraphStyle("pbody", parent=body, fontSize=9.5, leading=14, spaceAfter=5)

        def _inline(s):
            s = T(s)
            s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            s = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
            s = _re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", s)
            return s

        story.append(PageBreak())
        story.append(Paragraph(T(interpretation_title), ih))
        buf = []
        pending_key = None      # data block owed to the section we're inside

        def _flush():
            if buf:
                story.append(Paragraph(" ".join(buf), pbody))
                buf.clear()

        def _inject_pending():
            nonlocal pending_key
            if not tech and pending_key and pending_key not in injected:
                blk = _blocks.get(pending_key)
                if blk:
                    story.append(Spacer(1, 2 * mm))
                    story.extend(blk())
                    injected.add(pending_key)
            pending_key = None

        for raw in interpretation.splitlines():
            ln = raw.rstrip()
            if not ln.strip():
                _flush()
                continue
            if ln.lstrip().startswith("#"):
                _flush()
                _inject_pending()                      # data of the finished chapter
                txt = ln.lstrip("# ").strip()
                pending_key = _match_block(txt)
                story.append(Paragraph(_inline(txt), ph))
            elif ln.lstrip()[:2] in ("- ", "* ") or ln.lstrip().startswith("•"):
                _flush()
                txt = _re.sub(r"^[-*•]+\s+", "", ln.lstrip()).strip()
                story.append(Paragraph(("◆" if uni else "*") + "&nbsp;&nbsp;" + _inline(txt),
                                       pbody))
            else:
                buf.append(_inline(ln.strip()))
        _flush()
        _inject_pending()
        story.append(Paragraph(
            "<i>Dieser Bericht wurde KI-gestützt aus dem exakt berechneten Horoskop erstellt "
            "und dient der persönlichen Reflexion.</i>", cap))
        story.append(PageBreak())

    if tech:
        # ── technical report: fixed classical order, everything included ─
        story.extend(b_planets())
        story.extend(b_pada())
        story.extend(b_houses())
        story.extend(b_d1d9())
        story.extend(b_d3d10d4_tech())
        story.extend(b_bhava_transit())
        story.extend(b_akv())
        story.extend(b_varsha())
        story.extend(b_dasha())
        story.extend(b_transit_strength())
        story.extend(b_jaimini())
        story.extend(b_chara())
        pg = b_panchang_page()
        if pg:
            story.append(PageBreak())
            story.extend(pg)
        story.extend(b_sarva())
        story.extend(b_shadbala())
        story.extend(b_bhavabala())
        yg = b_yogas()
        if yg:
            story.append(PageBreak())
            story.extend(yg)
    else:
        # ── customer: append whatever the interpretation didn't trigger ──
        # (Methodik order; e.g. Basis reports have fewer chapters)
        for key in _METHODIK_ORDER:
            if key in injected:
                continue
            blk = _blocks[key]()
            if blk:
                story.append(Spacer(1, 2 * mm))
                story.extend(blk)
                injected.add(key)
        # Nakshatra-Pada chapter (Methodik 06) as its own reference part
        story.extend(b_pada())

    # ── compatibility (partnership product) ──────────────────────────────
    if compat:
        story.append(PageBreak())
        story.append(Paragraph("Marriage / Partnership Compatibility", h1))
        story.append(Paragraph("Ashtakoota (Guna Milan) · Moon-nakshatra matching", sub))
        story.append(Paragraph(
            f"<b>{compat['a_name']}</b> (Moon {compat['a_moon']})  &amp;  "
            f"<b>{compat['b_name']}</b> (Moon {compat['b_moon']}"
            + (f", {compat['b_loc']}" if compat.get("b_loc") else "") + ")", body))
        tot = compat["total"]; mx = compat.get("max", 36)
        vhex = _GOOD if tot >= 25 else _WARN if tot >= 18 else _BAD
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(
            f"<b>Guna Milan:</b> <font color='{vhex}'>{tot:g} / {mx} — {compat['verdict']}</font>"
            "  <font size=7 color='#7a6a4c'>(≥18 is the usual minimum)</font>", body))
        story.append(Spacer(1, 2 * mm))
        kd = [["Kuta", "Score", "Meaning"]]
        for k in compat["kutas"]:
            kd.append([k["name"], f"{k['got']:g} / {k['max']}", Paragraph(k["note"], small)])
        kt = Table(kd, repeatRows=1, colWidths=[26 * mm, 20 * mm, 116 * mm])
        kt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), paper),
            ("FONTNAME", (0, 0), (-1, 0), F_SER_B),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ] + _base))
        story.append(kt)
        story.append(Spacer(1, 2 * mm))
        for d in compat.get("doshas", []):
            if d["active"]:
                story.append(Paragraph(
                    f"<b><font color='{_BAD}'>{d['name']} dosha</font></b> present — "
                    f"{d['reason']}. A traditional caution.", body))
            else:
                story.append(Paragraph(
                    f"<b>{d['name']} dosha</b> present but <font color='{_GOOD}'>cancelled</font> "
                    f"— {d['reason']}.", body))
        if not compat.get("doshas"):
            story.append(Paragraph("No Nadi or Bhakoot dosha.", body))
        mg = compat.get("mangal")
        if mg and mg.get("a") and mg.get("b"):
            a_m, b_m = mg["a"]["manglik"], mg["b"]["manglik"]
            if a_m and b_m:
                mtxt = "Both partners are Manglik — Mangal dosha is mutually cancelled."
            elif a_m or b_m:
                mtxt = (f"Only {mg['a_name'] if a_m else mg['b_name']} is Manglik — "
                        "classically a caution.")
            else:
                mtxt = "Neither partner is Manglik."
            story.append(Paragraph(f"<b>Mangal (Kuja) dosha:</b> {mtxt}", body))
            story.append(Paragraph(f"{mg['a_name']}: {mg['a']['note']} · "
                                   f"{mg['b_name']}: {mg['b']['note']}", cap))
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(
            "Ashtakoota reflects Moon-nakshatra harmony only; a full match also weighs the "
            "7th house, Venus/Mars and dasha timing. Conventions vary by tradition.", cap))

    story.extend(b_eclipses())

    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("AstroVeda · reports.astroveda.ch · zur Studie und persönlichen "
                           "Reflexion.", cap))

    buf_out = BytesIO()
    doc = SimpleDocTemplate(buf_out, pagesize=A4,
                            leftMargin=14*mm, rightMargin=14*mm,
                            topMargin=12*mm, bottomMargin=12*mm,
                            title="Vedic Birth Chart")
    doc.build(story)
    return buf_out.getvalue()

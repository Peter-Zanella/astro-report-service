#!/usr/bin/env python3
"""
PDF report for a computed Jyotiṣa chart, using reportlab (pure-Python).

build_pdf(chart) -> bytes      raises RuntimeError if reportlab is missing.
"""
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


def build_pdf(chart: dict, compat: dict = None, interpretation: str = None,
              interpretation_title: str = "Persönliche Deutung") -> bytes:
    if not _have_reportlab():
        raise RuntimeError("reportlab not installed")

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether,
    )

    ink = colors.HexColor(_INK); accent = colors.HexColor(_ACCENT)
    line = colors.HexColor(_LINE); paper = colors.HexColor(_PAPER)
    lagna_bg = colors.HexColor(_LAGNA)
    cmap = {"good": colors.HexColor(_GOOD), "warn": colors.HexColor(_WARN),
            "bad": colors.HexColor(_BAD)}

    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], textColor=accent, fontName="Times-Bold",
                        fontSize=20, spaceAfter=2, alignment=1)
    sub = ParagraphStyle("sub", parent=ss["Normal"], textColor=ink, fontSize=9,
                         alignment=1, spaceAfter=10)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=accent,
                        fontName="Times-Bold", fontSize=13, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("body", parent=ss["Normal"], textColor=ink, fontSize=9, leading=13)
    small = ParagraphStyle("small", parent=ss["Normal"], textColor=ink, fontSize=7.5, leading=9)
    cap = ParagraphStyle("cap", parent=ss["Normal"], textColor=colors.HexColor("#7a6a4c"),
                         fontSize=7.5, leading=10)

    m = chart["meta"]
    story = []

    story.append(Paragraph("✦ Vedic Astrology Birth Chart ✦", h1))
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
        ("FONTNAME", (0, 0), (0, -1), "Times-Bold"),
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

    # ── AI interpretation (optional) ────────────────────────────────────────────
    if interpretation and interpretation.strip():
        import re as _re
        from reportlab.platypus import PageBreak
        ih = ParagraphStyle("ih", parent=h2, fontSize=15, spaceBefore=12, spaceAfter=6)
        ph = ParagraphStyle("ph", parent=h2, fontSize=11.5, spaceBefore=9, spaceAfter=3)
        pbody = ParagraphStyle("pbody", parent=body, fontSize=9.5, leading=14, spaceAfter=5)

        def _inline(s):
            s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            s = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
            s = _re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", s)
            return s

        story.append(PageBreak())
        story.append(Paragraph(interpretation_title, ih))
        buf = []

        def _flush():
            if buf:
                story.append(Paragraph(" ".join(buf), pbody))
                buf.clear()

        for raw in interpretation.splitlines():
            ln = raw.rstrip()
            if not ln.strip():
                _flush()
                continue
            if ln.lstrip().startswith("#"):
                _flush()
                txt = ln.lstrip("# ").strip()
                story.append(Paragraph(_inline(txt), ph))
            elif ln.lstrip()[:2] in ("- ", "* ") or ln.lstrip().startswith("•"):
                _flush()
                txt = _re.sub(r"^[-*•]+\s+", "", ln.lstrip()).strip()
                story.append(Paragraph("◆&nbsp;&nbsp;" + _inline(txt), pbody))
            else:
                buf.append(_inline(ln.strip()))
        _flush()
        story.append(Paragraph(
            "<i>Dieser Bericht wurde KI-gestützt aus dem exakt berechneten Horoskop erstellt "
            "und dient der persönlichen Reflexion.</i>", cap))
        story.append(PageBreak())

    # ── planets ───────────────────────────────────────────────────────────────
    story.append(Paragraph("Graha (Planets)", h2))
    head = ["Planet", "Sign", "Pos", "H", "Nakshatra", "Pada", "Syl", "Lord", "Dignity"]
    data = [head]
    row_styles = []
    # Lagna (Ascendant) row — mirrors the web view
    asc = chart["planets"].get("Ascendant")
    if asc:
        data.append(["Lagna", asc["sign"], asc["pos"], "1", asc["nakshatra"],
                     str(asc["pada"]), asc.get("syllable", "—"), asc["nak_lord"], "—"])
        row_styles.append(("BACKGROUND", (0, len(data) - 1), (-1, len(data) - 1), lagna_bg))
    # Arudha Lagna row — sign-based only (no degree / nakshatra / pada)
    _jai = chart.get("jaimini") or {}
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
        ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("TEXTCOLOR", (0, 0), (-1, -1), ink),
        ("GRID", (0, 0), (-1, -1), 0.3, line),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f1e4")]),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ] + row_styles))
    story.append(pt)

    # ── Pada interpretations (static 108-pada DB — same content as the web view) ─
    try:
        import pada_db
    except Exception:
        pada_db = None
    if pada_db:
        import re as _re_p
        from reportlab.platypus import PageBreak

        def _esc(s):
            return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        p_head = ParagraphStyle("p_head", parent=h2, fontSize=11.5,
                                spaceBefore=9, spaceAfter=2)
        p_lbl = ParagraphStyle("p_lbl", parent=body, fontName="Times-Bold",
                               textColor=colors.HexColor("#8a6d1f"), fontSize=8,
                               spaceBefore=4, spaceAfter=0)
        p_txt = ParagraphStyle("p_txt", parent=body, fontSize=9, leading=13,
                               spaceAfter=2)

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
        # Lagna first — mirrors the web view's expandable Lagna row
        if asc:
            a_entry = pada_db.get_pada(asc.get("nakshatra", ""), asc.get("pada", 0))
            if pada_db.has_content(a_entry):
                pada_story += _pada_block(
                    f"Lagna (Aszendent) · {asc['nakshatra']} Pada {asc['pada']} "
                    f"(Silbe {asc.get('syllable', '—')})",
                    "Der Aszendent prägt Persönlichkeit, Körper und Lebensausrichtung. "
                    "Sein Pada färbt die Grundnatur des gesamten Horoskops.",
                    a_entry)
        # Arudha Lagna — sign-based explanation (no pada of its own)
        if _jai.get("arudha_lagna"):
            pada_story.append(Paragraph(
                f"Arudha Lagna · {_esc(_jai['arudha_lagna'])} "
                f"(Herr: {_esc(_jai.get('arudha_lagna_lord', '—'))})", p_head))
            pada_story.append(Paragraph(
                "Das Arudha Lagna (AL) ist die <i>Projektion</i> des Aszendenten — wie die "
                "Person von der Welt wahrgenommen wird: öffentliches Bild, Ruf und die "
                "materielle Erscheinung ihres Lebens (Māyā). Während das Lagna zeigt, wer "
                "man <i>ist</i>, zeigt das AL, als was man <i>erscheint</i>. Das AL ist eine "
                "reine Zeichen-Position (aus der Jaimini-Zählung von Lagna und dessen Herrn "
                "abgeleitet) und hat daher kein eigenes Nakshatra oder Pada. Sein Zeichen "
                f"{_esc(_jai['arudha_lagna'])} und dessen Herr "
                f"{_esc(_jai.get('arudha_lagna_lord', '—'))} prägen das öffentliche Bild; "
                "Planeten im 2. und 12. vom AL (Arudha-Dhana-Häuser) zeigen Zufluss und "
                "Abfluss von Ansehen und Wohlstand.", p_txt))
        for nm in PLANET_ORDER:
            p = chart["planets"][nm]
            entry = pada_db.get_pada(p.get("nakshatra", ""), p.get("pada", 0))
            if pada_db.has_content(entry):
                pada_story += _pada_block(
                    f"{nm} · {p['nakshatra']} Pada {p['pada']} "
                    f"(Silbe {p.get('syllable', '—')})", "", entry)
        if pada_story:
            story.append(PageBreak())
            story.append(Paragraph("Pada-Deutungen — Nakshatra-Viertel der Graha", h2))
            story.append(Paragraph(
                "Jedes Nakshatra ist in vier Padas (Viertel zu 3°20′) geteilt; das Pada "
                "verfeinert die Deutung von Lagna und Planeten. Die folgenden Texte "
                "entsprechen der klassischen Pada-Bibliothek der interaktiven Ansicht.", cap))
            story.extend(pada_story)

    # ── houses ────────────────────────────────────────────────────────────────
    story.append(Paragraph("Bhava (Houses)", h2))
    hdata = [["H", "Sign", "Lord", "Occupants"]]
    for h in range(1, 13):
        sn = chart["houses"][h]
        hdata.append([str(h), sn, SIGN_LORDS[sn], ", ".join(chart["occupants"][h]) or "—"])
    ht = Table(hdata, repeatRows=1, colWidths=[10*mm, 22*mm, 22*mm, 118*mm])
    ht.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), paper),
        ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("TEXTCOLOR", (0, 0), (-1, -1), ink),
        ("GRID", (0, 0), (-1, -1), 0.3, line),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    story.append(ht)

    # ── South Indian D1 + D9 as tables ──────────────────────────────────────────
    def si_table(title, placements, lagna_si, cellmap=_SIGN_CELL):
        natal = {i: [] for i in range(12)}
        for p, si in placements.items():
            if p != "Ascendant":
                natal[si].append(PLANET_ABR.get(p, p[:2]))
        grid_sign = {pos: si for si, pos in cellmap.items()}
        data = [[None] * 4 for _ in range(4)]
        spans = []
        for (r, c), si in grid_sign.items():
            house = (si - lagna_si) % 12 + 1
            tag = "◆" if si == lagna_si else ""
            txt = f"<b>{SIGN_ABR[si]}{tag} H{house}</b>"
            if natal[si]:
                txt += "<br/>" + " ".join(natal[si])
            data[r][c] = Paragraph(txt, small)
        data[1][1] = Paragraph(f"<b>{title}</b>", ParagraphStyle(
            "ctr", parent=small, alignment=1, textColor=accent, fontName="Times-Bold", fontSize=9))
        data[1][2] = ""; data[2][1] = ""; data[2][2] = ""
        spans.append(("SPAN", (1, 1), (2, 2)))
        t = Table(data, colWidths=[22 * mm] * 4, rowHeights=[18 * mm] * 4)
        styl = [("GRID", (0, 0), (-1, -1), 0.4, line),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (1, 1), (2, 2), paper)]
        for (r, c), si in grid_sign.items():
            if si == lagna_si:
                styl.append(("BACKGROUND", (c, r), (c, r), lagna_bg))
        t.setStyle(TableStyle(styl + spans))
        return t

    story.append(Paragraph("Divisional Charts (South Indian)", h2))
    d1_pl = {p: chart["planets"][p]["sign_idx"] for p in chart["planets"]}
    crow = lambda a, b: Table([[a, b]], colWidths=[90 * mm, 90 * mm], style=TableStyle(
        [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(KeepTogether(crow(
        si_table("D1 Rasi", d1_pl, chart["lagna_idx"]),
        si_table("D9 Navamsa", chart["d9"], chart["d9_lagna"]))))
    story.append(Spacer(1, 3 * mm))
    story.append(KeepTogether(crow(
        si_table("D3 Drekkana", chart["d3"], chart["d3_lagna"]),
        si_table("D10 Dasamsha", chart["d10"], chart["d10_lagna"]))))
    if chart.get("d4"):
        story.append(Spacer(1, 3 * mm))
        story.append(KeepTogether(crow(
            si_table("D4 Chaturthamsha", chart["d4"], chart["d4_lagna"]),
            Paragraph("D4 (Chaturthamsha): Besitz, Immobilien, häusliches Glück. "
                      "D3: Geschwister &amp; Mut · D9: Ehe &amp; Dharma · "
                      "D10: Beruf &amp; Wirkung in der Welt.", cap))))

    # ── bhava chalit chart + transit charts ─────────────────────────────────────
    tr = chart.get("transits", {})
    trans_pl = {p: tr[p]["sign_idx"] for p in tr if p != "Ascendant"} if tr else {}
    bhava_pl = chart.get("bhava", {}).get("place") or d1_pl   # fallback to rasi if absent
    t_lagna  = chart.get("transit_lagna_idx", chart["lagna_idx"])
    story.append(Paragraph("Bhava Chalit &amp; Transit Charts (South Indian)", h2))
    story.append(KeepTogether(crow(
        si_table("Bhava Chalit", bhava_pl, chart["lagna_idx"]),
        si_table(f"Transits (vs natal) {chart.get('transit_date','')}",
                 trans_pl, chart["lagna_idx"]))))
    story.append(KeepTogether(crow(
        si_table(f"Now-chart · Lagna {chart.get('transit_lagna_pos','')} {SIGNS[t_lagna]}",
                 trans_pl, t_lagna),
        Spacer(1, 1))))
    story.append(Paragraph(
        "Bhava Chalit: houses centred on the Ascendant degree, so a planet near a sign edge "
        "can fall into the adjacent bhava. &nbsp; Transits (vs natal): current sky against the "
        "birth Lagna. &nbsp; Now-chart: same transiting planets, but houses counted from the "
        f"Lagna at chart-creation time ({chart.get('transit_local', chart.get('transit_date',''))} "
        "local, at the birthplace).", cap))

    # ── ashtakavarga ────────────────────────────────────────────────────────────
    story.append(Paragraph("Ashtakavarga", h2))
    akv = chart["ashtakavarga"]
    head = [""] + SIGN_ABR + ["Σ"]
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
    at = Table(adata, repeatRows=1,
               colWidths=[16 * mm] + [12 * mm] * 12 + [12 * mm])
    at.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), paper),
        ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
        ("FONTNAME", (0, -1), (0, -1), "Times-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("TEXTCOLOR", (0, 0), (0, -1), ink),
        ("GRID", (0, 0), (-1, -1), 0.3, line),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ] + color_cells))
    story.append(at)
    story.append(Paragraph("Bhinna per planet + Sarva. Green strong · amber average · red weak. "
                           "Sarva: ≥30 strong, 26–29 average, ≤25 weak.", cap))

    # ── varshaphala ─────────────────────────────────────────────────────────────
    vp = chart.get("varshaphala")
    if vp:
        story.append(Paragraph("Varshaphala (Solar Return)", h2))
        story.append(Paragraph(
            f"Year {vp['year_number']} ({vp['target_year']}–{vp['target_year']+1}) · "
            f"Annual Lagna <b>{vp['lagna']} {vp['lagna_pos']}</b> · "
            f"Muntha <b>{vp['muntha_sign']}</b> (lord {vp['muntha_lord']}) · "
            f"Varsha Pati <b>{vp['varsha_pati']}</b> · Solar return {vp['return_dt_utc']}", body))
        vp_pl = {p: vp["planets"][p]["sign_idx"] for p in vp["planets"]}
        story.append(KeepTogether(crow(
            si_table("Varshaphala (annual)", vp_pl, vp["lagna_si"]),
            Paragraph("Annual (solar-return) chart cast for the Sun's return to its natal "
                      "sidereal longitude. ◆ marks the annual Lagna.", cap))))

    # ── dasha ───────────────────────────────────────────────────────────────────
    story.append(Paragraph("Vimshottari Dasha", h2))
    cur = chart["dashas"]["current"]
    if cur["maha"]:
        story.append(Paragraph(
            f"<b>Today:</b> Mahadasha {cur['maha']} -&gt; Antardasha {cur['antar']} "
            f"-&gt; Pratyantardasha {cur['pratyantar']}", body))
    fmt = lambda dt: dt.strftime("%d %b %Y")
    ddata = [["Mahadasha", "Start", "End", "Years"]]
    for md in chart["dashas"]["mahadashas"]:
        mk = "  (now)" if md["active"] else ""
        ddata.append([md["planet"] + mk, fmt(md["start"]), fmt(md["end"]), f"{md['years']:.1f}"])
    dt_tbl = Table(ddata, repeatRows=1, colWidths=[40*mm, 35*mm, 35*mm, 20*mm])
    dt_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), paper),
        ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("TEXTCOLOR", (0, 0), (-1, -1), ink),
        ("GRID", (0, 0), (-1, -1), 0.3, line),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    story.append(dt_tbl)

    # active antardashas
    act = next((md for md in chart["dashas"]["mahadashas"] if md["active"]), None)
    if act:
        story.append(Paragraph(f"Antardashas in {act['planet']} Mahadasha", h2))
        adata = [["Antardasha", "Start", "End", "Years"]]
        for ad in act["antardashas"]:
            mk = "  (now)" if ad["active"] else ""
            adata.append([f"{act['planet']} / {ad['planet']}{mk}",
                          fmt(ad["start"]), fmt(ad["end"]), f"{ad['years']:.2f}"])
        adt = Table(adata, repeatRows=1, colWidths=[50*mm, 35*mm, 35*mm, 20*mm])
        adt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), paper), ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8), ("TEXTCOLOR", (0, 0), (-1, -1), ink),
            ("GRID", (0, 0), (-1, -1), 0.3, line),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
        story.append(adt)

    # ── transit strength ────────────────────────────────────────────────────────
    tr = chart.get("transits", {})
    if tr:
        story.append(Paragraph(f"Transit Strength ({chart['transit_date']})", h2))
        tdata = [["Planet", "Natal", "Transit", "H", "Bindus", "Strength"]]
        for p in _AKV_PLANETS:
            nat = chart["planets"][p]["sign_idx"]; tsi = tr.get(p, {}).get("sign_idx", nat)
            b = chart["ashtakavarga"][p][tsi]
            s = "strong" if b >= 5 else "average" if b >= 4 else "weak"
            tdata.append([p, SIGNS[nat], SIGNS[tsi], str((tsi - chart["lagna_idx"]) % 12 + 1),
                          str(b), s])
        tt = Table(tdata, repeatRows=1, colWidths=[24*mm, 28*mm, 28*mm, 10*mm, 16*mm, 24*mm])
        tt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), paper), ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8), ("TEXTCOLOR", (0, 0), (-1, -1), ink),
            ("GRID", (0, 0), (-1, -1), 0.3, line),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
        story.append(tt)

    # ── jaimini ─────────────────────────────────────────────────────────────────
    j = chart.get("jaimini")
    if j:
        from astro_engine import CHARA_ABR, CHARA_MEANING
        story.append(Paragraph("Jaimini — Chara Karakas (8-karaka, incl. Rahu)", h2))
        story.append(Paragraph(
            f"Atmakaraka <b>{j['atmakaraka']}</b> · Darakaraka <b>{j['darakaraka']}</b> · "
            f"Karakamsha <b>{j['karakamsha']}</b> (lord {j['karakamsha_lord']}) · "
            f"Arudha Lagna <b>{j['arudha_lagna']}</b> (lord {j['arudha_lagna_lord']}) · "
            f"Upapada Lagna <b>{j['upapada_lagna']}</b> (lord {j['upapada_lagna_lord']}). "
            f"Rahu is reckoned in reverse (30 deg minus its degree).", body))
        jdata = [["Karaka", "Significes", "Planet", "Sign", "Deg in sign", "Ranking deg"]]
        for r in j["order"]:
            k = j["karakas"][r]
            jdata.append([f"{CHARA_ABR[r]} {r}", CHARA_MEANING[r], k["planet"], k["sign"],
                          f"{k['deg_in_sign']:.2f}",
                          f"{k['effective']:.2f}{' (rev)' if k['reverse'] else ''}"])
        jt = Table(jdata, repeatRows=1,
                   colWidths=[34*mm, 34*mm, 20*mm, 22*mm, 24*mm, 26*mm])
        jt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), paper), ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("TEXTCOLOR", (0, 0), (-1, -1), ink),
            ("GRID", (0, 0), (-1, -1), 0.3, line),
            ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#fdf3df")),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
        story.append(jt)

    # ── chara dasha ─────────────────────────────────────────────────────────────
    cd = chart.get("chara_dasha")
    if cd:
        story.append(Paragraph("Jaimini — Chara Dasha", h2))
        note = (f"Sign-based dasha from the Lagna at birth; direction: <b>{cd['direction']}</b>. "
                f"Duration = (count to lord) minus 1 year.")
        if cd.get("colords"):
            note += " Dual-lord signs resolved by Chara Bala (Jaimini strength): " + \
                    "; ".join(f"{sn} -&gt; {v['lord']} ({v['reason']})"
                              for sn, v in cd["colords"].items()) + "."
        story.append(Paragraph(note, body))
        cddata = [["Rasi", "Start", "End", "Years"]]
        for m in cd["mahadashas"][:12]:
            mk = "  (now)" if m["active"] else ""
            cddata.append([m["sign"] + mk, fmt(m["start"]), fmt(m["end"]), str(m["years"])])
        cdt = Table(cddata, repeatRows=1, colWidths=[40*mm, 35*mm, 35*mm, 20*mm])
        cdt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), paper), ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8), ("TEXTCOLOR", (0, 0), (-1, -1), ink),
            ("GRID", (0, 0), (-1, -1), 0.3, line),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
        story.append(cdt)
        # antardashas of the active Chara mahadasha
        cact = next((m for m in cd["mahadashas"][:12] if m["active"]), None)
        if cact:
            story.append(Paragraph(f"Antardashas in {cact['sign']} (current Chara Mahadasha)", h2))
            cadata = [["Antardasha", "Start", "End", "Years"]]
            for a in cact["antardashas"]:
                mk = "  (now)" if a["active"] else ""
                cadata.append([f"{cact['sign']} / {a['sign']}{mk}",
                               fmt(a["start"]), fmt(a["end"]), str(a["years"])])
            cat = Table(cadata, repeatRows=1, colWidths=[40*mm, 35*mm, 35*mm, 20*mm])
            cat.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), paper), ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8), ("TEXTCOLOR", (0, 0), (-1, -1), ink),
                ("GRID", (0, 0), (-1, -1), 0.3, line),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
            story.append(cat)

    pan = chart.get("panchang")
    if pan:
        from reportlab.platypus import PageBreak
        story.append(PageBreak())
        story.append(Paragraph("Panchang of birth", h2))
        pdata = [["Tithi", f"{pan['tithi']}"],
                 ["Vara (weekday)", f"{pan['vara']} · ruled by {pan.get('vara_lord', '—')}"],
                 ["Nakshatra", f"{pan['nakshatra']} · ruled by {pan.get('nakshatra_lord', '—')}"],
                 ["Yoga", pan["yoga"]],
                 ["Karana", pan["karana"]]]
        pt = Table(pdata, colWidths=[42 * mm, 134 * mm])
        pt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), paper), ("FONTNAME", (0, 0), (0, -1), "Times-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9), ("TEXTCOLOR", (0, 0), (-1, -1), ink),
            ("GRID", (0, 0), (-1, -1), 0.3, line),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        story.append(pt)
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
        story.append(Paragraph("Muhurta notes: " + (" ".join(notes) if notes else
                     "no Rikta tithi, Vishti karana or malefic nitya-yoga flagged."), cap))

    akv = chart.get("ashtakavarga")
    sav = akv.get("Sarva") if akv else None
    if sav:
        from reportlab.graphics.shapes import Drawing, Rect, String
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph("Sarvashtakavarga — total bindus per sign", h2))
        story.append(Paragraph("Sum of all benefic points each sign receives (~28 is average; "
                               "higher signs support transits and houses more). * marks the "
                               "Lagna sign.", cap))
        lag = chart.get("lagna_idx", 0)
        rowh, padL, bar_w = 15, 30, 320
        dw, dh = padL + bar_w + 34, 12 * rowh + 4
        d = Drawing(dw, dh)
        scale = bar_w / 45.0
        for i in range(12):
            v = sav[i]
            y = dh - (i + 1) * rowh + 4
            lbl = SIGN_ABR[i] + (" *" if i == lag else "")
            d.add(String(0, y, lbl, fontName="Helvetica", fontSize=7.5, fillColor=ink))
            cc = _GOOD if v >= 30 else _WARN if v >= 26 else _BAD
            d.add(Rect(padL, y - 1.5, max(1, v * scale), 9, fillColor=colors.HexColor(cc),
                       strokeColor=None))
            d.add(String(padL + v * scale + 4, y, str(v), fontName="Helvetica", fontSize=7.5,
                         fillColor=ink))
        story.append(d)

    sb = chart.get("shadbala")
    if sb:
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph("Shad Bala — six-fold planetary strength", h2))
        story.append(Paragraph("Strength in virupas (60 = 1 rupa). Sthana, Dig, Paksha, Vara and "
                               "Naisargika are exact; Cheshta, Ayana and the sunrise-based Kala "
                               "parts are approximated — totals are indicative, the ranking and "
                               "position-based strengths reliable.", cap))
        story.append(Spacer(1, 1.5 * mm))
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
            ("BACKGROUND", (0, 0), (-1, 0), paper), ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("TEXTCOLOR", (0, 0), (-1, -1), ink),
            ("GRID", (0, 0), (-1, -1), 0.3, line), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
        story.append(sbt)
        story.append(Paragraph(f"Strongest: {sb['order'][0]} ({P[sb['order'][0]]['rupa']:g} "
                               f"rupas) · weakest: {sb['order'][-1]} "
                               f"({P[sb['order'][-1]]['rupa']:g} rupas).", cap))

        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph("Ishta &amp; Kashta Phala — benefic vs difficult yield "
                               "(sqrt of Uccha &amp; Cheshta balas; 0–60 each).", cap))
        idata = [["Planet"] + sb["order"]]
        idata.append(["Ishta (good)"] + [f"{P[p].get('ishta', 0):g}" for p in sb["order"]])
        idata.append(["Kashta (hard)"] + [f"{P[p].get('kashta', 0):g}" for p in sb["order"]])
        it = Table(idata, colWidths=[26 * mm] + [(176 - 26) / 7 * mm] * 7)
        it.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), paper), ("FONTNAME", (0, 0), (0, -1), "Times-Bold"),
            ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("TEXTCOLOR", (0, 0), (-1, -1), ink),
            ("GRID", (0, 0), (-1, -1), 0.3, line), ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
        story.append(it)

    bb = chart.get("bhavabala")
    if bb:
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph("Bhava Bala — house strengths", h2))
        story.append(Paragraph("Per house: the house-lord's Shad Bala (Bhavadhipati) + Bhava Dig "
                               "Bala (sign type) + Bhava Drishti Bala (net aspects). Dig and "
                               "Drishti are approximated. Higher rupas = a more capable house.",
                               cap))
        story.append(Spacer(1, 1.5 * mm))
        H = bb["houses"]
        hd = [["House", "Sign", "Lord", "Adhipati", "Dig", "Drishti", "Rupas"]]
        for h in range(1, 13):
            d = H[h]
            hd.append([f"H{h}", d["sign"], d["lord"], f"{d['adhipati']:g}", f"{d['dig']:g}",
                       f"{d['drishti']:g}", f"{d['rupa']:g}"])
        bht = Table(hd, repeatRows=1,
                    colWidths=[16 * mm, 26 * mm, 24 * mm, 24 * mm, 18 * mm, 20 * mm, 18 * mm])
        bht.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), paper), ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("TEXTCOLOR", (0, 0), (-1, -1), ink),
            ("GRID", (0, 0), (-1, -1), 0.3, line), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (3, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.3), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.3)]))
        story.append(bht)
        bo = bb["order"]
        story.append(Paragraph(f"Strongest house: H{bo[0]} ({H[bo[0]]['sign']}, "
                               f"{H[bo[0]]['rupa']:g} rupas) · weakest: H{bo[-1]} "
                               f"({H[bo[-1]]['sign']}, {H[bo[-1]]['rupa']:g} rupas).", cap))

    yogas = chart.get("yogas")
    if yogas:
        from reportlab.platypus import PageBreak
        story.append(PageBreak())
        story.append(Paragraph("Yogas — planetary combinations", h2))
        story.append(Paragraph(
            f"{len(yogas)} yoga(s) read from the natal D1 (whole-sign houses, graha drishti). "
            "Conventions vary by school — a study aid, not a verdict.", cap))
        story.append(Spacer(1, 1.5 * mm))
        _YG = ["Pancha Mahapurusha", "Raja", "Dhana", "Vipareeta Raja", "Sun", "Moon", "Other"]
        _yorder = {g: i for i, g in enumerate(_YG)}
        yd = [["Group", "Yoga", "Planets", "What it means"]]
        for y in sorted(yogas, key=lambda y: _yorder.get(y["group"], 99)):
            yd.append([Paragraph(y["group"], small), Paragraph(y["name"], small),
                       Paragraph(", ".join(y["planets"]), small),
                       Paragraph(y["detail"], small)])
        yt = Table(yd, repeatRows=1, colWidths=[28 * mm, 30 * mm, 26 * mm, 92 * mm])
        yt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), paper), ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8), ("TEXTCOLOR", (0, 0), (-1, -1), ink),
            ("GRID", (0, 0), (-1, -1), 0.3, line), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
        story.append(yt)

    if compat:
        from reportlab.platypus import PageBreak
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
            ("BACKGROUND", (0, 0), (-1, 0), paper), ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8), ("TEXTCOLOR", (0, 0), (-1, -1), ink),
            ("GRID", (0, 0), (-1, -1), 0.3, line), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
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

    # ── eclipses (static precomputed DB — same source as the web view) ─────────
    try:
        import eclipse_db as _ecl
    except Exception:
        _ecl = None
    if _ecl and _ecl.available():
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
        if _years:
            from reportlab.platypus import PageBreak
            story.append(PageBreak())
            story.append(Paragraph("Finsternisse (Sonnen- &amp; Mondfinsternisse)", h2))
            story.append(Paragraph(
                "Siderische Positionen (Lahiri-Ayanamsha) der verfinsterten Lichter — "
                "Sonne bei Sonnen-, Mond bei Mondfinsternissen. Sichtbarkeit bezogen auf "
                f"{_em.get('observer', '—')}. Die vollständige Tabelle {_y0}–{_y1} "
                "steht in der interaktiven Ansicht.", cap))
            _grp = _ecl.by_year()
            for _title, _ys in _years:
                story.append(Spacer(1, 2 * mm))
                story.append(Paragraph(_title, ParagraphStyle(
                    "eh", parent=h2, fontSize=10.5, spaceBefore=6, spaceAfter=2)))
                ed = [["Datum", "Zeit (UT)", "Art", "Typ", "Zeichen", "Grad",
                       "Nakshatra", "Sichtbar"]]
                for _y in _ys:
                    for e in _grp.get(_y, []):
                        _kind = ("Sonnenfinsternis" if e["kind"] == "solar"
                                 else "Mondfinsternis")
                        _vis = e.get("visible_wadenswil")
                        _vtxt = ("ja" if _vis is True else
                                 "nein" if _vis is False else "—")
                        ed.append([f"{e['day']:02d}.{e['month']:02d}.{e['year']}",
                                   e.get("time_ut", ""), _kind, e.get("type", ""),
                                   e.get("sign", ""), e.get("deg_str", ""),
                                   f"{e.get('nakshatra', '')} P{e.get('pada', '')}",
                                   _vtxt])
                et = Table(ed, repeatRows=1,
                           colWidths=[19*mm, 16*mm, 32*mm, 17*mm, 20*mm, 17*mm,
                                      40*mm, 15*mm])
                et.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), paper),
                    ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                    ("TEXTCOLOR", (0, 0), (-1, -1), ink),
                    ("GRID", (0, 0), (-1, -1), 0.3, line),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 2.2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2)]))
                story.append(et)
            story.append(Paragraph(
                "Finsternisse nahe natalen Planeten oder dem Lagna (±2–3°) gelten "
                "klassisch als besonders wirksam.", cap))

    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("AstroVeda · reports.astroveda.ch · zur Studie und persönlichen Reflexion.", cap))

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=14*mm, rightMargin=14*mm,
                            topMargin=12*mm, bottomMargin=12*mm,
                            title="Vedic Birth Chart")
    doc.build(story)
    return buf.getvalue()

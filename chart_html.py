"""
chart_html.py — renders a computed Jyotiṣa chart as a beautiful dark HTML page.

Usage:
    import chart_html
    html_str = chart_html.build_html(chart, interpretation="## Aszendent…")
"""
from __future__ import annotations
import json, re
from typing import Dict, Optional

SIGNS = ["Aries","Taurus","Gemini","Cancer","Leo","Virgo",
         "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"]
SIGN_ABR = ["Ari","Tau","Gem","Can","Leo","Vir","Lib","Sco","Sag","Cap","Aqu","Pis"]
PLANET_ORDER = ["Sun","Moon","Mars","Mercury","Jupiter","Venus","Saturn","Rahu","Ketu"]
PLANET_ABR   = {"Sun":"Su","Moon":"Mo","Mars":"Ma","Mercury":"Me",
                "Jupiter":"Ju","Venus":"Ve","Saturn":"Sa","Rahu":"Ra","Ketu":"Ke"}
PLANET_ICON  = {"Sun":"☉","Moon":"☽","Mars":"♂","Mercury":"☿","Jupiter":"♃",
                "Venus":"♀","Saturn":"♄","Rahu":"☊","Ketu":"☋"}
SIGN_ICON    = ["♈","♉","♊","♋","♌","♍","♎","♏","♐","♑","♒","♓"]

# North Indian diamond chart: fixed sign positions (Aries top-centre, clockwise)
# Cell layout 4×4, centre cells (1,1),(1,2),(2,1),(2,2) are the diamond interior
# Each of the 12 border cells maps to a zodiac sign (0=Aries … 11=Pisces)
_NI_SIGN_POS = {
    0:(0,1), 1:(0,2), 2:(0,3),   # Aries(top-mid-L), Taurus, Gemini
    3:(1,3), 4:(2,3), 5:(3,3),   # Cancer, Leo, Virgo (right col)
    6:(3,2), 7:(3,1), 8:(3,0),   # Libra, Scorpio, Sagittarius (bottom)
    9:(2,0), 10:(1,0), 11:(0,0), # Capricorn, Aquarius, Pisces (left col)
}
# Polygon points for each of the 12 triangular/trapezoidal cells in the diamond SVG
# Coordinates are within a 400×400 viewBox
_W = 400
_C = _W // 2  # 200 – centre
_NI_POLY = {
    0:  f"{_C},0 {_C-80},{_C-80} {_C+80},{_C-80}",                         # Aries   top
    1:  f"{_W},0 {_C+80},{_C-80} {_C},0",                                   # Taurus  top-right
    2:  f"{_W},0 {_C+80},{_C-80} {_W},{_C-80}",                             # Gemini  right-top
    3:  f"{_W},{_C-80} {_C+80},{_C-80} {_C+80},{_C+80} {_W},{_C+80}",       # Cancer  right
    4:  f"{_W},{_C+80} {_C+80},{_C+80} {_W},{_W}",                          # Leo     right-bot
    5:  f"{_W},{_W} {_C+80},{_C+80} {_C},{_W}",                             # Virgo   bot-right
    6:  f"{_C},{_W} {_C+80},{_C+80} {_C-80},{_C+80}",                       # Libra   bottom
    7:  f"{_C},{_W} {_C-80},{_C+80} 0,{_W}",                                # Scorpio bot-left
    8:  f"0,{_W} {_C-80},{_C+80} 0,{_C+80}",                                # Sag     left-bot
    9:  f"0,{_C+80} {_C-80},{_C+80} {_C-80},{_C-80} 0,{_C-80}",             # Cap     left
    10: f"0,0 {_C-80},{_C-80} 0,{_C-80}",                                   # Aqu     left-top
    11: f"0,0 {_C-80},{_C-80} {_C},0",                                       # Pisces  top-left
}

# Label centres for each cell
_NI_LABEL = {
    0:  (_C, 60),
    1:  (_W-48, 48),
    2:  (_W-32, _C-110),
    3:  (_W-32, _C),
    4:  (_W-48, _W-48),
    5:  (_C+90, _W-32),
    6:  (_C, _W-60),
    7:  (48, _W-48),
    8:  (32, _C+110),
    9:  (32, _C),
    10: (48, 48),
    11: (_C-90, 32),
}


def _ni_chart_svg(lagna_idx: int, planets: Dict, divisional_si: Dict = None,
                  title: str = "Rāśi · D-1", size: int = 400) -> str:
    """Build a North Indian diamond chart as inline SVG."""
    # Which planets are in which sign index
    sign_planets: Dict[int, list] = {i: [] for i in range(12)}
    src = divisional_si if divisional_si else {}

    if divisional_si:
        for pname, si in divisional_si.items():
            if pname == "Ascendant":
                continue
            sign_planets[si % 12].append(pname)
    else:
        for pname, pd in planets.items():
            if pname == "Ascendant":
                continue
            sign_planets[pd["sign_idx"]].append(pname)

    # Rotate: in North Indian the Lagna sign is always at top (sign 0 position)
    # signs are FIXED in North Indian style — Aries always top. Lagna shown with ASC marker.

    cells = []
    for si in range(12):
        pts  = _NI_POLY[si]
        lx, ly = _NI_LABEL[si]
        is_lagna = (si == lagna_idx)
        fill = "rgba(253,243,220,0.13)" if is_lagna else "rgba(255,255,255,0.03)"
        stroke = "#c9a84c" if is_lagna else "#3a3a6a"
        sw = "1.5" if is_lagna else "0.8"

        # Sign label
        abr = SIGN_ABR[si]
        sign_label = f'<text x="{lx}" y="{ly-14}" text-anchor="middle" font-size="9" fill="#8888bb" font-family="serif">{abr}</text>'

        # Planet abbreviations
        plist = sign_planets[si]
        planet_lines = []
        for i, pname in enumerate(plist):
            abr_p = PLANET_ABR.get(pname, pname[:2])
            color = "#f5e6a3" if pname in ("Sun","Moon","Mars","Jupiter") else "#a8d4ff"
            if pname in ("Rahu","Ketu"):
                color = "#cc99ff"
            planet_lines.append(
                f'<text x="{lx}" y="{ly + i*13}" text-anchor="middle" font-size="11" '
                f'font-weight="bold" fill="{color}" font-family="serif">{abr_p}</text>'
            )

        # Lagna marker
        asc_txt = ""
        if is_lagna:
            asc_txt = f'<text x="{lx}" y="{ly-26}" text-anchor="middle" font-size="8" fill="#c9a84c" font-family="serif">Asc</text>'

        cells.append(
            f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'
            + sign_label + asc_txt + "".join(planet_lines)
        )

    title_txt = f'<text x="200" y="218" text-anchor="middle" font-size="11" fill="#9999cc" font-family="serif" font-style="italic">{title}</text>'

    return (
        f'<svg viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;max-width:{size}px">'
        + "".join(cells) + title_txt +
        "</svg>"
    )


def _markdown_to_html(text: str) -> str:
    """Minimal Markdown → HTML: ## headings, **bold**, *italic*, bullet lists."""
    lines = text.split("\n")
    out = []
    in_list = False
    for raw in lines:
        ln = raw.rstrip()
        if not ln:
            if in_list:
                out.append("</ul>"); in_list = False
            out.append("<br>")
            continue
        # headings
        m = re.match(r'^(#{1,3})\s+(.*)', ln)
        if m:
            if in_list: out.append("</ul>"); in_list = False
            lvl = len(m.group(1)) + 1  # ## → h3
            content = _inline_md(m.group(2))
            out.append(f"<h{lvl} class='reading-h'>{content}</h{lvl}>")
            continue
        # bullet
        m2 = re.match(r'^[-*•]\s+(.*)', ln)
        if m2:
            if not in_list:
                out.append("<ul class='reading-list'>"); in_list = True
            out.append(f"<li>{_inline_md(m2.group(1))}</li>")
            continue
        if in_list: out.append("</ul>"); in_list = False
        out.append(f"<p class='reading-p'>{_inline_md(ln)}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def _inline_md(s: str) -> str:
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', s)
    return s


def build_html(chart: Dict, interpretation: Optional[str] = None,
               interpretation_title: str = "Persönliche Deutung") -> str:
    m   = chart["meta"]
    pls = chart["planets"]
    li  = chart["lagna_idx"]

    # ── Rāśi SVG ──────────────────────────────────────────────────────────────
    rasi_svg = _ni_chart_svg(li, pls, title="Rāśi · D-1")

    # D9 SVG
    d9_raw = chart.get("d9", {})
    d9_li  = d9_raw.get("Ascendant", li) if isinstance(d9_raw.get("Ascendant"), int) else li
    d9_si  = {p: v for p, v in d9_raw.items() if p != "Ascendant"}
    d9_svg = _ni_chart_svg(d9_li, pls, divisional_si=d9_si, title="Navāṃśa · D-9")

    d10_raw = chart.get("d10", {})
    d10_li  = d10_raw.get("Ascendant", li) if isinstance(d10_raw.get("Ascendant"), int) else li
    d10_si  = {p: v for p, v in d10_raw.items() if p != "Ascendant"}
    d10_svg = _ni_chart_svg(d10_li, pls, divisional_si=d10_si, title="Daśāṃśa · D-10")

    # ── Planet table rows ──────────────────────────────────────────────────────
    planet_rows = ""
    for pname in PLANET_ORDER:
        pd = pls.get(pname, {})
        icon  = PLANET_ICON.get(pname, "")
        si    = pd.get("sign_idx", 0)
        sig   = SIGN_ICON[si] + " " + pd.get("sign","—")
        dignity = pd.get("dignity","—")
        dcls = ("dig-exalted" if "Exalt" in dignity
                else "dig-debil" if "Debil" in dignity
                else "dig-own" if "Own" in dignity or "Moola" in dignity
                else "")
        planet_rows += f"""
        <tr>
          <td><span class="planet-icon">{icon}</span> <strong>{pname}</strong></td>
          <td>{sig}</td>
          <td>{pd.get("pos","—")}</td>
          <td>{pd.get("house","—")}</td>
          <td>{pd.get("nakshatra","—")}</td>
          <td>{pd.get("pada","—")}</td>
          <td>{pd.get("nak_lord","—")}</td>
          <td><span class="dignity {dcls}">{dignity}</span></td>
        </tr>"""

    # ── House table rows ───────────────────────────────────────────────────────
    from astro_engine import SIGN_LORDS
    house_rows = ""
    for h in range(1, 13):
        sn  = chart["houses"][h]
        occ = ", ".join(chart["occupants"].get(h, [])) or "—"
        house_rows += f"<tr><td>{h}</td><td>{SIGN_ICON[SIGNS.index(sn)]} {sn}</td><td>{SIGN_LORDS[sn]}</td><td>{occ}</td></tr>"

    # ── Dashas ────────────────────────────────────────────────────────────────
    dashas = chart.get("dashas", {})
    cur    = dashas.get("current", {})
    dasha_html = f"""
    <div class="dasha-current">
      <div class="dasha-label">Mahādaśā</div><div class="dasha-val">{cur.get('maha','—')}</div>
      <div class="dasha-label">Antaradaśā</div><div class="dasha-val">{cur.get('antar','—')}</div>
      <div class="dasha-label">Pratyantardaśā</div><div class="dasha-val">{cur.get('pratyantar','—')}</div>
    </div>"""

    mahadashas = dashas.get("mahadashas", [])
    dasha_rows = ""
    for md in mahadashas:
        active = md.get("active", False)
        cls = " active-dasha" if active else ""
        dasha_rows += f"<tr class='{cls}'><td>{md.get('planet','')}</td><td>{md.get('start','')}</td><td>{md.get('end','')}</td><td>{md.get('years','')} yrs</td></tr>"

    # ── Yogas ─────────────────────────────────────────────────────────────────
    yogas = chart.get("yogas", [])
    yoga_html = ""
    for y in yogas:
        yoga_html += f"<div class='yoga-card'><span class='yoga-name'>{y.get('name','')}</span><span class='yoga-detail'>{y.get('detail','')}</span></div>"
    if not yoga_html:
        yoga_html = "<p style='color:#7777aa'>No notable yogas detected.</p>"

    # ── Ashtakavarga ──────────────────────────────────────────────────────────
    akv = chart.get("ashtakavarga", {})
    akv_planets = ["Sun","Moon","Mars","Mercury","Jupiter","Venus","Saturn"]
    akv_header = "<tr><th>Sign</th>" + "".join(f"<th>{PLANET_ABR[p]}</th>" for p in akv_planets) + "<th>Sarva</th></tr>"
    akv_rows = ""
    sarva = akv.get("sarva", {})
    for si in range(12):
        sn = SIGNS[si]
        cells_akv = ""
        for p in akv_planets:
            val = akv.get(p, {}).get(sn, "—")
            cls = " akv-high" if isinstance(val, int) and val >= 5 else (" akv-low" if isinstance(val, int) and val <= 2 else "")
            cells_akv += f"<td class='{cls}'>{val}</td>"
        sarva_val = sarva.get(sn, "—")
        akv_rows += f"<tr><td>{SIGN_ABR[si]}</td>{cells_akv}<td><strong>{sarva_val}</strong></td></tr>"

    # ── Panchang ──────────────────────────────────────────────────────────────
    pan = chart.get("panchang", {})
    panchang_html = ""
    if pan:
        panchang_html = f"""
        <div class="panchang-grid">
          <div class="pan-item"><span class="pan-label">Tithi</span><span class="pan-val">{pan.get('tithi','—')} (day {pan.get('tithi_num','—')})</span></div>
          <div class="pan-item"><span class="pan-label">Vara</span><span class="pan-val">{pan.get('vara','—')} · lord {pan.get('vara_lord','—')}</span></div>
          <div class="pan-item"><span class="pan-label">Nakshatra</span><span class="pan-val">{pan.get('nakshatra','—')} · lord {pan.get('nakshatra_lord','—')}</span></div>
          <div class="pan-item"><span class="pan-label">Yoga</span><span class="pan-val">{pan.get('yoga','—')}</span></div>
          <div class="pan-item"><span class="pan-label">Karaṇa</span><span class="pan-val">{pan.get('karana','—')}</span></div>
        </div>"""

    # ── AI Reading ────────────────────────────────────────────────────────────
    reading_html = ""
    if interpretation and interpretation.strip():
        reading_html = _markdown_to_html(interpretation)

    # ── Transits ──────────────────────────────────────────────────────────────
    transits = chart.get("transits", {})
    transit_rows = ""
    for pname in PLANET_ORDER:
        td = transits.get(pname, {})
        natal_pd = pls.get(pname, {})
        icon = PLANET_ICON.get(pname, "")
        si = td.get("sign_idx", 0)
        transit_rows += f"""
        <tr>
          <td><span class="planet-icon">{icon}</span> {pname}</td>
          <td>{SIGN_ICON[si]} {td.get('sign','—')}</td>
          <td>{td.get('pos','—')}</td>
          <td>{td.get('nakshatra','—')}</td>
          <td>{natal_pd.get('sign','—')}</td>
        </tr>"""

    # ── Full HTML ──────────────────────────────────────────────────────────────
    name_g = f"{m.get('name','')}" + (f" ({m['gender']})" if m.get("gender") else "")

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vedic Chart · {m.get('name','')}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,600;1,400&family=Inter:wght@300;400;500&display=swap" rel="stylesheet">
<style>
:root {{
  --bg:      #0d0d1f;
  --bg2:     #13132a;
  --bg3:     #1a1a35;
  --accent:  #c9a84c;
  --accent2: #7b6fff;
  --text:    #e8e4f0;
  --muted:   #8888bb;
  --border:  #2a2a4a;
  --good:    #4caf7d;
  --warn:    #c9a84c;
  --bad:     #e05c5c;
}}
* {{ box-sizing:border-box; margin:0; padding:0 }}
body {{ background:var(--bg); color:var(--text); font-family:'Inter',sans-serif;
        font-size:14px; line-height:1.6; min-height:100vh }}

/* Stars background */
body::before {{
  content:''; position:fixed; inset:0; z-index:-1;
  background: radial-gradient(ellipse at 20% 30%, rgba(123,111,255,0.06) 0%, transparent 60%),
              radial-gradient(ellipse at 80% 70%, rgba(201,168,76,0.04) 0%, transparent 50%),
              var(--bg);
}}

.page-wrap {{ max-width:1100px; margin:0 auto; padding:24px 20px 60px }}

/* Header */
.chart-header {{ text-align:center; padding:40px 0 32px; border-bottom:1px solid var(--border) }}
.chart-header h1 {{ font-family:'Cormorant Garamond',serif; font-size:2.2rem;
                    color:var(--accent); letter-spacing:.05em }}
.chart-header .subtitle {{ color:var(--muted); font-size:.85rem; margin-top:4px; letter-spacing:.1em; text-transform:uppercase }}
.meta-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
              gap:8px; margin-top:24px; text-align:left }}
.meta-item {{ background:var(--bg2); border:1px solid var(--border); border-radius:8px;
              padding:10px 14px }}
.meta-label {{ color:var(--muted); font-size:.75rem; text-transform:uppercase; letter-spacing:.08em }}
.meta-val   {{ color:var(--text); font-size:.95rem; margin-top:2px }}
.lagna-badge {{ display:inline-block; background:rgba(201,168,76,.15); color:var(--accent);
                border:1px solid rgba(201,168,76,.3); border-radius:20px;
                padding:2px 12px; font-size:.85rem; margin-top:6px }}

/* Tabs */
.tabs {{ display:flex; gap:4px; margin:32px 0 0; border-bottom:1px solid var(--border);
         overflow-x:auto; scrollbar-width:none }}
.tabs::-webkit-scrollbar {{ display:none }}
.tab-btn {{ padding:10px 18px; background:none; border:none; border-bottom:2px solid transparent;
            color:var(--muted); cursor:pointer; font-size:.85rem; white-space:nowrap;
            font-family:'Inter',sans-serif; transition:.2s }}
.tab-btn:hover {{ color:var(--text) }}
.tab-btn.active {{ color:var(--accent); border-bottom-color:var(--accent) }}
.tab-panel {{ display:none; padding:28px 0 }}
.tab-panel.active {{ display:block }}

/* Charts grid */
.charts-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:24px; margin-bottom:32px }}
.chart-card {{ background:var(--bg2); border:1px solid var(--border); border-radius:12px;
               padding:20px; text-align:center }}
.chart-card h3 {{ font-family:'Cormorant Garamond',serif; color:var(--accent);
                  font-size:1rem; margin-bottom:12px; letter-spacing:.05em }}

/* Tables */
.data-table {{ width:100%; border-collapse:collapse; font-size:.82rem }}
.data-table th {{ background:var(--bg3); color:var(--muted); font-weight:500;
                  text-transform:uppercase; font-size:.72rem; letter-spacing:.08em;
                  padding:10px 12px; text-align:left; border-bottom:1px solid var(--border) }}
.data-table td {{ padding:9px 12px; border-bottom:1px solid rgba(255,255,255,.04); vertical-align:middle }}
.data-table tr:hover td {{ background:rgba(255,255,255,.02) }}
.planet-icon {{ font-size:1.1rem; margin-right:4px }}
.dignity {{ padding:2px 8px; border-radius:10px; font-size:.76rem; font-weight:500 }}
.dig-exalted {{ background:rgba(76,175,125,.15); color:var(--good) }}
.dig-debil   {{ background:rgba(224,92,92,.12);  color:var(--bad) }}
.dig-own     {{ background:rgba(201,168,76,.12); color:var(--accent) }}

/* Dasha */
.dasha-current {{ display:grid; grid-template-columns:auto 1fr; gap:6px 16px;
                  background:var(--bg2); border:1px solid var(--border); border-radius:10px;
                  padding:18px 22px; margin-bottom:24px; max-width:400px }}
.dasha-label {{ color:var(--muted); font-size:.78rem; text-transform:uppercase; letter-spacing:.07em; align-self:center }}
.dasha-val   {{ color:var(--accent); font-size:1rem; font-family:'Cormorant Garamond',serif; font-weight:600 }}
.active-dasha td {{ color:var(--accent) }}
.active-dasha {{ background:rgba(201,168,76,.06) }}

/* Yogas */
.yoga-card {{ background:var(--bg2); border:1px solid var(--border); border-radius:8px;
              padding:12px 16px; margin-bottom:10px }}
.yoga-name   {{ color:var(--accent); font-family:'Cormorant Garamond',serif; font-size:1rem;
                font-weight:600; display:block; margin-bottom:4px }}
.yoga-detail {{ color:var(--muted); font-size:.82rem }}

/* Ashtakavarga */
.akv-high {{ color:var(--good); font-weight:600 }}
.akv-low  {{ color:var(--bad) }}

/* Panchang */
.panchang-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px }}
.pan-item  {{ background:var(--bg2); border:1px solid var(--border); border-radius:8px; padding:12px 16px }}
.pan-label {{ color:var(--muted); font-size:.75rem; text-transform:uppercase; letter-spacing:.07em; display:block }}
.pan-val   {{ color:var(--text); font-size:.95rem; margin-top:4px; display:block }}

/* Reading */
.reading-wrap {{ max-width:720px }}
.reading-h  {{ font-family:'Cormorant Garamond',serif; color:var(--accent);
               font-size:1.35rem; margin:28px 0 10px; display:flex; align-items:center; gap:10px }}
.reading-h::before {{ content:'—'; color:rgba(201,168,76,.5) }}
.reading-p  {{ color:var(--text); line-height:1.8; margin-bottom:14px; font-size:.92rem }}
.reading-list {{ padding-left:20px; margin-bottom:14px }}
.reading-list li {{ color:var(--text); line-height:1.7; font-size:.92rem; margin-bottom:6px }}
.reading-disclaimer {{ color:var(--muted); font-size:.78rem; font-style:italic;
                       border-top:1px solid var(--border); margin-top:32px; padding-top:16px }}

/* Section header */
.sec-head {{ font-family:'Cormorant Garamond',serif; color:var(--muted);
             font-size:.75rem; text-transform:uppercase; letter-spacing:.12em;
             margin-bottom:16px }}

/* Download bar */
.dl-bar {{ display:flex; gap:12px; margin:24px 0 32px; flex-wrap:wrap }}
.dl-btn {{ display:inline-flex; align-items:center; gap:8px; padding:10px 20px;
           border-radius:8px; font-size:.85rem; font-weight:500; cursor:pointer;
           text-decoration:none; transition:.2s; border:none }}
.dl-primary {{ background:var(--accent); color:#0d0d1f }}
.dl-primary:hover {{ background:#d4b560 }}
.dl-secondary {{ background:var(--bg2); color:var(--text); border:1px solid var(--border) }}
.dl-secondary:hover {{ border-color:var(--accent); color:var(--accent) }}
</style>
</head>
<body>
<div class="page-wrap">

  <!-- Header -->
  <div class="chart-header">
    <div class="subtitle">✦ Jyotiṣa · Lahiri Ayanamsha · Whole-Sign Houses ✦</div>
    <h1>{name_g or 'Vedic Birth Chart'}</h1>
    <div class="meta-grid">
      <div class="meta-item">
        <div class="meta-label">Birth</div>
        <div class="meta-val">{m.get('birth','')} <span style="color:var(--muted)">({m.get('tz','')})</span></div>
      </div>
      <div class="meta-item">
        <div class="meta-label">Location</div>
        <div class="meta-val">{m.get('location','—')}</div>
      </div>
      <div class="meta-item">
        <div class="meta-label">Lagna</div>
        <div class="meta-val">
          <span class="lagna-badge">{chart.get('lagna','')} {chart.get('lagna_pos','')}</span>
        </div>
      </div>
      <div class="meta-item">
        <div class="meta-label">Ayanamsha · Engine</div>
        <div class="meta-val">{m.get('ayan','')}° Lahiri</div>
        <div style="color:var(--muted);font-size:.75rem;margin-top:2px">{m.get('engine','')}</div>
      </div>
    </div>
  </div>

  <!-- Download bar -->
  <div class="dl-bar">
    <a class="dl-btn dl-secondary" href="javascript:window.print()">⬇ Print / Save as PDF</a>
  </div>

  <!-- Tabs -->
  <div class="tabs">
    <button class="tab-btn active" onclick="showTab('reading',this)">Reading</button>
    <button class="tab-btn" onclick="showTab('chart',this)">Chart</button>
    <button class="tab-btn" onclick="showTab('planets',this)">Planets &amp; Houses</button>
    <button class="tab-btn" onclick="showTab('divisional',this)">Divisional</button>
    <button class="tab-btn" onclick="showTab('dasha',this)">Viṃśottarī</button>
    <button class="tab-btn" onclick="showTab('ashtaka',this)">Ashtakavarga</button>
    <button class="tab-btn" onclick="showTab('panchang',this)">Pañcāṅga</button>
    <button class="tab-btn" onclick="showTab('yogas',this)">Yogas</button>
    <button class="tab-btn" onclick="showTab('transits',this)">Transits</button>
  </div>

  <!-- Tab: Reading -->
  <div class="tab-panel active" id="tab-reading">
    {'<div class="reading-wrap">' + reading_html + '<p class="reading-disclaimer">This report was AI-generated from precisely computed chart data and is intended for personal reflection only.</p></div>' if reading_html else '<p style="color:var(--muted);padding:32px 0">No AI reading available for this chart.</p>'}
  </div>

  <!-- Tab: Chart -->
  <div class="tab-panel" id="tab-chart">
    <div class="charts-grid">
      <div class="chart-card">
        <h3>Rāśi · D-1 (Natal)</h3>
        {rasi_svg}
      </div>
    </div>
  </div>

  <!-- Tab: Planets & Houses -->
  <div class="tab-panel" id="tab-planets">
    <p class="sec-head">Grahas</p>
    <div style="overflow-x:auto">
    <table class="data-table">
      <thead><tr>
        <th>Planet</th><th>Sign</th><th>Position</th><th>H</th>
        <th>Nakshatra</th><th>Pada</th><th>Lord</th><th>Dignity</th>
      </tr></thead>
      <tbody>{planet_rows}</tbody>
    </table>
    </div>
    <br>
    <p class="sec-head">Bhavas (Houses)</p>
    <div style="overflow-x:auto">
    <table class="data-table">
      <thead><tr><th>H</th><th>Sign</th><th>Lord</th><th>Occupants</th></tr></thead>
      <tbody>{house_rows}</tbody>
    </table>
    </div>
  </div>

  <!-- Tab: Divisional -->
  <div class="tab-panel" id="tab-divisional">
    <div class="charts-grid">
      <div class="chart-card">
        <h3>Navāṃśa · D-9</h3>
        {d9_svg}
      </div>
      <div class="chart-card">
        <h3>Daśāṃśa · D-10</h3>
        {d10_svg}
      </div>
    </div>
  </div>

  <!-- Tab: Vimsottari Dasha -->
  <div class="tab-panel" id="tab-dasha">
    <p class="sec-head">Current Period</p>
    {dasha_html}
    <p class="sec-head">Mahādaśā Timeline</p>
    <div style="overflow-x:auto">
    <table class="data-table">
      <thead><tr><th>Planet</th><th>Start</th><th>End</th><th>Duration</th></tr></thead>
      <tbody>{dasha_rows}</tbody>
    </table>
    </div>
  </div>

  <!-- Tab: Ashtakavarga -->
  <div class="tab-panel" id="tab-ashtaka">
    <p class="sec-head">Bindus per Sign — ≥5 strong · ≤2 weak</p>
    <div style="overflow-x:auto">
    <table class="data-table">
      <thead>{akv_header}</thead>
      <tbody>{akv_rows}</tbody>
    </table>
    </div>
  </div>

  <!-- Tab: Panchang -->
  <div class="tab-panel" id="tab-panchang">
    <p class="sec-head">Pañcāṅga at Birth</p>
    {panchang_html}
  </div>

  <!-- Tab: Yogas -->
  <div class="tab-panel" id="tab-yogas">
    <p class="sec-head">Active Yogas</p>
    {yoga_html}
  </div>

  <!-- Tab: Transits -->
  <div class="tab-panel" id="tab-transits">
    <p class="sec-head">Current Transits vs Natal — {chart.get('transit_local','today')}</p>
    <div style="overflow-x:auto">
    <table class="data-table">
      <thead><tr><th>Planet</th><th>Transit Sign</th><th>Position</th><th>Nakshatra</th><th>Natal Sign</th></tr></thead>
      <tbody>{transit_rows}</tbody>
    </table>
    </div>
  </div>

</div><!-- /page-wrap -->

<script>
function showTab(id, btn) {{
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + id).classList.add('active');
  btn.classList.add('active');
}}
</script>
</body>
</html>"""

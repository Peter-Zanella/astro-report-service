"""
chart_html.py — vollständige interaktive HTML-Ansicht eines Jyotiṣa-Charts.
Entspricht dem PDF-Inhalt 1:1, plus Nord/Süd-Toggle und Tabs.
"""
from __future__ import annotations
import re
from typing import Dict, Optional

SIGNS    = ["Aries","Taurus","Gemini","Cancer","Leo","Virgo",
            "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"]
SIGN_ABR = ["Ari","Tau","Gem","Can","Leo","Vir","Lib","Sco","Sag","Cap","Aqu","Pis"]
SIGN_ICON= ["♈","♉","♊","♋","♌","♍","♎","♏","♐","♑","♒","♓"]
PLANET_ORDER = ["Sun","Moon","Mars","Mercury","Jupiter","Venus","Saturn","Rahu","Ketu"]
PLANET_ABR   = {"Sun":"Su","Moon":"Mo","Mars":"Ma","Mercury":"Me",
                "Jupiter":"Ju","Venus":"Ve","Saturn":"Sa","Rahu":"Ra","Ketu":"Ke"}
PLANET_ICON  = {"Sun":"☉","Moon":"☽","Mars":"♂","Mercury":"☿","Jupiter":"♃",
                "Venus":"♀","Saturn":"♄","Rahu":"☊","Ketu":"☋"}
CHARA_KARAKA_ABBR = {
    "Atmakaraka":"AK","Amatyakaraka":"AmK","Bhratrikaraka":"BK",
    "Matrikaraka":"MK","Pitrikaraka":"PiK","Putrakaraka":"PuK",
    "Gnatikaraka":"GK","Darakaraka":"DK",
}

# ── South Indian chart: sign→(row,col) fixed ──────────────────────────────────
_SI_CELL = {
    11:(0,0), 0:(0,1), 1:(0,2),  2:(0,3),
    10:(1,0),                     3:(1,3),
     9:(2,0),                     4:(2,3),
     8:(3,0), 7:(3,1), 6:(3,2),  5:(3,3),
}

# ── North Indian diamond chart polygons (400×400 viewBox) ────────────────────
_W=400; _C=200
_NI_POLY = {
    0: f"{_C},0 {_C-80},{_C-80} {_C+80},{_C-80}",
    1: f"{_W},0 {_C+80},{_C-80} {_C},0",
    2: f"{_W},0 {_C+80},{_C-80} {_W},{_C-80}",
    3: f"{_W},{_C-80} {_C+80},{_C-80} {_C+80},{_C+80} {_W},{_C+80}",
    4: f"{_W},{_C+80} {_C+80},{_C+80} {_W},{_W}",
    5: f"{_W},{_W} {_C+80},{_C+80} {_C},{_W}",
    6: f"{_C},{_W} {_C+80},{_C+80} {_C-80},{_C+80}",
    7: f"{_C},{_W} {_C-80},{_C+80} 0,{_W}",
    8: f"0,{_W} {_C-80},{_C+80} 0,{_C+80}",
    9: f"0,{_C+80} {_C-80},{_C+80} {_C-80},{_C-80} 0,{_C-80}",
    10:f"0,0 {_C-80},{_C-80} 0,{_C-80}",
    11:f"0,0 {_C-80},{_C-80} {_C},0",
}
_NI_LABEL = {
    0:(_C,55), 1:(_W-42,42), 2:(_W-30,_C-115),
    3:(_W-30,_C), 4:(_W-42,_W-42), 5:(_C+95,_W-30),
    6:(_C,_W-55), 7:(42,_W-42), 8:(30,_C+115),
    9:(30,_C), 10:(42,42), 11:(_C-95,30),
}


def _planet_color(pname):
    if pname in ("Sun","Moon","Jupiter","Mars"): return "#f5e6a3"
    if pname in ("Rahu","Ketu"): return "#cc99ff"
    return "#a8d4ff"


def _ni_svg(li, sign_planets, title="", size=380, planet_data=None):
    # In North Indian chart, cell position 0 = top-centre = Lagna (house 1).
    # We map each NI cell position (0-11) to the actual sign_idx by rotating
    # so that the lagna sign always lands in position 0.
    cells = []
    for pos in range(12):
        si = (li + pos) % 12          # sign that occupies NI cell 'pos'
        pts = _NI_POLY[pos]
        lx,ly = _NI_LABEL[pos]
        is_l = (pos == 0)             # position 0 is always Lagna cell
        fill = "rgba(201,168,76,0.12)" if is_l else "rgba(255,255,255,0.02)"
        stroke = "#c9a84c" if is_l else "#2e2e5a"
        sw = "1.5" if is_l else "0.7"
        abr = SIGN_ABR[si]
        house_num = pos + 1
        sl = f'<text x="{lx}" y="{ly-16}" text-anchor="middle" font-size="9" fill="#6666aa" font-family="serif">{abr}</text>'
        asc = f'<text x="{lx}" y="{ly-27}" text-anchor="middle" font-size="8" fill="#c9a84c" font-family="serif">Asc</text>' if is_l else ""
        pl_items = []
        for i,p in enumerate(sign_planets.get(si,[])):
            abbr = PLANET_ABR.get(p,p[:2])
            pd_info = planet_data.get(p,{}) if planet_data else {}
            pos_str = pd_info.get("pos","")
            deg = pos_str.split("°")[0].strip() if pos_str and "°" in pos_str else ""
            nak = pd_info.get("nakshatra","")
            nak_short = nak[:3] if nak else ""
            label = f"{abbr} {deg}°" if deg else abbr
            pl_items.append(f'<text x="{lx}" y="{ly+i*18}" text-anchor="middle" font-size="10" font-weight="bold" fill="{_planet_color(p)}" font-family="serif">{label}</text>')
            if nak_short:
                pl_items.append(f'<text x="{lx}" y="{ly+i*18+10}" text-anchor="middle" font-size="7" fill="#9999cc" font-family="serif">{nak_short}</text>')
        pl = "".join(pl_items)
        cells.append(f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>{sl}{asc}{pl}')
    tl = f'<text x="200" y="215" text-anchor="middle" font-size="10" fill="#7777aa" font-family="serif" font-style="italic">{title}</text>'
    return f'<svg viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:{size}px">'+"".join(cells)+tl+"</svg>"


def _si_svg(li, sign_planets, title="", size=380, planet_data=None):
    CW = size//4
    cells = []
    for si,(r,c) in _SI_CELL.items():
        x,y = c*CW, r*CW
        is_l = (si==li)
        fill = "rgba(201,168,76,0.12)" if is_l else "rgba(255,255,255,0.02)"
        stroke = "#c9a84c" if is_l else "#2e2e5a"
        sw = "1.5" if is_l else "0.7"
        abr = SIGN_ABR[si] + ("◆" if is_l else "")
        sl = f'<text x="{x+CW//2}" y="{y+14}" text-anchor="middle" font-size="9" fill="{("#c9a84c" if is_l else "#6666aa")}" font-family="serif">{abr}</text>'
        pl_items = []
        for i,p in enumerate(sign_planets.get(si,[])):
            abbr = PLANET_ABR.get(p,p[:2])
            pd_info = planet_data.get(p,{}) if planet_data else {}
            pos = pd_info.get("pos","")
            deg = pos.split("°")[0].strip() if pos and "°" in pos else ""
            nak = pd_info.get("nakshatra","")
            nak_short = nak[:3] if nak else ""
            label = f"{abbr} {deg}°" if deg else abbr
            pl_items.append(f'<text x="{x+CW//2}" y="{y+14+14+i*18}" text-anchor="middle" font-size="10" font-weight="bold" fill="{_planet_color(p)}" font-family="serif">{label}</text>')
            if nak_short:
                pl_items.append(f'<text x="{x+CW//2}" y="{y+14+14+i*18+10}" text-anchor="middle" font-size="7" fill="#9999cc" font-family="serif">{nak_short}</text>')
        pl = "".join(pl_items)
        cells.append(f'<rect x="{x}" y="{y}" width="{CW}" height="{CW}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>{sl}{pl}')
    tl = f'<text x="{size//2}" y="{size//2+5}" text-anchor="middle" font-size="10" fill="#7777aa" font-family="serif" font-style="italic">{title}</text>'
    return f'<svg viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:{size}px">'+"".join(cells)+tl+"</svg>"


def _chart_svgs(li, sign_planets, title, planet_data=None):
    ni = _ni_svg(li, sign_planets, title, planet_data=planet_data)
    si = _si_svg(li, sign_planets, title, planet_data=planet_data)
    return f"""
<div class="chart-toggle-wrap">
  <div class="chart-toggle">
    <button class="ctbtn active" onclick="setStyle(this,'north',this.closest('.chart-toggle-wrap'))">North</button>
    <button class="ctbtn" onclick="setStyle(this,'south',this.closest('.chart-toggle-wrap'))">South</button>
  </div>
  <div class="cv north">{ni}</div>
  <div class="cv south" style="display:none">{si}</div>
</div>"""


def _build_sign_planets(planets, divisional_si=None):
    """Returns {sign_idx: [planet_name, ...]} and planet_details for degree/nak display."""
    sp = {i:[] for i in range(12)}
    if divisional_si:
        for p,si in divisional_si.items():
            if p!="Ascendant": sp[si%12].append(p)
    else:
        for p,pd in planets.items():
            if p!="Ascendant": sp[pd["sign_idx"]].append(p)
    return sp


def _md_html(text):
    lines = text.split("\n"); out=[]; inlist=False
    for raw in lines:
        ln=raw.rstrip()
        if not ln:
            if inlist: out.append("</ul>"); inlist=False
            out.append("<br>"); continue
        m=re.match(r'^(#{1,3})\s+(.*)',ln)
        if m:
            if inlist: out.append("</ul>"); inlist=False
            lvl=len(m.group(1))+1
            out.append(f"<h{lvl} class='rh'>{_il(m.group(2))}</h{lvl}>"); continue
        m2=re.match(r'^[-*•]\s+(.*)',ln)
        if m2:
            if not inlist: out.append("<ul class='rl'>"); inlist=True
            out.append(f"<li>{_il(m2.group(1))}</li>"); continue
        if inlist: out.append("</ul>"); inlist=False
        out.append(f"<p class='rp'>{_il(ln)}</p>")
    if inlist: out.append("</ul>")
    return "\n".join(out)

def _il(s):
    s=s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    s=re.sub(r'\*\*(.+?)\*\*',r'<strong>\1</strong>',s)
    s=re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)',r'<em>\1</em>',s)
    return s


def build_html(chart:Dict, interpretation:Optional[str]=None,
               interpretation_title:str="Persönliche Deutung") -> str:
    m   = chart["meta"]
    pls = chart["planets"]
    li  = chart["lagna_idx"]

    # sign→planets for each chart
    sp_rasi   = _build_sign_planets(pls)
    sp_bhava  = {i:[] for i in range(12)}
    for p,bh in chart.get("bhava",{}).get("house",{}).items():
        si = (li+bh-1)%12; sp_bhava[si].append(p)

    d9  = chart.get("d9",{});  d9li  = d9.get("Ascendant",li)
    d3  = chart.get("d3",{});  d3li  = d3.get("Ascendant",li)
    d10 = chart.get("d10",{}); d10li = d10.get("Ascendant",li)
    sp_d9  = _build_sign_planets(pls,{p:v for p,v in d9.items()  if p!="Ascendant"})
    sp_d3  = _build_sign_planets(pls,{p:v for p,v in d3.items()  if p!="Ascendant"})
    sp_d10 = _build_sign_planets(pls,{p:v for p,v in d10.items() if p!="Ascendant"})

    # Varshaphala chart
    vp = chart.get("varshaphala",{})
    vp_li  = vp.get("lagna_idx", li)
    vp_pls = vp.get("planets",{})
    sp_vp  = _build_sign_planets(vp_pls) if vp_pls else sp_rasi

    # Transit chart (current sky vs natal lagna)
    tr_pls = chart.get("transits",{})
    tr_li  = chart.get("transit_lagna_idx", li)
    sp_tr  = _build_sign_planets(tr_pls)

    # ── Planet table ───────────────────────────────────────────────────────────
    planet_rows = ""
    for pn in PLANET_ORDER:
        pd=pls.get(pn,{})
        icon=PLANET_ICON.get(pn,"")
        si=pd.get("sign_idx",0)
        sig=SIGN_ICON[si]+" "+pd.get("sign","—")
        dig=pd.get("dignity","—")
        dcls=("dig-e" if "Exalt" in dig else "dig-d" if "Debil" in dig else "dig-o" if "Own" in dig or "Moola" in dig else "")
        bh=pd.get("bhava",""); bshift=pd.get("bhava_shift",0)
        bh_note=f" <span style='color:#8888bb;font-size:.75rem'>({'+' if bshift>0 else ''}{bshift})</span>" if bshift else ""
        planet_rows+=f"<tr><td><span class='pi'>{icon}</span><strong>{pn}</strong></td><td>{sig}</td><td>{pd.get('pos','—')}</td><td>{pd.get('house','—')}{bh_note}</td><td>{pd.get('nakshatra','—')}</td><td>{pd.get('pada','—')}</td><td>{pd.get('nak_lord','—')}</td><td><span class='dig {dcls}'>{dig}</span></td></tr>"

    # ── House table ────────────────────────────────────────────────────────────
    from astro_engine import SIGN_LORDS
    house_rows=""
    for h in range(1,13):
        sn=chart["houses"][h]
        occ=", ".join(chart["occupants"].get(h,[])) or "—"
        house_rows+=f"<tr><td>{h}</td><td>{SIGN_ICON[SIGNS.index(sn)]} {sn}</td><td>{SIGN_LORDS[sn]}</td><td>{occ}</td></tr>"

    # ── Ashtakavarga ──────────────────────────────────────────────────────────
    akv=chart.get("ashtakavarga",{})
    akv_pl=["Sun","Moon","Mars","Mercury","Jupiter","Venus","Saturn"]
    akv_hdr="<tr><th>Sign</th>"+"".join(f"<th>{PLANET_ABR[p]}</th>" for p in akv_pl)+"<th>Σ</th></tr>"
    sarva=akv.get("Sarva",[0]*12)
    akv_rows=""
    for si in range(12):
        cells=""
        for p in akv_pl:
            pl=akv.get(p,[]); v=pl[si] if si<len(pl) else "—"
            cls=" av-h" if isinstance(v,int) and v>=5 else (" av-l" if isinstance(v,int) and v<=2 else "")
            cells+=f"<td class='{cls}'>{v}</td>"
        sv=sarva[si] if si<len(sarva) else "—"
        scls=" av-h" if isinstance(sv,int) and sv>=30 else (" av-l" if isinstance(sv,int) and sv<=25 else "")
        is_l="*" if si==li else ""
        akv_rows+=f"<tr><td>{SIGN_ABR[si]}{is_l}</td>{cells}<td class='{scls}'><strong>{sv}</strong></td></tr>"

    # ── Dashas ────────────────────────────────────────────────────────────────
    dashas=chart.get("dashas",{})
    cur=dashas.get("current",{})
    dasha_cur=f"""<div class="dbox">
      <div class="dl">Mahādaśā</div><div class="dv">{cur.get('maha','—')}</div>
      <div class="dl">Antaradaśā</div><div class="dv">{cur.get('antar','—')}</div>
      <div class="dl">Pratyantardaśā</div><div class="dv">{cur.get('pratyantar','—')}</div>
    </div>"""
    maha_rows=""
    for md in dashas.get("mahadashas",[]):
        a=md.get("active",False)
        cls=" act" if a else ""
        now=" (now)" if a else ""
        s=str(md.get('start',''))[:10]; e=str(md.get('end',''))[:10]
        maha_rows+=f"<tr class='{cls}'><td>{md.get('planet','')}{now}</td><td>{s}</td><td>{e}</td><td>{md.get('years','')} yrs</td></tr>"

    antar_rows=""
    for md in dashas.get("mahadashas",[]):
        if md.get("active"):
            for ad in md.get("antardashas",[]):
                a=ad.get("active",False)
                cls=" act" if a else ""
                now=" (now)" if a else ""
                s=str(ad.get('start',''))[:10]; e=str(ad.get('end',''))[:10]
                antar_rows+=f"<tr class='{cls}'><td>{md.get('planet','')}/{ad.get('planet','')}{now}</td><td>{s}</td><td>{e}</td></tr>"

    # ── Chara Dasha ───────────────────────────────────────────────────────────
    chara=chart.get("chara_dasha",{})
    chara_cur=chara.get("current",{})
    chara_rows=""
    for rd in chara.get("mahadashas",[]):
        a=rd.get("active",False)
        cls=" act" if a else ""
        now=" (now)" if a else ""
        s=str(rd.get('start',''))[:10]; e=str(rd.get('end',''))[:10]
        chara_rows+=f"<tr class='{cls}'><td>{rd.get('sign','')}{now}</td><td>{s}</td><td>{e}</td><td>{rd.get('years','')} yrs</td></tr>"

    chara_antar_rows=""
    for rd in chara.get("mahadashas",[]):
        if rd.get("active"):
            for ad in rd.get("antardashas",[]):
                a=ad.get("active",False)
                cls=" act" if a else ""
                now=" (now)" if a else ""
                s=str(ad.get('start',''))[:10]; e=str(ad.get('end',''))[:10]
                chara_antar_rows+=f"<tr class='{cls}'><td>{rd.get('sign','')}/{ad.get('sign','')}{now}</td><td>{s}</td><td>{e}</td></tr>"

    # ── Jaimini Karakas ───────────────────────────────────────────────────────
    jai=chart.get("jaimini",{})
    jai_rows=""
    for role,abbr in CHARA_KARAKA_ABBR.items():
        kd=jai.get("karakas",{}).get(role,{})
        rev=" (rev)" if kd.get("reverse") else ""
        jai_rows+=f"<tr><td><strong>{abbr}</strong></td><td>{role}</td><td>{kd.get('planet','—')}</td><td>{kd.get('sign','—')}</td><td>{round(kd.get('deg_in_sign',0),2)}°{rev}</td><td>{round(kd.get('effective',0),2)}</td></tr>"

    jai_summary=f"""<div class="pan-grid" style="margin-top:16px">
      <div class="pi2"><span class="pl2">Atmakaraka</span><span class="pv2">{jai.get('atmakaraka','—')}</span></div>
      <div class="pi2"><span class="pl2">Darakaraka</span><span class="pv2">{jai.get('darakaraka','—')}</span></div>
      <div class="pi2"><span class="pl2">Karakamsha</span><span class="pv2">{jai.get('karakamsha','—')} (lord {jai.get('karakamsha_lord','—')})</span></div>
      <div class="pi2"><span class="pl2">Arudha Lagna</span><span class="pv2">{jai.get('arudha_lagna','—')} (lord {jai.get('arudha_lagna_lord','—')})</span></div>
      <div class="pi2"><span class="pl2">Upapada Lagna</span><span class="pv2">{jai.get('upapada_lagna','—')} (lord {jai.get('upapada_lagna_lord','—')})</span></div>
    </div>"""

    # ── Shadbala ──────────────────────────────────────────────────────────────
    sb=chart.get("shadbala",{})
    sb_rows=""
    for p in PLANET_ORDER[:7]:
        pd2=sb.get("planets",{}).get(p,{})
        strong=pd2.get("strong",False)
        scls=" sb-s" if strong else " sb-w"
        sb_rows+=f"""<tr>
          <td><span class='pi'>{PLANET_ICON.get(p,'')}</span>{p}</td>
          <td>{pd2.get('sthana','—')}</td><td>{pd2.get('dig','—')}</td>
          <td>{pd2.get('kala','—')}</td><td>{pd2.get('cheshta','—')}</td>
          <td>{pd2.get('naisargika','—')}</td><td>{pd2.get('drik','—')}</td>
          <td>{pd2.get('rupa','—')} / {pd2.get('required','—')}</td>
          <td class='{scls}'>{'strong' if strong else 'weak'}</td>
        </tr>"""

    ishta_row="".join(f"<td>{sb.get('planets',{}).get(p,{}).get('ishta','—')}</td>" for p in PLANET_ORDER[:7])
    kashta_row="".join(f"<td>{sb.get('planets',{}).get(p,{}).get('kashta','—')}</td>" for p in PLANET_ORDER[:7])

    # ── Bhavabala ─────────────────────────────────────────────────────────────
    bb=chart.get("bhavabala",{})
    bb_rows=""
    bb_order=bb.get("order",[])
    for h in range(1,13):
        hd=bb.get("houses",{}).get(h,{})
        is_str=(h==bb_order[0]) if bb_order else False
        is_wk=(h==bb_order[-1]) if bb_order else False
        cls=" sb-s" if is_str else (" sb-w" if is_wk else "")
        bb_rows+=f"<tr><td>H{h}</td><td>{chart['houses'][h]}</td><td>{SIGN_LORDS[chart['houses'][h]]}</td><td>{hd.get('adhipati','—')}</td><td>{hd.get('dig','—')}</td><td>{hd.get('drishti','—')}</td><td class='{cls}'>{hd.get('rupa','—')}</td></tr>"

    # ── Transit strength ──────────────────────────────────────────────────────
    ts_rows=""
    akv_sarva=akv.get("Sarva",[0]*12)
    for pn in PLANET_ORDER:
        npd=pls.get(pn,{}); tpd=tr_pls.get(pn,{})
        tsi=tpd.get("sign_idx",0)
        bindus=akv_sarva[tsi] if tsi<len(akv_sarva) else "—"
        str_cls=""
        if isinstance(bindus,int):
            str_cls="av-h" if bindus>=30 else ("av-l" if bindus<=25 else "av-m")
        ts_rows+=f"<tr><td><span class='pi'>{PLANET_ICON.get(pn,'')}</span>{pn}</td><td>{npd.get('sign','—')}</td><td>{SIGN_ICON[tsi]} {tpd.get('sign','—')}</td><td>{tpd.get('pos','—')}</td><td>{tpd.get('nakshatra','—')}</td><td class='{str_cls}'>{bindus}</td></tr>"

    # ── Panchang ──────────────────────────────────────────────────────────────
    pan=chart.get("panchang",{})
    pan_html=""
    if pan:
        pan_html=f"""<div class="pan-grid">
          <div class="pi2"><span class="pl2">Tithi</span><span class="pv2">{pan.get('tithi','—')}</span></div>
          <div class="pi2"><span class="pl2">Vara</span><span class="pv2">{pan.get('vara','—')} · lord {pan.get('vara_lord','—')}</span></div>
          <div class="pi2"><span class="pl2">Nakshatra</span><span class="pv2">{pan.get('nakshatra','—')} · lord {pan.get('nakshatra_lord','—')}</span></div>
          <div class="pi2"><span class="pl2">Yoga</span><span class="pv2">{pan.get('yoga','—')}</span></div>
          <div class="pi2"><span class="pl2">Karaṇa</span><span class="pv2">{pan.get('karana','—')}</span></div>
        </div>"""

    # ── Yogas ─────────────────────────────────────────────────────────────────
    yoga_html=""
    for y in chart.get("yogas",[]):
        yoga_html+=f"<div class='ycard'><span class='yn'>{y.get('name','')}</span> <span class='yg'>{y.get('group','')}</span><div class='yd'>{y.get('detail','')}</div></div>"
    if not yoga_html: yoga_html="<p style='color:#7777aa'>No notable yogas detected.</p>"

    # ── Varshaphala summary ───────────────────────────────────────────────────
    vp_html=""
    if vp:
        vp_html=f"""<div class="pan-grid" id="vp-summary" style="margin-bottom:20px">
          <div class="pi2"><span class="pl2">Solar Return</span><span class="pv2">{vp.get('return_dt_utc', vp.get('solar_return_utc','—'))}</span></div>
          <div class="pi2"><span class="pl2">Jahreslagna</span><span class="pv2">{vp.get('lagna','—')} {vp.get('lagna_pos','—')}</span></div>
          <div class="pi2"><span class="pl2">Muntha</span><span class="pv2">{vp.get('muntha_sign', vp.get('muntha','—'))} (Herr: {vp.get('muntha_lord','—')})</span></div>
          <div class="pi2"><span class="pl2">Varsha Pati</span><span class="pv2">{vp.get('varsha_pati','—')}</span></div>
        </div>"""

    # ── Varshaphala age dropdown & static planet rows ────────────────────────────
    import datetime as _dt2
    try:
        birth_year = int(str(m.get("birth","1900"))[:4])
    except Exception:
        birth_year = 1900
    current_age = max(1, _dt2.date.today().year - birth_year)
    vp_age_options = ""
    for _a in range(1, 101):
        _yr = birth_year + _a
        _sel = " selected" if _a == current_age else ""
        vp_age_options += f'<option value="{_a}"{_sel}>{_a} Jahre ({_yr})</option>'

    vp_planet_rows = ""
    for pn in PLANET_ORDER:
        vpd = vp.get("planets",{}).get(pn,{})
        _si = vpd.get("sign_idx",0)
        _dig = vpd.get("dignity","—")
        _dcls = ("dig-e" if "Exalt" in _dig else "dig-d" if "Debil" in _dig
                 else "dig-o" if "Own" in _dig or "Moola" in _dig else "")
        vp_planet_rows += (f"<tr><td><span class='pi'>{PLANET_ICON.get(pn,'')}</span>{pn}</td>"
                           f"<td>{SIGN_ICON[_si]} {vpd.get('sign','—')}</td>"
                           f"<td>{vpd.get('house','—')}</td>"
                           f"<td>{vpd.get('pos','—')}</td>"
                           f"<td>{vpd.get('nakshatra','—')}</td>"
                           f"<td><span class='dig {_dcls}'>{_dig}</span></td></tr>")

    sp_vp2 = _build_sign_planets(vp.get("planets",{})) if vp.get("planets") else sp_rasi
    vp_svgs_ni = _ni_svg(vp_li, sp_vp2, f"Varshaphala · Jahr {vp.get('year_number','')}")
    vp_svgs_si = _si_svg(vp_li, sp_vp2, f"Varshaphala · Jahr {vp.get('year_number','')}")

    # ── AI reading ────────────────────────────────────────────────────────────
    reading_html=""
    if interpretation and interpretation.strip():
        reading_html=_md_html(interpretation)

    name_g=m.get('name','')+(f" ({m['gender']})" if m.get('gender') else "")

    # ── Main rasi chart svgs ──────────────────────────────────────────────────
    rasi_svgs   = _chart_svgs(li, sp_rasi,  "Rāśi · D-1", planet_data=pls)
    bhava_svgs  = _chart_svgs(li, sp_bhava, "Bhava Chalit", planet_data=pls)
    d9_svgs     = _chart_svgs(d9li,  sp_d9,  "Navāṃśa · D-9")
    d3_svgs     = _chart_svgs(d3li,  sp_d3,  "Drekkāna · D-3")
    d10_svgs    = _chart_svgs(d10li, sp_d10, "Daśāṃśa · D-10")
    vp_svgs     = _chart_svgs(vp_li, sp_vp,  f"Varshaphala · Year {vp.get('year','')}")
    tr_svgs     = _chart_svgs(tr_li, sp_tr,  f"Transits · {chart.get('transit_date','today')}")

    # ── HTML ──────────────────────────────────────────────────────────────────
    return f"""<!DOCTYPE html>
<html lang="de"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vedic Chart · {m.get('name','')}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,600;1,400&family=Inter:wght@300;400;500&display=swap" rel="stylesheet">
<style>
:root{{--bg:#0d0d1f;--bg2:#13132a;--bg3:#1a1a35;--ac:#c9a84c;--ac2:#7b6fff;--tx:#e8e4f0;--mu:#8888bb;--bd:#2a2a4a;--gd:#4caf7d;--rd:#e05c5c}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--tx);font-family:'Inter',sans-serif;font-size:14px;line-height:1.6;min-height:100vh}}
body::before{{content:'';position:fixed;inset:0;z-index:-1;background:radial-gradient(ellipse at 20% 30%,rgba(123,111,255,.06) 0%,transparent 60%),radial-gradient(ellipse at 80% 70%,rgba(201,168,76,.04) 0%,transparent 50%),var(--bg)}}
.pw{{max-width:1120px;margin:0 auto;padding:24px 16px 80px}}
/* Header */
.hdr{{text-align:center;padding:36px 0 28px;border-bottom:1px solid var(--bd)}}
.hdr h1{{font-family:'Cormorant Garamond',serif;font-size:2.1rem;color:var(--ac);letter-spacing:.04em}}
.sub{{color:var(--mu);font-size:.78rem;letter-spacing:.12em;text-transform:uppercase;margin-bottom:8px}}
.mg{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:8px;margin-top:20px;text-align:left}}
.mi{{background:var(--bg2);border:1px solid var(--bd);border-radius:8px;padding:10px 14px}}
.ml{{color:var(--mu);font-size:.72rem;text-transform:uppercase;letter-spacing:.08em}}
.mv{{color:var(--tx);font-size:.92rem;margin-top:2px}}
.lb{{display:inline-block;background:rgba(201,168,76,.12);color:var(--ac);border:1px solid rgba(201,168,76,.3);border-radius:20px;padding:2px 12px;font-size:.82rem}}
/* DL bar */
.dlb{{display:flex;gap:10px;margin:20px 0 0;flex-wrap:wrap}}
.btn{{display:inline-flex;align-items:center;gap:6px;padding:10px 18px;border-radius:8px;font-size:.84rem;font-weight:500;cursor:pointer;text-decoration:none;border:none;transition:.18s;font-family:'Inter',sans-serif}}
.btn-p{{background:var(--ac);color:#0d0d1f}}.btn-p:hover{{background:#d4b560}}
.btn-s{{background:var(--bg2);color:var(--tx);border:1px solid var(--bd)}}.btn-s:hover{{border-color:var(--ac);color:var(--ac)}}
/* Tabs */
.tabs{{display:flex;gap:2px;margin:28px 0 0;border-bottom:1px solid var(--bd);overflow-x:auto;scrollbar-width:none}}
.tabs::-webkit-scrollbar{{display:none}}
.tb{{padding:9px 16px;background:none;border:none;border-bottom:2px solid transparent;color:var(--mu);cursor:pointer;font-size:.82rem;white-space:nowrap;font-family:'Inter',sans-serif;transition:.18s}}
.tb:hover{{color:var(--tx)}}.tb.active{{color:var(--ac);border-bottom-color:var(--ac)}}
.tp{{display:none;padding:24px 0}}.tp.active{{display:block}}
/* Charts */
.cg{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px;margin-bottom:28px}}
.cc{{background:var(--bg2);border:1px solid var(--bd);border-radius:12px;padding:16px;text-align:center}}
.cc h3{{font-family:'Cormorant Garamond',serif;color:var(--ac);font-size:.95rem;margin-bottom:10px;letter-spacing:.05em}}
.chart-toggle-wrap{{position:relative}}
.chart-toggle{{display:flex;gap:4px;justify-content:center;margin-bottom:10px}}
.ctbtn{{padding:4px 14px;border-radius:20px;border:1px solid var(--bd);background:none;color:var(--mu);cursor:pointer;font-size:.76rem;font-family:'Inter',sans-serif;transition:.15s}}
.ctbtn.active{{background:rgba(201,168,76,.15);border-color:var(--ac);color:var(--ac)}}
/* Tables */
.dt{{width:100%;border-collapse:collapse;font-size:.8rem}}
.dt th{{background:var(--bg3);color:var(--mu);font-weight:500;text-transform:uppercase;font-size:.7rem;letter-spacing:.07em;padding:9px 10px;text-align:left;border-bottom:1px solid var(--bd)}}
.dt td{{padding:8px 10px;border-bottom:1px solid rgba(255,255,255,.04);vertical-align:middle}}
.dt tr:hover td{{background:rgba(255,255,255,.02)}}
.pi{{font-size:1rem;margin-right:3px}}
.dig{{padding:2px 8px;border-radius:10px;font-size:.74rem;font-weight:500}}
.dig-e{{background:rgba(76,175,125,.15);color:var(--gd)}}
.dig-d{{background:rgba(224,92,92,.12);color:var(--rd)}}
.dig-o{{background:rgba(201,168,76,.12);color:var(--ac)}}
.av-h{{color:var(--gd);font-weight:600}}.av-l{{color:var(--rd)}}.av-m{{color:var(--ac)}}
.sb-s{{color:var(--gd)}}.sb-w{{color:var(--rd)}}
.act td{{color:var(--ac)}}.act{{background:rgba(201,168,76,.05)}}
/* Dasha box */
.dbox{{display:grid;grid-template-columns:auto 1fr;gap:5px 14px;background:var(--bg2);border:1px solid var(--bd);border-radius:10px;padding:16px 20px;margin-bottom:20px;max-width:380px}}
.dl{{color:var(--mu);font-size:.75rem;text-transform:uppercase;letter-spacing:.07em;align-self:center}}
.dv{{color:var(--ac);font-size:.98rem;font-family:'Cormorant Garamond',serif;font-weight:600}}
/* Yogas */
.ycard{{background:var(--bg2);border:1px solid var(--bd);border-radius:8px;padding:11px 15px;margin-bottom:9px}}
.yn{{color:var(--ac);font-family:'Cormorant Garamond',serif;font-size:.98rem;font-weight:600}}
.yg{{color:var(--mu);font-size:.74rem;margin-left:8px}}
.yd{{color:var(--tx);font-size:.8rem;margin-top:4px}}
/* Panchang / summary cards */
.pan-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}}
.pi2{{background:var(--bg2);border:1px solid var(--bd);border-radius:8px;padding:10px 14px}}
.pl2{{color:var(--mu);font-size:.72rem;text-transform:uppercase;letter-spacing:.07em;display:block}}
.pv2{{color:var(--tx);font-size:.88rem;margin-top:3px;display:block}}
/* Reading */
.rw{{max-width:720px}}
.rh{{font-family:'Cormorant Garamond',serif;color:var(--ac);font-size:1.3rem;margin:26px 0 9px;display:flex;align-items:center;gap:10px}}
.rh::before{{content:'—';color:rgba(201,168,76,.5)}}
.rp{{color:var(--tx);line-height:1.8;margin-bottom:12px;font-size:.9rem}}
.rl{{padding-left:18px;margin-bottom:12px}}
.rl li{{color:var(--tx);line-height:1.7;font-size:.9rem;margin-bottom:5px}}
.rdis{{color:var(--mu);font-size:.76rem;font-style:italic;border-top:1px solid var(--bd);margin-top:28px;padding-top:14px}}
.sh{{font-family:'Cormorant Garamond',serif;color:var(--mu);font-size:.72rem;text-transform:uppercase;letter-spacing:.12em;margin-bottom:14px;margin-top:24px}}
.ow{{overflow-x:auto}}
</style></head>
<body><div class="pw">

<div class="hdr">
  <div class="sub">✦ Jyotiṣa · Lahiri Ayanamsha · Whole-Sign Houses ✦</div>
  <h1>{name_g or 'Vedic Birth Chart'}</h1>
  <div class="mg">
    <div class="mi"><div class="ml">Birth</div><div class="mv">{m.get('birth','')} <span style="color:var(--mu)">({m.get('tz','')})</span></div></div>
    <div class="mi"><div class="ml">Universal Time</div><div class="mv">{m.get('ut','')}</div></div>
    <div class="mi"><div class="ml">Location</div><div class="mv">{m.get('location','—')} · {m.get('lat','')}° N / {m.get('lon','')}° E</div></div>
    <div class="mi"><div class="ml">Lagna</div><div class="mv"><span class="lb">{chart.get('lagna','')} {chart.get('lagna_pos','')}</span></div></div>
    <div class="mi"><div class="ml">JD / Ayanamsha</div><div class="mv">{m.get('jd','')} / {m.get('ayan','')}° (Lahiri)</div></div>
    <div class="mi"><div class="ml">Engine</div><div class="mv" style="font-size:.8rem">{m.get('engine','')}</div></div>
  </div>
</div>

<div class="dlb">
  <a class="btn btn-p" id="pdf-btn" href="#">⬇ PDF herunterladen</a>
  <a class="btn btn-s" href="javascript:window.print()">🖨 Drucken</a>
</div>

<div class="tabs">
  <button class="tb active" onclick="showTab('reading',this)">Reading</button>
  <button class="tb" onclick="showTab('chart',this)">Chart</button>
  <button class="tb" onclick="showTab('planets',this)">Planeten &amp; Häuser</button>
  <button class="tb" onclick="showTab('divisional',this)">Divisional</button>
  <button class="tb" onclick="showTab('dasha',this)">Viṃśottarī</button>
  <button class="tb" onclick="showTab('chara',this)">Chara Daśā</button>
  <button class="tb" onclick="showTab('jaimini',this)">Jaimini</button>
  <button class="tb" onclick="showTab('ashtaka',this)">Ashtakavarga</button>
  <button class="tb" onclick="showTab('bala',this)">Bala</button>
  <button class="tb" onclick="showTab('panchang',this)">Pañcāṅga</button>
  <button class="tb" onclick="showTab('yogas',this)">Yogas</button>
  <button class="tb" onclick="showTab('transits',this)">Transits</button>
  <button class="tb" onclick="showTab('varsha',this)">Varshaphala</button>
</div>

<!-- READING -->
<div class="tp active" id="tab-reading">
  {'<div class="rw">'+reading_html+'<p class="rdis">Dieser Bericht wurde KI-gestützt aus dem exakt berechneten Horoskop erstellt und dient der persönlichen Reflexion.</p></div>' if reading_html else '<p style="color:var(--mu);padding:32px 0">Keine Deutung verfügbar.</p>'}
</div>

<!-- CHART -->
<div class="tp" id="tab-chart">
  <div class="cg">
    <div class="cc"><h3>Rāśi · D-1</h3>{rasi_svgs}</div>
    <div class="cc"><h3>Bhava Chalit</h3>{bhava_svgs}</div>
  </div>
</div>

<!-- PLANETS & HOUSES -->
<div class="tp" id="tab-planets">
  <p class="sh">Grahas</p>
  <div class="ow"><table class="dt">
    <thead><tr><th>Planet</th><th>Sign</th><th>Pos</th><th>H (Bhava)</th><th>Nakshatra</th><th>Pada</th><th>Lord</th><th>Dignity</th></tr></thead>
    <tbody>{planet_rows}</tbody>
  </table></div>
  <p class="sh">Bhavas (Häuser)</p>
  <div class="ow"><table class="dt">
    <thead><tr><th>H</th><th>Sign</th><th>Lord</th><th>Occupants</th></tr></thead>
    <tbody>{house_rows}</tbody>
  </table></div>
</div>

<!-- DIVISIONAL -->
<div class="tp" id="tab-divisional">
  <div class="cg">
    <div class="cc"><h3>Navāṃśa · D-9</h3>{d9_svgs}</div>
    <div class="cc"><h3>Drekkāna · D-3</h3>{d3_svgs}</div>
    <div class="cc"><h3>Daśāṃśa · D-10</h3>{d10_svgs}</div>
  </div>
</div>

<!-- VIMSHOTTARI DASHA -->
<div class="tp" id="tab-dasha">
  <p class="sh">Aktuelle Periode</p>
  {dasha_cur}
  <p class="sh">Mahādaśā Timeline</p>
  <div class="ow"><table class="dt">
    <thead><tr><th>Planet</th><th>Start</th><th>End</th><th>Duration</th></tr></thead>
    <tbody>{maha_rows}</tbody>
  </table></div>
  <p class="sh">Antaradaśās (aktive Mahādaśā)</p>
  <div class="ow"><table class="dt">
    <thead><tr><th>Maha / Antar</th><th>Start</th><th>End</th></tr></thead>
    <tbody>{antar_rows}</tbody>
  </table></div>
</div>

<!-- CHARA DASHA -->
<div class="tp" id="tab-chara">
  <p class="sh">Chara Daśā (Jaimini)</p>
  <div class="ow"><table class="dt">
    <thead><tr><th>Rāśi</th><th>Start</th><th>End</th><th>Years</th></tr></thead>
    <tbody>{chara_rows}</tbody>
  </table></div>
  <p class="sh">Antaradaśās (aktive Chara Mahadaśā)</p>
  <div class="ow"><table class="dt">
    <thead><tr><th>Maha / Antar</th><th>Start</th><th>End</th></tr></thead>
    <tbody>{chara_antar_rows}</tbody>
  </table></div>
</div>

<!-- JAIMINI -->
<div class="tp" id="tab-jaimini">
  <p class="sh">Chara Karakas (8-karaka)</p>
  {jai_summary}
  <div class="ow" style="margin-top:16px"><table class="dt">
    <thead><tr><th>Abbr</th><th>Role</th><th>Planet</th><th>Sign</th><th>Deg</th><th>Effective</th></tr></thead>
    <tbody>{jai_rows}</tbody>
  </table></div>
</div>

<!-- ASHTAKAVARGA -->
<div class="tp" id="tab-ashtaka">
  <p class="sh">Bhinnashtakavarga · Sarvashtakavarga — grün ≥5 / ≥30, rot ≤2 / ≤25, * = Lagna</p>
  <div class="ow"><table class="dt">
    <thead>{akv_hdr}</thead>
    <tbody>{akv_rows}</tbody>
  </table></div>
</div>

<!-- BALA -->
<div class="tp" id="tab-bala">
  <p class="sh">Shad Bala</p>
  <div class="ow"><table class="dt">
    <thead><tr><th>Planet</th><th>Sthana</th><th>Dig</th><th>Kala</th><th>Cheshta</th><th>Naisarg</th><th>Drik</th><th>Rupa / Req</th><th>Status</th></tr></thead>
    <tbody>{sb_rows}</tbody>
  </table></div>
  <p class="sh" style="margin-top:20px">Ishta &amp; Kashta Phala</p>
  <div class="ow"><table class="dt">
    <thead><tr><th></th>{"".join(f"<th>{p}</th>" for p in PLANET_ORDER[:7])}</tr></thead>
    <tbody>
      <tr><td style="color:var(--gd)">Ishta</td>{ishta_row}</tr>
      <tr><td style="color:var(--rd)">Kashta</td>{kashta_row}</tr>
    </tbody>
  </table></div>
  <p class="sh" style="margin-top:20px">Bhava Bala</p>
  <div class="ow"><table class="dt">
    <thead><tr><th>House</th><th>Sign</th><th>Lord</th><th>Adhipati</th><th>Dig</th><th>Drishti</th><th>Rupas</th></tr></thead>
    <tbody>{bb_rows}</tbody>
  </table></div>
</div>

<!-- PANCHANG -->
<div class="tp" id="tab-panchang">
  <p class="sh">Pañcāṅga bei Geburt</p>
  {pan_html}
</div>

<!-- YOGAS -->
<div class="tp" id="tab-yogas">
  <p class="sh">Aktive Yogas</p>
  {yoga_html}
</div>

<!-- TRANSITS -->
<div class="tp" id="tab-transits">
  <p class="sh">Aktuelle Transits vs. natal · {chart.get('transit_local','heute')}</p>
  <div class="cg"><div class="cc"><h3>Transits</h3>{tr_svgs}</div></div>
  <div class="ow"><table class="dt">
    <thead><tr><th>Planet</th><th>Natal Sign</th><th>Transit Sign</th><th>Pos</th><th>Nakshatra</th><th>Bindus (Sarva)</th></tr></thead>
    <tbody>{ts_rows}</tbody>
  </table></div>
</div>

<!-- VARSHAPHALA -->
<div class="tp" id="tab-varsha">
  <p class="sh">Varshaphala · Jahr {vp.get('year','')}</p>
  {vp_html}
  <div class="cg"><div class="cc"><h3>Solar Return Chart</h3>{vp_svgs}</div></div>
</div>

</div>
<script>
function showTab(id,btn){{
  document.querySelectorAll('.tp').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tb').forEach(b=>b.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  btn.classList.add('active');
}}
function setStyle(btn,style,wrap){{
  wrap.querySelectorAll('.ctbtn').forEach(b=>b.classList.remove('active'));
  wrap.querySelectorAll('.cv').forEach(v=>v.style.display='none');
  btn.classList.add('active');
  wrap.querySelector('.cv.'+style).style.display='';
}}
// Set PDF button href from URL param
(function(){{
  var sid=new URLSearchParams(location.search).get('session_id')||location.pathname.split('/').pop();
  if(sid){{ var b=document.getElementById('pdf-btn'); if(b) b.href='/download/'+sid; }}
}})();

// ── Varshaphala dynamic loader ──────────────────────────────────────────────
var _SIGNS_ABR=['Ari','Tau','Gem','Can','Leo','Vir','Lib','Sco','Sag','Cap','Aqu','Pis'];
var _SIGN_ICO=['♈','♉','♊','♋','♌','♍','♎','♏','♐','♑','♒','♓'];
var _PL_ABR={{Sun:'Su',Moon:'Mo',Mars:'Ma',Mercury:'Me',Jupiter:'Ju',Venus:'Ve',Saturn:'Sa',Rahu:'Ra',Ketu:'Ke'}};
var _PL_ICO={{Sun:'☉',Moon:'☽',Mars:'♂',Mercury:'☿',Jupiter:'♃',Venus:'♀',Saturn:'♄',Rahu:'☊',Ketu:'☋'}};
var _PL_ORDER=['Sun','Moon','Mars','Mercury','Jupiter','Venus','Saturn','Rahu','Ketu'];
var _NI_POLY=["200,0 120,120 280,120","400,0 280,120 200,0","400,0 280,120 400,120","400,120 280,120 280,280 400,280","400,280 280,280 400,400","400,400 280,280 200,400","200,400 280,280 120,280","200,400 120,280 0,400","0,400 120,280 0,280","0,280 120,280 120,120 0,120","0,0 120,120 0,120","0,0 120,120 200,0"];
var _NI_LX=[200,358,370,370,358,295,200,42,30,30,42,105];
var _NI_LY=[55,42,85,200,358,370,345,358,315,200,42,32];
var _SI_POS={{11:[0,0],0:[0,1],1:[0,2],2:[0,3],10:[1,0],3:[1,3],9:[2,0],4:[2,3],8:[3,0],7:[3,1],6:[3,2],5:[3,3]}};

function _plCol(p){{return(['Sun','Moon','Jupiter','Mars'].indexOf(p)>=0)?'#f5e6a3':(['Rahu','Ketu'].indexOf(p)>=0)?'#cc99ff':'#a8d4ff';}}

function _niSvg(li,sp,ttl,sz){{
  sz=sz||380; var h='';
  for(var si=0;si<12;si++){{
    var pts=_NI_POLY[si],lx=_NI_LX[si],ly=_NI_LY[si],isL=(si===li);
    h+='<polygon points="'+pts+'" fill="'+(isL?'rgba(201,168,76,.12)':'rgba(255,255,255,.02)')+'" stroke="'+(isL?'#c9a84c':'#2e2e5a')+'" stroke-width="'+(isL?1.5:.7)+'"/>';
    h+='<text x="'+lx+'" y="'+(ly-16)+'" text-anchor="middle" font-size="9" fill="'+(isL?'#c9a84c':'#6666aa')+'" font-family="serif">'+_SIGNS_ABR[si]+(isL?'◆':'')+'</text>';
    if(isL) h+='<text x="'+lx+'" y="'+(ly-27)+'" text-anchor="middle" font-size="8" fill="#c9a84c" font-family="serif">Asc</text>';
    (sp[si]||[]).forEach(function(p,i){{h+='<text x="'+lx+'" y="'+(ly+i*13)+'" text-anchor="middle" font-size="11" font-weight="bold" fill="'+_plCol(p)+'" font-family="serif">'+(_PL_ABR[p]||p.slice(0,2))+'</text>';}});
  }}
  h+='<text x="200" y="215" text-anchor="middle" font-size="10" fill="#7777aa" font-family="serif" font-style="italic">'+ttl+'</text>';
  return '<svg viewBox="0 0 '+sz+' '+sz+'" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:'+sz+'px">'+h+'</svg>';
}}
function _siSvg(li,sp,ttl,sz){{
  sz=sz||380; var CW=sz/4,h='';
  Object.keys(_SI_POS).forEach(function(si){{
    si=parseInt(si); var pos=_SI_POS[si],r=pos[0],c=pos[1],x=c*CW,y=r*CW,isL=(si===li);
    h+='<rect x="'+x+'" y="'+y+'" width="'+CW+'" height="'+CW+'" fill="'+(isL?'rgba(201,168,76,.12)':'rgba(255,255,255,.02)')+'" stroke="'+(isL?'#c9a84c':'#2e2e5a')+'" stroke-width="'+(isL?1.5:.7)+'"/>';
    h+='<text x="'+(x+CW/2)+'" y="'+(y+14)+'" text-anchor="middle" font-size="9" fill="'+(isL?'#c9a84c':'#6666aa')+'" font-family="serif">'+_SIGNS_ABR[si]+(isL?'◆':'')+'</text>';
    (sp[si]||[]).forEach(function(p,i){{h+='<text x="'+(x+CW/2)+'" y="'+(y+28+i*13)+'" text-anchor="middle" font-size="11" font-weight="bold" fill="'+_plCol(p)+'" font-family="serif">'+(_PL_ABR[p]||p.slice(0,2))+'</text>';}});
  }});
  h+='<text x="'+(sz/2)+'" y="'+(sz/2+5)+'" text-anchor="middle" font-size="10" fill="#7777aa" font-family="serif" font-style="italic">'+ttl+'</text>';
  return '<svg viewBox="0 0 '+sz+' '+sz+'" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:'+sz+'px">'+h+'</svg>';
}}

function setVpStyle(s){{
  document.querySelectorAll('#tab-varsha .ctbtn').forEach(function(b){{b.classList.toggle('active',b.textContent.toLowerCase()===s);}});
  document.getElementById('vp-chart-ni').style.display=s==='north'?'':'none';
  document.getElementById('vp-chart-si').style.display=s==='south'?'':'none';
}}

function loadVarshaphala(age){{
  var sid=new URLSearchParams(location.search).get('session_id')||location.pathname.split('/').pop();
  if(!sid||sid==='view') return;
  document.getElementById('vp-loading').style.display='block';
  document.getElementById('vp-content').style.display='none';
  document.getElementById('vp-error').style.display='none';
  fetch('/varshaphala/'+sid+'/'+age)
    .then(function(r){{return r.json();}})
    .then(function(d){{
      if(d.error){{document.getElementById('vp-error').textContent=d.error;document.getElementById('vp-error').style.display='block';document.getElementById('vp-loading').style.display='none';return;}}
      var sg=document.getElementById('vp-summary');
      if(sg) sg.innerHTML='<div class="pi2"><span class="pl2">Solar Return</span><span class="pv2">'+d.solar_return+'</span></div><div class="pi2"><span class="pl2">Jahreslagna</span><span class="pv2">'+d.lagna+' '+d.lagna_pos+'</span></div><div class="pi2"><span class="pl2">Muntha</span><span class="pv2">'+d.muntha+' ('+d.muntha_lord+')</span></div><div class="pi2"><span class="pl2">Varsha Pati</span><span class="pv2">'+d.varsha_pati+'</span></div>';
      var sp={{}};for(var i=0;i<12;i++) sp[i]=[];
      _PL_ORDER.forEach(function(p){{if(d.planets[p]) sp[d.planets[p].sign_idx||0].push(p);}});
      var ttl='Varshaphala · '+age+' Jahre ('+d.year+')';
      document.getElementById('vp-chart-ni').innerHTML=_niSvg(d.lagna_si||0,sp,ttl);
      document.getElementById('vp-chart-si').innerHTML=_siSvg(d.lagna_si||0,sp,ttl);
      document.getElementById('vp-chart-title').textContent=ttl;
      var rows='';
      _PL_ORDER.forEach(function(p){{
        var pd=d.planets[p]||{{}},si=pd.sign_idx||0,dig=pd.dignity||'—';
        var dc=dig.indexOf('Exalt')>=0?'dig-e':dig.indexOf('Debil')>=0?'dig-d':(dig.indexOf('Own')>=0||dig.indexOf('Moola')>=0)?'dig-o':'';
        rows+='<tr><td><span class="pi">'+(_PL_ICO[p]||'')+'</span>'+p+'</td><td>'+_SIGN_ICO[si]+' '+(pd.sign||'—')+'</td><td>'+(pd.house||'—')+'</td><td>'+(pd.pos||'—')+'</td><td>'+(pd.nakshatra||'—')+'</td><td><span class="dig '+dc+'">'+(pd.dignity||'—')+'</span></td></tr>';
      }});
      document.getElementById('vp-planet-rows').innerHTML=rows;
      document.getElementById('vp-loading').style.display='none';
      document.getElementById('vp-content').style.display='block';
    }})
    .catch(function(e){{document.getElementById('vp-error').textContent='Fehler: '+e;document.getElementById('vp-error').style.display='block';document.getElementById('vp-loading').style.display='none';}});
}}
</script>
</body></html>"""

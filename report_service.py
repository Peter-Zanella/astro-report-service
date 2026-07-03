#!/usr/bin/env python3
"""
report_service.py — the automatic fulfilment "robot" for AI-assisted Jyotiṣa reports.

Flow:
  1. Customer pays via a Stripe Payment Link.
  2. Stripe redirects to  {BASE_URL}/report?session_id={CHECKOUT_SESSION_ID}
  3. We verify the session is PAID, show a short birth-data form.
  4. On submit we calculate the chart, write the AI interpretation, build the PDF,
     e-mail it to the customer (and return it as an instant download).
  5. Each Stripe session can be redeemed once (idempotent, via SQLite).

Deploy alongside:  astro_engine.py · ai_report.py · pdf_report.py
Run:               uvicorn report_service:app --host 0.0.0.0 --port 8000
Requirements:      fastapi  uvicorn[standard]  stripe  anthropic  reportlab
                   python-multipart  pyswisseph
Host on:           Render / Railway / Fly.io / a small VPS (set the env vars below).

Environment variables
  STRIPE_SECRET_KEY     sk_live_… (or sk_test_…)
  ANTHROPIC_API_KEY     sk-ant-…           (used by ai_report)
  BASE_URL              https://reports.deine-domain.ch
  SMTP_HOST SMTP_PORT SMTP_USER SMTP_PASS MAIL_FROM   (e-mail sending)
  MAIL_FROM_NAME        "Jyotiṣa Reports"   (optional)
  BCC_OWNER             your@email           (optional copy to you)
  DEV_NO_STRIPE=1       optional: skip Stripe checks for LOCAL testing only
"""

from __future__ import annotations
import datetime as _dt
import os
import sqlite3
from html import escape
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from io import BytesIO

import astro_engine as E
import ai_report
import pdf_report
import chart_html

# ── CONFIG ────────────────────────────────────────────────────────────────────
BASE_URL   = os.environ.get("BASE_URL", "http://localhost:8000")
DEV_NO_STRIPE = os.environ.get("DEV_NO_STRIPE") == "1"
TEST_MODE  = DEV_NO_STRIPE or os.environ.get("TEST_MODE") == "1"
DB_PATH    = os.environ.get("DB_PATH", "deliveries.db")

# Map your Stripe Price IDs -> (depth, human label). Fill in from your Payment Links.
PRICE_DEPTH = {
    "price_BASIS":   ("basis",   "Basis-Bericht"),
    "price_PREMIUM": ("premium", "Premium-Bericht"),
    "price_YEAR":    ("year",    "Jahresbericht"),
    "price_MATCH":   ("premium", "Partnerschafts-Bericht"),
    "price_PRASNA":  ("prasna",  "Prāśna-Bericht"),
}
DEFAULT_DEPTH = ("premium", "Bericht")

PAL = {"ink": "#2b2118", "paper": "#fdf6e9", "paper2": "#f6ecd6",
       "gold": "#b8902f", "accent": "#9a342c", "line": "#e3d6b8", "muted": "#8a7a5c"}

app = FastAPI(title="Jyotiṣa Report Service")


# ── Stripe helpers ────────────────────────────────────────────────────────────
def _stripe():
    import stripe
    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    return stripe


def get_paid_session(session_id: str, want_depth: str = ""):
    """Return (ok, info) where info has email, name, depth, label. Verifies payment."""
    if TEST_MODE:
        depth = want_depth if want_depth in ("basis", "premium", "prasna", "year") else "premium"
        label = f"{depth.capitalize()}-Bericht (TEST)" if depth not in ("prasna", "year") else ("Prāśna (TEST)" if depth == "prasna" else "Jahresbericht (TEST)")
        return True, {"email": "", "name": "", "depth": depth,
                      "label": label, "test": True}
    try:
        stripe = _stripe()
        s = stripe.checkout.Session.retrieve(session_id, expand=["line_items"])
    except Exception:
        return False, {"error": "Session nicht gefunden."}
    if s.get("payment_status") != "paid":
        return False, {"error": "Zahlung nicht bestätigt."}
    depth, label = DEFAULT_DEPTH
    try:
        price_id = s["line_items"]["data"][0]["price"]["id"]
        depth, label = PRICE_DEPTH.get(price_id, DEFAULT_DEPTH)
    except Exception:
        pass
    cd = s.get("customer_details") or {}
    return True, {"email": cd.get("email") or "", "name": cd.get("name") or "",
                  "depth": depth, "label": label}


# ── idempotency (one report per paid session) ─────────────────────────────────
def _db():
    con = sqlite3.connect(DB_PATH)
    con.execute("CREATE TABLE IF NOT EXISTS deliveries"
                "(session_id TEXT PRIMARY KEY, status TEXT, created TEXT)")
    return con


def claim_session(session_id: str) -> bool:
    """Return True if we just claimed it (first time); False if already used.
    TEST- and PRASNA- sessions are never locked (always allow re-runs)."""
    if session_id.startswith("TEST-") or session_id.startswith("PRASNA-"):
        return True
    con = _db()
    try:
        con.execute("INSERT INTO deliveries VALUES(?,?,?)",
                    (session_id, "done", _dt.datetime.utcnow().isoformat()))
        con.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        con.close()


def already_done(session_id: str) -> bool:
    if session_id.startswith("TEST-") or session_id.startswith("PRASNA-"):
        return False
    con = _db()
    row = con.execute("SELECT 1 FROM deliveries WHERE session_id=?", (session_id,)).fetchone()
    con.close()
    return row is not None



# ── HTML (on-brand, minimal) ──────────────────────────────────────────────────
def _page(title: str, inner: str) -> str:
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box}} body{{margin:0;background:{PAL['paper']};color:{PAL['ink']};
font-family:'Inter',system-ui,sans-serif;line-height:1.6;display:flex;min-height:100vh;
align-items:center;justify-content:center;padding:24px}}
.card{{background:{PAL['paper2']};border:1px solid {PAL['line']};border-radius:8px;
max-width:520px;width:100%;padding:40px}}
h1{{font-family:'Cormorant Garamond',serif;font-size:2rem;margin:0 0 .2em;color:{PAL['accent']}}}
.ey{{font-size:.74rem;letter-spacing:.2em;text-transform:uppercase;color:{PAL['gold']};
font-weight:600;margin-bottom:10px}}
label{{display:block;font-size:.85rem;font-weight:600;margin:14px 0 4px}}
input,select{{width:100%;padding:11px 12px;border:1px solid {PAL['line']};border-radius:4px;
background:{PAL['paper2']};color:{PAL['ink']};font-size:1rem;font-family:inherit}}
input:-webkit-autofill,input:-webkit-autofill:hover,input:-webkit-autofill:focus{{-webkit-box-shadow:0 0 0 30px {PAL['paper2']} inset !important;-webkit-text-fill-color:{PAL['ink']} !important}}
.row{{display:flex;gap:12px}} .row>div{{flex:1}}
button{{margin-top:22px;width:100%;background:{PAL['ink']};color:{PAL['paper']};border:0;
padding:14px;border-radius:3px;font-weight:600;font-size:1rem;cursor:pointer}}
button:hover{{background:#3c2f20}}
.muted{{color:{PAL['muted']};font-size:.85rem;margin-top:14px}}
.ok{{color:#2e7d4f}} .err{{color:{PAL['accent']}}}
.dot{{color:{PAL['gold']}}}
</style></head><body><div class="card">{inner}</div></body></html>"""


def form_html(session_id: str, info: dict) -> str:
    test = info.get("test")
    cur_depth = info.get("depth", "premium")
    banner = ('<p class="muted" style="background:#fff8e8;border:1px dashed #b8902f;'
              'padding:8px 12px;border-radius:4px">⚙ TEST-MODUS – keine Zahlung nötig.</p>'
              if test else "")
    def _opt(val, label):
        sel = " selected" if val == cur_depth else ""
        return f'<option value="{val}"{sel}>{label}</option>'
    depth_field = ("" if not test else
                   '<label>Stufe (nur Test)</label><select name="depth">'
                   + _opt("premium", "Premium")
                   + _opt("basis", "Basis")
                   + _opt("year", "Jahr (Varshaphala)")
                   + '</select>')
    return _page("Geburtsdaten – " + info["label"], f"""
<div class="ey"><span class="dot">◆</span> {escape(info['label'])}</div>
<h1>Fast geschafft</h1>{banner}
<p>Gib deine Geburtsdaten ein – wir erstellen deinen Bericht sofort. Er steht dir
danach direkt zum Anschauen und als PDF-Download zur Verfügung.</p>
<form method="post" action="/generate" onsubmit="document.getElementById('working').style.display='block';var b=this.querySelector('button[type=submit]');b.textContent='⏳ Bericht wird erstellt…';setTimeout(function(){{b.disabled=true;}},50);">
<input type="hidden" name="session_id" value="{escape(session_id)}">
<label>Name</label><input name="name" value="{escape(info.get('name',''))}" required>
<div class="row"><div><label>Geburtsdatum</label>
<input type="text" name="date" placeholder="TT.MM.JJJJ" inputmode="numeric" required></div>
<div><label>Geburtszeit</label><input type="time" name="time" value="12:00"></div></div>
<label>Geburtsort (Stadt, Land)</label>
<input name="city" placeholder="z.B. Zürich, Schweiz" required>
<div><label>Sprache</label><select name="lang"><option value="de">Deutsch</option>
<option value="en">English</option></select></div></div>
{depth_field}
<button type="submit">Bericht erstellen</button>
</form>
<div id="working" style="display:none;margin-top:18px;padding:14px;background:#fff8e8;border:1px solid #b8902f;border-radius:6px;text-align:center;font-size:.9rem;color:#8a7a5c">
  ⏳ Berechnung läuft — Planetenpositionen, KI-Deutung, PDF.<br>
  <small>Dies dauert 1–3 Minuten. Bitte die Seite nicht schliessen.</small>
</div>
<p class="muted">Geburtszeit unbekannt? 12:00 ist eine faire Näherung – Aszendent/Häuser
sind dann weniger genau.</p>""")


def msg_html(title: str, body: str, kind: str = "") -> str:
    return _page(title, f'<div class="ey"><span class="dot">◆</span> Jyotiṣa Reports</div>'
                        f'<h1>{escape(title)}</h1><p class="{kind}">{body}</p>')


# ── routes ────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def home():
    return msg_html("Jyotiṣa Report Service", "Service läuft. Berichte werden nach der "
                    "Zahlung über den Stripe-Link erstellt.")


@app.get("/report", response_class=HTMLResponse)
def report_form(session_id: str = "", depth: str = ""):
    if not session_id:
        if TEST_MODE:                       # test: no payment/session needed
            session_id = "TEST-" + _dt.datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        else:
            return HTMLResponse(msg_html("Kein Zugang", "Fehlende Session-ID.", "err"), 400)
    if already_done(session_id):
        return HTMLResponse(msg_html("Bereits erstellt",
                            "Dieser Bericht wurde bereits erstellt und kann unten heruntergeladen werden.", "ok"))
    ok, info = get_paid_session(session_id, want_depth=depth)
    if not ok:
        return HTMLResponse(msg_html("Zahlung prüfen",
                            escape(info.get("error", "Zahlung nicht bestätigt.")), "err"), 402)
    return HTMLResponse(form_html(session_id, info))


@app.post("/generate")
def generate(session_id: str = Form(...), name: str = Form(""), date: str = Form(...),
             time: str = Form("12:00"), city: str = Form(...),
             lang: str = Form("de"), depth: str = Form("")):
    ok, info = get_paid_session(session_id, want_depth=depth)
    if not ok:
        return HTMLResponse(msg_html("Zahlung prüfen",
                            escape(info.get("error", "nicht bestätigt")), "err"), 402)
    if not claim_session(session_id):
        return HTMLResponse(msg_html("Bereits erstellt",
                            "Dieser Bericht wurde bereits erstellt und kann unten heruntergeladen werden.", "ok"))

    try:
        # Accept DD.MM.YYYY (new default), YYYY-MM-DD, DD-MM-YYYY, MM/DD/YYYY
        date = date.strip()
        if "." in date:
            parts = date.split(".")
            d, mo, y = int(parts[0]), int(parts[1]), int(parts[2])
        elif "-" in date:
            parts = date.split("-")
            if len(parts[0]) == 4:
                y, mo, d = int(parts[0]), int(parts[1]), int(parts[2])
            else:
                d, mo, y = int(parts[0]), int(parts[1]), int(parts[2])
        elif "/" in date:
            parts = date.split("/")
            mo, d, y = int(parts[0]), int(parts[1]), int(parts[2])
        else:
            raise ValueError(f"Unbekanntes Datumsformat: {date}")
        hh, mm = (int(x) for x in (time or "12:00").split(":"))
        loc = E.resolve_location(city, y, mo, d, hh, mm)
        if not loc:
            return HTMLResponse(msg_html("Ort nicht gefunden",
                                "Bitte Stadt und Land prüfen.", "err"), 400)
        chart = E.generate_chart(y, mo, d, hh, mm, loc["lat"], loc["lon"], loc["offset"],
                                 loc.get("label", city), name, "")
        depth = info["depth"]
        text = ai_report.generate_interpretation(chart, lang=lang, depth=depth)
        title = "Persönliche Deutung" if lang == "de" else "Personal Reading"
        pdf = pdf_report.build_pdf(chart, interpretation=text, interpretation_title=title)
    except Exception as e:
        # un-claim so the customer can retry
        con = _db(); con.execute("DELETE FROM deliveries WHERE session_id=?", (session_id,))
        con.commit(); con.close()
        import traceback, sys
        traceback.print_exc(file=sys.stderr)
        return HTMLResponse(msg_html("Etwas ist schiefgelaufen",
                            f"Bitte versuche es erneut oder melde dich bei uns. ({escape(str(e))})",
                            "err"), 500)

    fn = f"{info['label'].replace(' ', '_')}.pdf"
    ititle = "Persönliche Deutung" if lang == "de" else "Personal Reading"
    html_view = chart_html.build_html(chart, interpretation=text,
                                      interpretation_title=ititle)
    _PDF_CACHE[session_id]  = (pdf, fn)
    _HTML_CACHE[session_id] = html_view
    # Cache raw birth params so Varshaphala can be recomputed for any age
    _CHART_CACHE[session_id] = {
        "y": y, "mo": mo, "d": d, "hh": hh, "mm": mm,
        "lat": loc["lat"], "lon": loc["lon"], "offset": loc["offset"],
        "label": loc.get("label", city), "name": name,
        "natal_sun_sid": chart.get("lons", {}).get("Sun"),
        "natal_lagna_si": chart.get("lagna_idx"),
        "birth_year": y,
    }
    # Redirect directly to the HTML view — it has a PDF download button built in
    return RedirectResponse(url=f"/view/{session_id}?session_id={session_id}", status_code=303)




# ── Prāśna (Horary) ──────────────────────────────────────────────────────────
def _prasna_form_html(session_id: str, info: dict) -> str:
    now = _dt.datetime.now()
    test = info.get("test")
    banner = ('<p class="muted" style="background:#fff8e8;border:1px dashed #b8902f;'
              'padding:8px 12px;border-radius:4px">⚙ TEST-MODUS – keine Zahlung nötig.</p>'
              if test else "")
    return _page("Prāśna — Horoskop der Frage", f"""
<div class="ey"><span class="dot">◆</span> Prāśna · Jyotiṣa</div>
<h1>Deine Frage ans Universum</h1>{banner}
<p>Prāśna ist die horārische Astrologie des Jyotiṣa: Das Horoskop des Frageaugenblicks
enthält die Antwort. Stelle deine Frage aufrichtig — der Moment zählt.</p>
<form method="post" action="/prasna-generate"
  onsubmit="document.getElementById('pw').style.display='block';var b=this.querySelector('button[type=submit]');b.textContent='⏳ Prāśna wird berechnet…';setTimeout(function(){{b.disabled=true;}},50);">
<input type="hidden" name="session_id" value="{escape(session_id)}">
<label>Deine Frage</label>
<input name="question" placeholder="z.B. Werde ich die Stelle bekommen?" required>
<label>Name (optional)</label><input name="name" value="">
<label>Ort der Frage (Stadt, Land)</label>
<input name="city" placeholder="z.B. Zürich, Schweiz" required>
<div class="row">
  <div><label>Datum</label>
  <input type="text" name="date" placeholder="TT.MM.JJJJ"
    value="{now.strftime('%d.%m.%Y')}" inputmode="numeric" required></div>
  <div><label>Uhrzeit</label>
  <input type="time" name="time" value="{now.strftime('%H:%M')}"></div>
</div>
<div><label>Sprache</label><select name="lang">
  <option value="de">Deutsch</option>
  <option value="en">English</option>
</select></div>
<button type="submit">Prāśna berechnen</button>
</form>
<div id="pw" style="display:none;margin-top:18px;padding:14px;background:#fff8e8;
  border:1px solid {PAL['gold']};border-radius:6px;text-align:center;
  font-size:.9rem;color:{PAL['muted']}">
  ⏳ Berechnung läuft — Planetenpositionen, Signifikatoren, KI-Deutung.<br>
  <small>Dies dauert 1–2 Minuten. Bitte die Seite nicht schliessen.</small>
</div>
<p class="muted">Das Horoskop wird für den angegebenen Moment berechnet.
Je aufrichtiger und drängender die Frage, desto klarer die Antwort.</p>""")


@app.get("/prasna", response_class=HTMLResponse)
def prasna_page(session_id: str = ""):
    if not session_id:
        if TEST_MODE:
            session_id = "PRASNA-" + _dt.datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        else:
            return HTMLResponse(msg_html("Kein Zugang",
                                "Fehlende Session-ID. Bitte über den Zahlungslink zugreifen.", "err"), 400)
    ok, info = get_paid_session(session_id, want_depth="prasna")
    if not ok:
        return HTMLResponse(msg_html("Zahlung prüfen",
                            escape(info.get("error", "Zahlung nicht bestätigt.")), "err"), 402)
    return HTMLResponse(_prasna_form_html(session_id, info))


@app.post("/prasna-generate")
def prasna_generate(
    session_id: str = Form(...),
    question: str = Form(...),
    name: str = Form(""),
    city: str = Form(...),
    date: str = Form(...),
    time: str = Form("12:00"),
    lang: str = Form("de"),
):
    ok, info = get_paid_session(session_id, want_depth="prasna")
    if not ok:
        return HTMLResponse(msg_html("Zahlung prüfen",
                            escape(info.get("error", "nicht bestätigt")), "err"), 402)
    if not claim_session(session_id):
        return HTMLResponse(msg_html("Bereits erstellt",
                            "Dieser Prāśna-Bericht wurde bereits erstellt.", "ok"))
    try:
        date = date.strip()
        if "." in date:
            parts = date.split(".")
            d, mo, y = int(parts[0]), int(parts[1]), int(parts[2])
        elif "-" in date:
            parts = date.split("-")
            if len(parts[0]) == 4:
                y, mo, d = int(parts[0]), int(parts[1]), int(parts[2])
            else:
                d, mo, y = int(parts[0]), int(parts[1]), int(parts[2])
        else:
            parts = date.split("/")
            mo, d, y = int(parts[0]), int(parts[1]), int(parts[2])
        hh, mm = (int(x) for x in (time or "12:00").split(":"))
        loc = E.resolve_location(city, y, mo, d, hh, mm)
        if not loc:
            return HTMLResponse(msg_html("Ort nicht gefunden",
                                "Bitte Stadt und Land prüfen.", "err"), 400)
        chart = E.generate_chart(y, mo, d, hh, mm,
                                 loc["lat"], loc["lon"], loc["offset"],
                                 loc.get("label", city), name or "Prāśna", "")
        chart["prasna_question"] = question
        chart["prasna_mode"] = True
        text = ai_report.generate_interpretation(chart, lang=lang, depth="prasna")
        title = "Prāśna-Deutung" if lang == "de" else "Prāśna Reading"
        pdf = pdf_report.build_pdf(chart, interpretation=text,
                                   interpretation_title=title)
        html_view = chart_html.build_html(chart, interpretation=text,
                                          interpretation_title=title)
    except Exception as e:
        # un-claim so the customer can retry
        con = _db(); con.execute("DELETE FROM deliveries WHERE session_id=?", (session_id,))
        con.commit(); con.close()
        import traceback, sys
        traceback.print_exc(file=sys.stderr)
        return HTMLResponse(msg_html("Fehler",
                            f"Bitte erneut versuchen. ({escape(str(e))})", "err"), 500)

    fn = f"Prasna_{y}{mo:02d}{d:02d}.pdf"
    _PDF_CACHE[session_id]  = (pdf, fn)
    _HTML_CACHE[session_id] = html_view
    return RedirectResponse(url=f"/view/{session_id}?session_id={session_id}", status_code=303)



# ── Varshaphala (age-dependent, AJAX) ────────────────────────────────────────
from fastapi.responses import JSONResponse

@app.get("/varshaphala/{session_id}/{age}")
def varshaphala_age(session_id: str, age: int,
                    sun: float = None, lagna: int = None,
                    mo: int = None, d: int = None,
                    lat: float = None, lon: float = None, by: int = None):
    """Recompute Varshaphala for a given age.
    Birth params come from query args (survive spin-down) or fall back to disk cache."""
    # Prefer explicit query params (robust); fall back to disk cache
    if all(v is not None for v in (sun, lagna, mo, d, lat, lon, by)):
        params = {"natal_sun_sid": sun, "natal_lagna_si": lagna,
                  "mo": mo, "d": d, "lat": lat, "lon": lon, "birth_year": by}
    else:
        params = _CHART_CACHE.get(session_id)
    if not params:
        return JSONResponse({"error": "Sitzung abgelaufen \u2014 bitte Bericht neu erstellen."})
    try:
        if params.get("natal_sun_sid") is None or params.get("natal_lagna_si") is None:
            return JSONResponse({"error": "Grunddaten unvollst\u00e4ndig."})
        target_year = int(params["birth_year"]) + int(age)
        vp = E.compute_varshaphala(
            int(params["birth_year"]), int(params["mo"]), int(params["d"]),
            float(params["natal_sun_sid"]), int(params["natal_lagna_si"]),
            float(params["lat"]), float(params["lon"]), target_year,
        )
        vp_lagna_si = vp.get("lagna_si", 0)
        # Shape response for the frontend (loadVarshaphala expects these keys)
        return JSONResponse({
            "year":         vp.get("target_year"),
            "year_number":  vp.get("year_number"),
            "solar_return": vp.get("return_dt_utc", ""),
            "lagna":        vp.get("lagna"),
            "lagna_pos":    vp.get("lagna_pos"),
            "lagna_si":     vp_lagna_si,
            "muntha":       vp.get("muntha_sign"),
            "muntha_lord":  vp.get("muntha_lord"),
            "varsha_pati":  vp.get("varsha_pati"),
            "planets": {
                p: {
                    "sign":      d2.get("sign"),
                    "sign_idx":  d2.get("sign_idx"),
                    # house = position of planet's sign relative to the year-lagna
                    "house":     ((d2.get("sign_idx", 0) - vp_lagna_si) % 12) + 1,
                    "pos":       d2.get("pos"),
                    "nakshatra": d2.get("nakshatra"),
                    "dignity":   d2.get("dignity"),
                }
                for p, d2 in vp.get("planets", {}).items()
                if p != "Ascendant"
            },
        })
    except Exception as e:
        import traceback, sys
        traceback.print_exc(file=sys.stderr)
        return JSONResponse({"error": f"Berechnungsfehler: {e}"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))

# ── caches persisted to disk (survive Render free-tier spin-down) ────────────
_CACHE_DIR = Path(os.environ.get("CACHE_DIR", "report_cache"))
_CACHE_DIR.mkdir(exist_ok=True)
_PDF_CACHE:  dict = {}
_HTML_CACHE: dict = {}


class _DiskCache:
    """Dict-like wrapper that also persists to disk (HTML as .html, PDF as .pdf+.name)."""
    def __init__(self, kind: str):
        self.kind = kind  # "html" or "pdf"

    def __setitem__(self, sid: str, value):
        safe = "".join(c for c in sid if c.isalnum() or c in "-_")
        if self.kind == "html":
            (_CACHE_DIR / f"{safe}.html").write_text(value, encoding="utf-8")
        else:
            pdf, fn = value
            (_CACHE_DIR / f"{safe}.pdf").write_bytes(pdf)
            (_CACHE_DIR / f"{safe}.name").write_text(fn, encoding="utf-8")

    def get(self, sid: str, default=None):
        safe = "".join(c for c in sid if c.isalnum() or c in "-_")
        try:
            if self.kind == "html":
                return (_CACHE_DIR / f"{safe}.html").read_text(encoding="utf-8")
            else:
                pdf = (_CACHE_DIR / f"{safe}.pdf").read_bytes()
                fn  = (_CACHE_DIR / f"{safe}.name").read_text(encoding="utf-8")
                return (pdf, fn)
        except FileNotFoundError:
            return default

    def pop(self, sid: str, default=None):
        # For PDFs we keep the file (allow repeat downloads); just return it
        return self.get(sid, default)


_PDF_CACHE  = _DiskCache("pdf")
_HTML_CACHE = _DiskCache("html")
class _JsonDiskCache:
    """Dict-like JSON cache persisted to disk (for Varshaphala birth params)."""
    def __init__(self):
        pass
    def __setitem__(self, sid: str, value: dict):
        safe = "".join(c for c in sid if c.isalnum() or c in "-_")
        import json
        (_CACHE_DIR / f"{safe}.chart.json").write_text(
            json.dumps(value), encoding="utf-8")
    def get(self, sid: str, default=None):
        safe = "".join(c for c in sid if c.isalnum() or c in "-_")
        import json
        try:
            return json.loads((_CACHE_DIR / f"{safe}.chart.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            return default

_CHART_CACHE = _JsonDiskCache()   # session_id -> raw birth params for Varshaphala recompute


@app.get("/download/{session_id}")
def download_pdf(session_id: str):
    entry = _PDF_CACHE.pop(session_id, None)
    if not entry:
        return HTMLResponse(msg_html("Link abgelaufen",
                            "Der Download-Link ist nicht mehr gültig. "
                            "Bitte wende dich an uns.", "err"), 404)
    pdf, fn = entry
    return StreamingResponse(BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{fn}"'})


@app.get("/view/{session_id}", response_class=HTMLResponse)
def view_chart(session_id: str):
    html = _HTML_CACHE.get(session_id)
    if not html:
        return HTMLResponse(msg_html("Ansicht abgelaufen",
                            "Die interaktive Ansicht ist nicht mehr verfügbar. "
                            "Bitte erstelle einen neuen Bericht.", "err"), 404)
    return HTMLResponse(html)  # keep in cache (not popped)

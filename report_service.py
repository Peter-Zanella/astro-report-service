#!/usr/bin/env python3
"""
report_service.py — the automatic fulfilment "robot" for AI-assisted Jyotiṣa reports.

Flow:
  1. Customer pays via a Stripe Payment Link.
  2. Stripe redirects to  {BASE_URL}/report?session_id={CHECKOUT_SESSION_ID}
  3. We verify the session is PAID, show a short birth-data form.
  4. On submit we calculate the chart, write the AI interpretation, build the PDF,
     and redirect to the interactive HTML view (PDF download button built in).
     The customer can re-open /view and /download with their session link anytime.
  5. Each Stripe session can be generated once (idempotent, via SQLite), but the
     finished report stays downloadable from the web page.

Deploy alongside:  astro_engine.py · ai_report.py · pdf_report.py
Run:               uvicorn report_service:app --host 0.0.0.0 --port 8000
Requirements:      fastapi  uvicorn[standard]  stripe  anthropic  reportlab
                   python-multipart  pyswisseph
Host on:           Render / Railway / Fly.io / a small VPS (set the env vars below).

Environment variables
  STRIPE_SECRET_KEY     sk_live_… (or sk_test_…)
  ANTHROPIC_API_KEY     sk-ant-…           (used by ai_report)
  BASE_URL              https://reports.deine-domain.ch
  DEV_NO_STRIPE=1       optional: skip Stripe checks for LOCAL testing only
  TEST_KEY              optional: secret for test entrances; testers use
                        /report?key=<TEST_KEY> — without it, TEST_MODE is open
"""

from __future__ import annotations
import datetime as _dt
import os
import sqlite3
import sys as _sys
import threading as _threading
import time as _time
import traceback as _traceback
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
TEST_KEY   = os.environ.get("TEST_KEY", "").strip()

# ── production safety for the free "test" entrances ──────────────────────────
# Free test generation bypasses Stripe entirely, so it must NEVER be reachable
# on a production deployment. Two hard guards:
#   1. If a LIVE Stripe key is configured, test mode is forced OFF regardless of
#      TEST_MODE/DEV_NO_STRIPE (prevents an accidental env var from opening free
#      premium reports in prod).
#   2. Without a TEST_KEY, test access is only honoured on a localhost BASE_URL
#      (local dev). On any real domain a TEST_KEY is required.
_STRIPE_LIVE   = os.environ.get("STRIPE_SECRET_KEY", "").startswith("sk_live")
_LOCAL_DEPLOY  = BASE_URL.startswith(("http://localhost", "http://127.", "http://0.0.0.0"))
_TEST_REQUESTED = DEV_NO_STRIPE or os.environ.get("TEST_MODE") == "1"
TEST_MODE  = _TEST_REQUESTED and not _STRIPE_LIVE
if _TEST_REQUESTED and _STRIPE_LIVE:
    print("[SECURITY] TEST_MODE/DEV_NO_STRIPE ignored: a live Stripe key is present.",
          file=_sys.stderr)


def _test_access(key: str) -> bool:
    """True if free test generation is allowed for this request."""
    if not TEST_MODE:
        return False
    if TEST_KEY:
        return key == TEST_KEY
    return _LOCAL_DEPLOY          # no TEST_KEY → localhost dev only


def _is_test_session(sid: str) -> bool:
    """True if `sid` is a trusted test session id. Without a TEST_KEY the prefix
    is guessable ('TEST-'), so such ids are only trusted on a localhost deploy —
    otherwise anyone could POST a 'TEST-…' id to get a free paid report."""
    if not TEST_MODE:
        return False
    if not sid.startswith((_test_prefix("TEST"), _test_prefix("PRASNA"))):
        return False
    return bool(TEST_KEY) or _LOCAL_DEPLOY


def _test_prefix(kind: str = "TEST") -> str:
    """Prefix for minted test session ids. With TEST_KEY set, the prefix embeds
    a token derived from the key, so hand-crafted TEST-… ids don't bypass
    payment verification."""
    if not TEST_KEY:
        return f"{kind}-"
    import hashlib
    tok = hashlib.sha256(TEST_KEY.encode()).hexdigest()[:10]
    return f"{kind}-{tok}-"
DB_PATH    = os.environ.get("DB_PATH", "deliveries.db")

# Map your Stripe Price IDs -> (depth, human label). Fill in from your Payment Links.
# Preise (Stand Juli 2026): Premium CHF 49 · Prāśna CHF 49 · Zusatzfrage CHF 18
PRICE_DEPTH = {
    "price_BASIS":   ("basis",   "Basis-Bericht"),
    "price_PREMIUM": ("premium", "Premium-Bericht"),
    "price_PRASNA_ZUSATZ": ("prasna_zusatz", "Prāśna-Zusatzfrage"),
    "price_FRAGE":   ("frage", "Zusatzfrage zum Bericht"),
    "price_YEAR":    ("year",    "Jahresbericht"),
    "price_MATCH":   ("partner", "Partnerschafts-Bericht"),
    "price_PRASNA":  ("prasna",  "Prāśna-Bericht"),
}
# NOTE: intentionally NO default depth. get_paid_session() fails closed on an
# unknown/unmapped price id rather than granting a premium report.

# Dark theme — matches the interactive report view (chart_html.py :root vars),
# so the order form and the finished report look like one product.
PAL = {"ink": "#e8e4f0", "paper": "#0d0d1f", "paper2": "#13132a",
       "gold": "#c9a84c", "accent": "#c9a84c", "line": "#2a2a4a", "muted": "#8888bb",
       "field": "#1a1a35"}

app = FastAPI(title="Jyotiṣa Report Service")


# ── simple in-process rate limiting (fixed window per client IP) ─────────────
# Single-worker deployments (Render/Railway free tier) → an in-memory limiter is
# sufficient to blunt the expensive LLM/engine endpoints. For multi-worker setups
# move this to Redis.
_RL_LOCK = _threading.Lock()
_RL: dict = {}          # ip -> (count, window_start_monotonic)


def _client_ip(request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "?"


def _rate_ok(ip: str, limit: int, window: float) -> bool:
    """True if this IP is under `limit` requests in the last `window` seconds."""
    now = _time.monotonic()
    with _RL_LOCK:
        cnt, start = _RL.get(ip, (0, now))
        if now - start > window:
            cnt, start = 0, now
        cnt += 1
        _RL[ip] = (cnt, start)
        if len(_RL) > 4096:                     # opportunistic cleanup
            for k in [k for k, (_c, s) in list(_RL.items()) if now - s > window]:
                _RL.pop(k, None)
        return cnt <= limit


# ── PII retention: sweep cached charts/PDFs/HTML + delivery rows past TTL ─────
RETENTION_DAYS = int(os.environ.get("REPORT_RETENTION_DAYS", "90"))
_SWEEP_LOCK = _threading.Lock()
_LAST_SWEEP = [0.0]


def _maybe_sweep(force: bool = False) -> None:
    """Delete report_cache files and delivery rows older than RETENTION_DAYS.
    Throttled to once per hour. PII (name, birth data, lat/lon) must not linger
    on disk indefinitely."""
    if RETENTION_DAYS <= 0:
        return
    now = _time.monotonic()
    with _SWEEP_LOCK:
        if not force and (now - _LAST_SWEEP[0]) < 3600:
            return
        _LAST_SWEEP[0] = now
    cutoff = _time.time() - RETENTION_DAYS * 86400
    try:
        for f in _CACHE_DIR.glob("*"):
            try:
                if f.is_file() and f.stat().st_mtime < cutoff:
                    f.unlink()
            except OSError:
                pass
    except Exception:
        _traceback.print_exc(file=_sys.stderr)
    try:
        iso_cutoff = (_dt.datetime.utcnow()
                      - _dt.timedelta(days=RETENTION_DAYS)).isoformat()
        con = _db()
        con.execute("DELETE FROM deliveries WHERE created < ?", (iso_cutoff,))
        con.commit(); con.close()
    except Exception:
        _traceback.print_exc(file=_sys.stderr)


# ── access control for read/compute endpoints ───────────────────────────────
def _is_known_session(sid: str) -> bool:
    """Authorise /view-adjacent read & compute endpoints: only sessions we
    actually issued a report for. already_done() reads SQLite (survives the free
    tier's disk spin-down); cache + test-session checks cover fresh/local cases.
    Prevents anonymous callers from driving the engine with an arbitrary sid."""
    if not sid:
        return False
    return (already_done(sid) or _is_test_session(sid)
            or _HTML_CACHE.get(sid) is not None
            or _CHART_CACHE.get(sid) is not None)


# ── Stripe helpers ────────────────────────────────────────────────────────────
def _stripe():
    import stripe
    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    return stripe


def get_paid_session(session_id: str, want_depth: str = ""):
    """Return (ok, info) where info has email, name, depth, label. Verifies payment."""
    if _is_test_session(session_id):
        depth = want_depth if want_depth in ("basis", "premium", "prasna",
                                             "prasna_zusatz", "year",
                                             "partner", "frage") else "premium"
        label = (f"{depth.capitalize()}-Bericht (TEST)"
                 if depth not in ("prasna", "year", "partner")
                 else "Prāśna (TEST)" if depth == "prasna"
                 else "Jahresbericht (TEST)" if depth == "year"
                 else "Zusatzfrage zum Bericht (TEST)" if depth == "frage"
                 else "Partnerschafts-Bericht (TEST)")
        return True, {"email": "", "name": "", "depth": depth,
                      "label": label, "test": True}
    try:
        stripe = _stripe()
        s = stripe.checkout.Session.retrieve(session_id, expand=["line_items"])
    except Exception:
        # Log the real cause (network/Stripe outage vs. genuinely unknown id) so a
        # transient failure isn't silently misreported as "not found" forever.
        _traceback.print_exc(file=_sys.stderr)
        return False, {"error": "Session konnte nicht geprüft werden. "
                                "Bitte später erneut versuchen oder uns kontaktieren."}
    if s.get("payment_status") != "paid":
        return False, {"error": "Zahlung nicht bestätigt."}
    # Fail CLOSED: depth is derived only from a known Stripe price id. An unknown
    # or unreadable price must not silently grant a premium report (price/param
    # tampering, or a cheaper product with an unmapped id).
    try:
        price_id = s["line_items"]["data"][0]["price"]["id"]
    except Exception:
        price_id = None
    if price_id not in PRICE_DEPTH:
        print(f"[BILLING] unmapped/again price_id={price_id!r} for session "
              f"{session_id[:12]}… — refusing.", file=_sys.stderr)
        return False, {"error": "Produkt nicht erkannt — bitte kontaktiere uns "
                                "mit deiner Zahlungsbestätigung."}
    depth, label = PRICE_DEPTH[price_id]
    cd = s.get("customer_details") or {}
    return True, {"email": cd.get("email") or "", "name": cd.get("name") or "",
                  "depth": depth, "label": label,
                  "ref": s.get("client_reference_id") or ""}


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
    # referrer=no-referrer: the report URL carries the session_id (a bearer token),
    # so no Referer header must reach the Google Fonts CDN or any cross-origin host.
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="referrer" content="no-referrer">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box}} body{{margin:0;background:{PAL['paper']};color:{PAL['ink']};
font-family:'Inter',system-ui,sans-serif;line-height:1.6;display:flex;min-height:100vh;
align-items:center;justify-content:center;padding:24px}}
body::before{{content:'';position:fixed;inset:0;z-index:-1;background:
radial-gradient(ellipse at 20% 30%,rgba(123,111,255,.06) 0%,transparent 60%),
radial-gradient(ellipse at 80% 70%,rgba(201,168,76,.04) 0%,transparent 50%),{PAL['paper']}}}
.card{{background:{PAL['paper2']};border:1px solid {PAL['line']};border-radius:12px;
max-width:520px;width:100%;padding:40px}}
h1{{font-family:'Cormorant Garamond',serif;font-size:2.1rem;margin:0 0 .2em;color:{PAL['gold']};letter-spacing:.03em}}
.ey{{font-size:.74rem;letter-spacing:.2em;text-transform:uppercase;color:{PAL['gold']};
font-weight:600;margin-bottom:10px}}
p{{color:{PAL['ink']}}}
label{{display:block;font-size:.85rem;font-weight:600;margin:14px 0 4px;color:{PAL['ink']}}}
input,select,textarea{{width:100%;padding:11px 12px;border:1px solid {PAL['line']};border-radius:6px;
background:{PAL['field']};color:{PAL['ink']};font-size:1rem;font-family:inherit}}
input:focus,select:focus,textarea:focus{{outline:none;border-color:{PAL['gold']}}}
input::placeholder,textarea::placeholder{{color:{PAL['muted']}}}
input[type=date],input[type=time]{{color-scheme:dark}}
input:-webkit-autofill,input:-webkit-autofill:hover,input:-webkit-autofill:focus{{-webkit-box-shadow:0 0 0 30px {PAL['field']} inset !important;-webkit-text-fill-color:{PAL['ink']} !important}}
.row{{display:flex;gap:12px;flex-wrap:wrap}} .row>div{{flex:1;min-width:150px}}
@media(max-width:480px){{.row{{flex-direction:column;gap:8px}}}}
button{{margin-top:22px;width:100%;background:{PAL['gold']};color:#0d0d1f;border:0;
padding:14px;border-radius:8px;font-weight:600;font-size:1rem;cursor:pointer}}
button:hover{{background:#d4b560}}
.muted{{color:{PAL['muted']};font-size:.85rem;margin-top:14px}}
.ok{{color:#4caf7d}} .err{{color:#e05c5c}}
.dot{{color:{PAL['gold']}}}
</style></head><body><div class="card">{inner}</div>
<script>
// Date mask: user types digits only (numeric keypad on mobile); dots are
// inserted automatically → TT.MM.JJJJ. Lets the birth YEAR be typed directly,
// unlike a native date picker which forces spinning through the calendar.
function fmtDate(el){{var v=el.value.replace(/[^0-9]/g,'').slice(0,8);
el.value = v.length>4 ? v.slice(0,2)+'.'+v.slice(2,4)+'.'+v.slice(4)
         : v.length>2 ? v.slice(0,2)+'.'+v.slice(2) : v;}}
</script></body></html>"""


def form_html(session_id: str, info: dict) -> str:
    # Bis zu 3 individuelle Fragen — nur im Premium-Reading; die allgemeinen
    # Varga-/Beziehungskapitel werden dann kompakter gehalten (ai_report).
    if info.get("depth") == "premium":
        questions_block = f"""
<div style="border:1px solid {PAL['line']};border-radius:6px;padding:14px 16px;margin:14px 0">
<label style="font-weight:600">Deine Fragen an dein Horoskop <span style="color:{PAL['muted']};font-weight:400">(bis zu 3, optional — sie erhalten ein eigenes Kapitel)</span></label>
<input name="q1" placeholder="Frage 1 — z.B. Soll ich mich beruflich verändern?" style="margin-bottom:8px">
<input name="q2" placeholder="Frage 2 (optional)" style="margin-bottom:8px">
<input name="q3" placeholder="Frage 3 (optional)">
<p class="muted" style="font-size:.8rem;margin-top:8px">Damit deine Fragen Raum bekommen, fallen die allgemeinen Kapitel zu Beruf (D10), Geschwistern (D3), Heim (D4) und Beziehung (D9) etwas kompakter aus. Weitere Fragen kannst du später jederzeit als bezahlte Zusatzfrage stellen.</p>
</div>"""
    else:
        questions_block = ""
    test = info.get("test")
    cur_depth = info.get("depth", "premium")
    banner = ('<p class="muted" style="background:rgba(201,168,76,.1);border:1px dashed #c9a84c;'
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
<div class="row">
  <div><label>Geburtsdatum</label>
    <input name="date" inputmode="numeric" maxlength="10" oninput="fmtDate(this)"
      placeholder="TT.MM.JJJJ · z.B. 24.08.1957" autocomplete="off" required></div>
  <div><label>Geburtszeit</label><input type="time" name="time" value="12:00"></div>
</div>
<label>Geburtsort (Stadt, Land)</label>
<input name="city" placeholder="z.B. Zürich, Schweiz" required>
<div class="row"><div><label>Geschlecht <span style="color:{PAL['muted']};font-weight:400">(optional)</span></label>
<select name="gender"><option value="">—</option><option value="weiblich">weiblich</option>
<option value="männlich">männlich</option><option value="divers">divers</option></select></div>
<div><label>Beruf <span style="color:{PAL['muted']};font-weight:400">(optional)</span></label>
<input name="occupation" placeholder="z.B. Lehrerin, Ingenieur"></div></div>
<label>Aktuelle Lebensumstände <span style="color:{PAL['muted']};font-weight:400">(optional, für gezieltere Deutung)</span></label>
<textarea name="context" rows="3" placeholder="z.B. berufliche Neuorientierung, Familiengründung geplant, gesundheitliche Fragen …" style="width:100%;padding:11px 12px;border:1px solid {PAL['line']};border-radius:4px;background:{PAL['paper2']};color:{PAL['ink']};font-size:1rem;font-family:inherit;resize:vertical"></textarea>
{questions_block}
<div><label>Sprache</label><select name="lang"><option value="de">Deutsch</option>
<option value="en">English</option></select></div></div>
{depth_field}
<button type="submit">Bericht erstellen</button>
</form>
<div id="working" style="display:none;margin-top:18px;padding:14px;background:rgba(201,168,76,.1);border:1px solid #c9a84c;border-radius:8px;text-align:center;font-size:.9rem;color:#c9a84c">
  ⏳ Berechnung läuft — Planetenpositionen, KI-Deutung, PDF.<br>
  <small>Dies dauert 1–3 Minuten. Bitte die Seite nicht schliessen.</small>
</div>""")


def msg_html(title: str, body: str, kind: str = "") -> str:
    return _page(title, f'<div class="ey"><span class="dot">◆</span> Jyotiṣa Reports</div>'
                        f'<h1>{escape(title)}</h1><p class="{kind}">{body}</p>')


def done_html(session_id: str) -> str:
    """Page shown when a session was already redeemed: link straight to the
    finished report (interactive view + PDF download) instead of a dead end."""
    sid = escape(session_id, quote=True)
    has_html = _HTML_CACHE.get(session_id) is not None
    has_pdf  = _PDF_CACHE.get(session_id)  is not None
    btn = (f'display:block;text-align:center;text-decoration:none;margin-top:14px;'
           f'padding:14px;border-radius:3px;font-weight:600;font-size:1rem')
    links = ""
    if has_html:
        links += (f'<a href="/view/{sid}" style="{btn};background:{PAL["ink"]};'
                  f'color:{PAL["paper"]}">Bericht ansehen</a>')
    if has_pdf:
        links += (f'<a href="/download/{sid}" style="{btn};background:{PAL["paper2"]};'
                  f'color:{PAL["ink"]};border:1px solid {PAL["gold"]}">PDF herunterladen</a>')
    if _PDF_CACHE.get(session_id + "-technik") is not None:
        links += (f'<a href="/download/{sid}?variant=technik" style="{btn};'
                  f'background:{PAL["paper2"]};color:{PAL["muted"]};'
                  f'border:1px solid {PAL["line"]}">Technische Daten (PDF)</a>')
    if links:
        body = ('<p class="ok">Dieser Bericht wurde bereits erstellt. '
                'Du kannst ihn hier jederzeit wieder öffnen:</p>' + links +
                f'<p class="muted">Tipp: Speichere diesen Link, um später wieder '
                f'auf deinen Bericht zuzugreifen.</p>')
    else:
        body = ('<p class="err">Dieser Bericht wurde bereits erstellt, ist aber '
                'auf dem Server nicht mehr verfügbar. '
                'Bitte melde dich bei uns – wir helfen dir sofort weiter.</p>')
    return _page("Dein Bericht", f'<div class="ey"><span class="dot">◆</span> Jyotiṣa Reports</div>'
                                 f'<h1>Dein Bericht</h1>{body}')


# ── routes ────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def home():
    return msg_html("Jyotiṣa Report Service", "Service läuft. Berichte werden nach der "
                    "Zahlung über den Stripe-Link erstellt.")


@app.get("/health")
def health():
    """Cheap liveness check for uptime monitors (also keeps the free-tier
    instance warm when pinged periodically). No side effects, no tokens."""
    try:
        import swisseph  # noqa: F401
        eng = "swiss-ephemeris"
    except ImportError:
        eng = "fallback"
    return JSONResponse({"ok": True, "engine": eng})


@app.get("/report", response_class=HTMLResponse)
def report_form(session_id: str = "", depth: str = "", key: str = ""):
    if not session_id:
        if _test_access(key):               # test: no payment/session needed
            session_id = _test_prefix("TEST") + _dt.datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        else:
            return HTMLResponse(msg_html("Kein Zugang", "Fehlende Session-ID.", "err"), 400)
    if already_done(session_id):
        return HTMLResponse(done_html(session_id))
    ok, info = get_paid_session(session_id, want_depth=depth)
    if not ok:
        return HTMLResponse(msg_html("Zahlung prüfen",
                            escape(info.get("error", "Zahlung nicht bestätigt.")), "err"), 402)
    if info.get("depth") == "partner":
        return HTMLResponse(partner_form_html(session_id, info))
    if info.get("depth") == "frage":
        return RedirectResponse(
            url=f"/report-frage?session_id={session_id}", status_code=303)
    return HTMLResponse(form_html(session_id, info))


@app.post("/generate")
def generate(request: Request,
             session_id: str = Form(...), name: str = Form(""), date: str = Form(""),
             time: str = Form("12:00"), city: str = Form(...),
             lang: str = Form("de"), depth: str = Form(""),
             gender: str = Form(""), occupation: str = Form(""), context: str = Form(""),
             b_day: str = Form(""), b_month: str = Form(""), b_year: str = Form(""),
             q1: str = Form(""), q2: str = Form(""), q3: str = Form("")):
    if not _rate_ok(_client_ip(request), limit=10, window=600.0):
        return HTMLResponse(msg_html("Zu viele Anfragen",
                            "Bitte warte einen Moment und versuche es erneut.", "err"), 429)
    _maybe_sweep()
    ok, info = get_paid_session(session_id, want_depth=depth)
    if not ok:
        return HTMLResponse(msg_html("Zahlung prüfen",
                            escape(info.get("error", "nicht bestätigt")), "err"), 402)
    if info.get("depth") == "partner":
        return RedirectResponse(url=f"/report?session_id={session_id}&depth=partner",
                                status_code=303)
    if not claim_session(session_id):
        return HTMLResponse(done_html(session_id))

    try:
        # Accept DD.MM.YYYY (new default), YYYY-MM-DD, DD-MM-YYYY, MM/DD/YYYY
        date = date.strip()
        if b_day.strip() and b_month.strip() and b_year.strip():
            date = f"{int(b_day):02d}.{int(b_month):02d}.{int(b_year):04d}"
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
                                 loc.get("label", city), name, gender)
        if "/" in str(loc.get("iana", "")):
            chart["meta"]["tzname"] = loc["iana"]
        # Optional user context — used only for interpretation, never for calculation
        chart["meta"]["occupation"] = occupation.strip()
        chart["meta"]["context"] = context.strip()
        # Bis zu 3 individuelle Kundenfragen (Premium): eigenes Kapitel in der
        # Deutung; Varga-/Beziehungskapitel werden dafür kompakter (ai_report).
        _qs = [q.strip() for q in (q1, q2, q3) if q and q.strip()][:3]
        if _qs and info.get("depth") == "premium":
            chart["meta"]["questions"] = _qs
        # Lebensspannen-Checkliste im Medizin-Tab: NUR im Test-Modus (Betreiber),
        # niemals in bezahlten Kundenberichten.
        chart["show_lifespan"] = bool(info.get("test"))
        depth = info["depth"]
        text = ai_report.generate_interpretation(chart, lang=lang, depth=depth)
        title = "Persönliche Deutung" if lang == "de" else "Personal Reading"
        # HTML-Ansicht ist das interaktive Kernprodukt — zuerst bauen, damit sie
        # auch vorliegt, wenn danach der PDF-Renderer scheitert.
        _ups = _frage_upsell_url(session_id) if info.get("depth") == "premium" else None
        html_view = chart_html.build_html(chart, interpretation=text,
                                          interpretation_title=title, upsell_url=_ups)
        # PDF isoliert: ein Fehler hier verwirft die schon erzeugte Deutung/HTML
        # NICHT — der Kunde bekommt die Ansicht, das PDF kann später neu erzeugt
        # werden, statt dass der ganze (teure) Bericht verloren geht.
        pdf = pdf_tech = None
        try:
            pdf = pdf_report.build_pdf(chart, interpretation=text,
                                       interpretation_title=title, variant="customer")
            pdf_tech = pdf_report.build_pdf(chart, interpretation=text,
                                            interpretation_title=title, variant="full")
        except Exception:
            _traceback.print_exc(file=_sys.stderr)
    except Exception as e:
        # un-claim so the customer can retry
        con = _db(); con.execute("DELETE FROM deliveries WHERE session_id=?", (session_id,))
        con.commit(); con.close()
        import traceback, sys
        traceback.print_exc(file=sys.stderr)
        return HTMLResponse(msg_html("Etwas ist schiefgelaufen",
                            "Bitte versuche es erneut oder melde dich bei uns — falls es erneut auftritt, kontaktiere uns bitte.",
                            "err"), 500)

    fn = f"{info['label'].replace(' ', '_')}.pdf"
    _HTML_CACHE[session_id] = html_view
    if pdf is not None:
        _PDF_CACHE[session_id] = (pdf, fn)
    if pdf_tech is not None:
        _PDF_CACHE[session_id + "-technik"] = (
            pdf_tech, fn.replace(".pdf", "_Technische_Daten.pdf"))
    # Cache raw birth params so Varshaphala can be recomputed for any age AND so
    # /view can rebuild the interactive view after a cache loss without a new LLM
    # call (interpretation + title + gender stored alongside the birth data).
    _CHART_CACHE[session_id] = {
        "y": y, "mo": mo, "d": d, "hh": hh, "mm": mm,
        "lat": loc["lat"], "lon": loc["lon"], "offset": loc["offset"],
        "label": loc.get("label", city), "name": name, "gender": gender,
        "iana": loc.get("iana", ""),
        "natal_sun_sid": chart.get("lons", {}).get("Sun"),
        "natal_lagna_si": chart.get("lagna_idx"),
        "birth_year": y,
        "interpretation": text, "interp_title": title, "depth": depth, "pdf_fn": fn,
    }
    # Redirect directly to the HTML view — it has a PDF download button built in
    return RedirectResponse(url=f"/view/{session_id}", status_code=303)




# ── Partnerschafts-Bericht (Synastrie, depth="partner") ──────────────────────
def _parse_date_de(date: str):
    """DD.MM.YYYY / YYYY-MM-DD / DD-MM-YYYY → (y, mo, d)."""
    date = (date or "").strip()
    if "." in date:
        p = date.split("."); return int(p[2]), int(p[1]), int(p[0])
    if "-" in date:
        p = date.split("-")
        if len(p[0]) == 4: return int(p[0]), int(p[1]), int(p[2])
        return int(p[2]), int(p[1]), int(p[0])
    raise ValueError(f"Unbekanntes Datumsformat: {date}")


def _person_fields(prefix: str, title: str) -> str:
    """Formularblock für eine Person (Name, Datum, Zeit, Ort, Geschlecht)."""
    return f"""
<div style="border:1px solid {PAL['line']};border-radius:6px;padding:14px 16px;margin:14px 0">
<div class="ey"><span class="dot">◆</span> {title}</div>
<label>Name</label><input name="{prefix}_name" required>
<div class="row">
  <div><label>Geburtsdatum</label>
    <input name="{prefix}_date" inputmode="numeric" maxlength="10" oninput="fmtDate(this)"
      placeholder="TT.MM.JJJJ · z.B. 24.08.1957" autocomplete="off" required></div>
  <div><label>Geburtszeit</label><input type="time" name="{prefix}_time" value="12:00"></div>
</div>
<label>Geburtsort (Stadt, Land)</label>
<input name="{prefix}_city" placeholder="z.B. Zürich, Schweiz" required>
<label>Geschlecht <span style="color:{PAL['muted']};font-weight:400">(optional)</span></label>
<select name="{prefix}_gender"><option value="">—</option>
<option value="weiblich">weiblich</option><option value="männlich">männlich</option>
<option value="divers">divers</option></select>
</div>"""


def partner_form_html(session_id: str, info: dict) -> str:
    test = info.get("test")
    banner = ('<p class="muted" style="background:rgba(201,168,76,.1);border:1px dashed #c9a84c;'
              'padding:8px 12px;border-radius:4px">⚙ TEST-MODUS – keine Zahlung nötig.</p>'
              if test else "")
    return _page("Geburtsdaten – " + info["label"], f"""
<div class="ey"><span class="dot">◆</span> {escape(info['label'])}</div>
<h1>Zwei Horoskope, eine Analyse</h1>{banner}
<p>Gib die Geburtsdaten beider Personen ein – wir berechnen beide Horoskope,
die vollständige Aṣṭakūṭa-Analyse (36 Guṇas), Mangal Doṣa, Vedha/Rajju und
erstellen eine ausführliche Deutung eurer Verbindung.</p>
<form method="post" action="/partner-generate" onsubmit="document.getElementById('working').style.display='block';var b=this.querySelector('button[type=submit]');b.textContent='⏳ Bericht wird erstellt…';setTimeout(function(){{b.disabled=true;}},50);">
<input type="hidden" name="session_id" value="{escape(session_id)}">
{_person_fields("a", "Person A")}
{_person_fields("b", "Person B")}
<p class="muted" style="font-size:.82rem">Hinweis: Die klassischen Kūṭa-Faktoren
mit Geschlechtsbezug (z.B. Strī-Dīrgha) folgen der Konvention
Person A = männlich, Person B = weiblich. Bei gleichgeschlechtlichen Paaren
werden diese Einzelfaktoren entsprechend relativiert gedeutet.</p>
<div><label>Sprache</label><select name="lang"><option value="de">Deutsch</option>
<option value="en">English</option></select></div>
<button type="submit">Partner-Bericht erstellen</button>
</form>
<div id="working" style="display:none;margin-top:18px;padding:14px;background:rgba(201,168,76,.1);border:1px solid #c9a84c;border-radius:6px;text-align:center;font-size:.9rem;color:#c9a84c">
  ⏳ Berechnung läuft — zwei Horoskope, Kompatibilität, KI-Deutung, PDF.<br>
  <small>Dies dauert 1–3 Minuten. Bitte die Seite nicht schliessen.</small>
</div>""")


@app.post("/partner-generate")
def partner_generate(request: Request,
                     session_id: str = Form(...), lang: str = Form("de"),
                     a_name: str = Form(...), a_date: str = Form(...),
                     a_time: str = Form("12:00"), a_city: str = Form(...),
                     a_gender: str = Form(""),
                     b_name: str = Form(...), b_date: str = Form(...),
                     b_time: str = Form("12:00"), b_city: str = Form(...),
                     b_gender: str = Form("")):
    if not _rate_ok(_client_ip(request), limit=10, window=600.0):
        return HTMLResponse(msg_html("Zu viele Anfragen",
                            "Bitte warte einen Moment und versuche es erneut.", "err"), 429)
    _maybe_sweep()
    ok, info = get_paid_session(session_id, want_depth="partner")
    if not ok:
        return HTMLResponse(msg_html("Zahlung prüfen",
                            escape(info.get("error", "nicht bestätigt")), "err"), 402)
    if info.get("depth") != "partner":
        return HTMLResponse(msg_html("Falscher Bericht",
                            "Diese Session gehört nicht zu einem "
                            "Partnerschafts-Bericht.", "err"), 400)
    if not claim_session(session_id):
        return HTMLResponse(done_html(session_id))

    try:
        def _build(name, date_s, time_s, city, gender, who):
            y, mo, d = _parse_date_de(date_s)     # accepts YYYY-MM-DD (native date) + DD.MM.YYYY
            hh, mm = (int(x) for x in (time_s or "12:00").split(":"))
            loc = E.resolve_location(city, y, mo, d, hh, mm)
            if not loc:
                raise ValueError(f"Ort von {who} nicht gefunden — bitte "
                                 f"Stadt und Land prüfen.")
            ch = E.generate_chart(y, mo, d, hh, mm, loc["lat"], loc["lon"],
                                  loc["offset"], loc.get("label", city),
                                  name, gender)
            if "/" in str(loc.get("iana", "")):
                ch["meta"]["tzname"] = loc["iana"]
            return ch, loc, (y, mo, d, hh, mm)

        chart, loc_a, (y, mo, d, hh, mm) = _build(
            a_name, a_date, a_time, a_city, a_gender, "Person A")
        chart_b, _loc_b, _ = _build(
            b_name, b_date, b_time, b_city, b_gender, "Person B")

        # Vertrag von ai_report._build_partner_facts:
        chart["partner_chart"] = chart_b
        chart["compatibility"] = E.compute_compatibility(chart, chart_b)
        chart["show_lifespan"] = bool(info.get("test"))

        text = ai_report.generate_interpretation(chart, lang=lang, depth="partner")
        title = ("Partnerschafts-Deutung" if lang == "de"
                 else "Relationship Reading")
        pdf = pdf_report.build_pdf(chart, interpretation=text,
                                   interpretation_title=title, variant="customer")
        pdf_tech = pdf_report.build_pdf(chart, interpretation=text,
                                        interpretation_title=title, variant="full")
    except Exception as e:
        con = _db(); con.execute("DELETE FROM deliveries WHERE session_id=?", (session_id,))
        con.commit(); con.close()
        import traceback, sys
        traceback.print_exc(file=sys.stderr)
        return HTMLResponse(msg_html("Etwas ist schiefgelaufen",
                            "Bitte versuche es erneut oder melde dich bei uns — falls es erneut auftritt, kontaktiere uns bitte.",
                            "err"), 500)

    fn = f"{info['label'].replace(' ', '_')}.pdf"
    html_view = chart_html.build_html(chart, interpretation=text,
                                      interpretation_title=title)
    _PDF_CACHE[session_id] = (pdf, fn)
    _PDF_CACHE[session_id + "-technik"] = (
        pdf_tech, fn.replace(".pdf", "_Technische_Daten.pdf"))
    _HTML_CACHE[session_id] = html_view
    # Rohdaten von Person A cachen — Varshaphala-/Kompatibilitäts-Tab im Viewer
    _CHART_CACHE[session_id] = {
        "y": y, "mo": mo, "d": d, "hh": hh, "mm": mm,
        "lat": loc_a["lat"], "lon": loc_a["lon"], "offset": loc_a["offset"],
        "label": loc_a.get("label", a_city), "name": a_name,
        "natal_sun_sid": chart.get("lons", {}).get("Sun"),
        "natal_lagna_si": chart.get("lagna_idx"),
        "birth_year": y,
    }
    return RedirectResponse(url=f"/view/{session_id}",
                            status_code=303)


# ── Prāśna (Horary) ──────────────────────────────────────────────────────────
def _build_janma_context(birth_date: str, birth_time: str, birth_city: str,
                         name: str, gender: str):
    """(janma_context, error_html). Berechnet den kompakten Geburts-Kontext
    für Prāśna Plus; error_html ist gesetzt, wenn Eingaben fehlerhaft sind."""
    try:
        bd = birth_date.strip()
        if "." in bd:
            d3, m3, y3 = (int(x) for x in bd.split("."))
        else:
            parts = bd.split("-")
            y3, m3, d3 = int(parts[0]), int(parts[1]), int(parts[2])
        bt = (birth_time or "12:00").strip()
        bh, bm = (int(x) for x in bt.split(":")[:2])
        bloc = E.resolve_location(birth_city.strip(), y3, m3, d3, bh, bm)
        if not bloc:
            return None, msg_html(
                "Geburtsort nicht gefunden",
                "Der Geburtsort für den Horoskop-Abgleich wurde nicht "
                "erkannt. Bitte Stadt und Land prüfen — oder die "
                "Geburtsfelder leer lassen.", "err")
        janma = E.generate_chart(y3, m3, d3, bh, bm,
                                 bloc["lat"], bloc["lon"], bloc["offset"],
                                 bloc.get("label", birth_city), name, gender)
        cur = janma["dashas"]["current"]
        act = next((md for md in janma["dashas"]["mahadashas"]
                    if md["active"]), None)
        lords = {}
        for h in range(1, 13):
            lp = E.SIGN_LORDS[janma["houses"][h]]
            rec = janma["planets"].get(lp, {})
            lords[f"house_{h}"] = {
                "lord": lp, "goes_to_house": rec.get("house"),
                "dignity": rec.get("dignity"),
                "afflictions": (janma.get("afflictions") or {}).get(lp, []),
            }
        return {
            "birth": janma["meta"]["birth"],
            "lagna": f"{janma['lagna']} {janma['lagna_pos']}",
            "moon_nakshatra": (f"{janma['planets']['Moon']['nakshatra']} "
                               f"Pada {janma['planets']['Moon']['pada']}"),
            "vimshottari_current": cur,
            "mahadasha_ends": (act["end"].strftime("%d %b %Y") if act else None),
            "house_lords": lords,
        }, None
    except (ValueError, KeyError, IndexError):
        return None, msg_html(
            "Geburtsdaten unvollständig",
            "Die optionalen Geburtsangaben konnten nicht gelesen werden. "
            "Bitte prüfen — oder alle drei Felder leer lassen.", "err")


def _frage_upsell_url(anchor_sid: str):
    """Stripe-Payment-Link für die Zusatzfrage zum Bericht, verankert am
    ursprünglichen Reading via client_reference_id. Env: REPORT_FRAGE_URL."""
    base = os.environ.get("REPORT_FRAGE_URL", "").strip()
    if not base:
        return None
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}client_reference_id={anchor_sid}"


def _prasna_upsell_url(anchor_sid: str):
    """Stripe-Payment-Link für die Zusatzfrage (CHF 18), verankert am
    ursprünglichen Prāśna via client_reference_id. Env: PRASNA_FOLLOWUP_URL."""
    base = os.environ.get("PRASNA_FOLLOWUP_URL", "").strip()
    if not base:
        return None
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}client_reference_id={anchor_sid}"


def _prasna_form_html(session_id: str, info: dict) -> str:
    now = _dt.datetime.now()
    test = info.get("test")
    banner = ('<p class="muted" style="background:rgba(201,168,76,.1);border:1px dashed #c9a84c;'
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
</div>
<label>Hintergrund zur Frage <span style="color:{PAL['muted']};font-weight:400">(optional, für gezieltere Antwort)</span></label>
<textarea name="context" rows="2" placeholder="z.B. worum es genau geht, seit wann die Situation besteht …" style="width:100%;padding:11px 12px;border:1px solid {PAL['line']};border-radius:4px;background:{PAL['paper2']};color:{PAL['ink']};font-size:1rem;font-family:inherit;resize:vertical"></textarea>
<div class="row">
  <div><label>Datum</label>
  <input type="date" name="date" min="1900-01-01" max="2030-12-31"
    value="{now.strftime('%Y-%m-%d')}" required></div>
  <div><label>Uhrzeit</label>
  <input type="time" name="time" value="{now.strftime('%H:%M')}"></div>
</div>
<div><label>Sprache</label><select name="lang">
  <option value="de">Deutsch</option>
  <option value="en">English</option>
</select></div>

<div style="margin-top:22px;padding:14px;border:1px dashed {PAL['gold']};border-radius:6px">
  <label style="margin-top:0">Abgleich mit dem Geburtshoroskop
    <span style="color:{PAL['muted']};font-weight:400">(optional — Prāśna Plus)</span></label>
  <p class="muted" style="margin:4px 0 10px;font-size:.85rem">
    Mit Geburtsdaten prüft die Deutung zusätzlich, ob deine aktuelle
    Lebensphase (Daśā) die Antwort des Prāśna stützt. Geburtsdatum und -ort
    ausfüllen — oder beide leer lassen.</p>
  <div class="row">
    <div><label>Geburtsdatum</label>
      <input name="birth_date" inputmode="numeric" maxlength="10" oninput="fmtDate(this)"
        placeholder="TT.MM.JJJJ · z.B. 24.08.1957" autocomplete="off"></div>
    <div><label>Geburtszeit</label>
      <input type="time" name="birth_time"></div>
  </div>
  <label>Geburtsort (Stadt, Land)</label>
  <input name="birth_city" placeholder="z.B. Liestal, Schweiz">
</div>
<button type="submit">Prāśna berechnen</button>
</form>
<div id="pw" style="display:none;margin-top:18px;padding:14px;background:rgba(201,168,76,.1);
  border:1px solid {PAL['gold']};border-radius:6px;text-align:center;
  font-size:.9rem;color:{PAL['muted']}">
  ⏳ Berechnung läuft — Planetenpositionen, Signifikatoren, KI-Deutung.<br>
  <small>Dies dauert 1–2 Minuten. Bitte die Seite nicht schliessen.</small>
</div>
<p class="muted">Das Horoskop wird für den angegebenen Moment berechnet.
Je aufrichtiger und drängender die Frage, desto klarer die Antwort.</p>""")


@app.get("/prasna", response_class=HTMLResponse)
def prasna_page(session_id: str = "", key: str = ""):
    if not session_id:
        if _test_access(key):
            session_id = _test_prefix("PRASNA") + _dt.datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
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
    request: Request,
    session_id: str = Form(...),
    question: str = Form(...),
    name: str = Form(""),
    city: str = Form(...),
    date: str = Form(...),
    time: str = Form("12:00"),
    lang: str = Form("de"),
    gender: str = Form(""),
    occupation: str = Form(""),
    context: str = Form(""),
    birth_date: str = Form(""),
    birth_time: str = Form(""),
    birth_city: str = Form(""),
    bb_day: str = Form(""), bb_month: str = Form(""), bb_year: str = Form(""),
):
    if not _rate_ok(_client_ip(request), limit=10, window=600.0):
        return HTMLResponse(msg_html("Zu viele Anfragen",
                            "Bitte warte einen Moment und versuche es erneut.", "err"), 429)
    _maybe_sweep()
    ok, info = get_paid_session(session_id, want_depth="prasna")
    if not ok:
        return HTMLResponse(msg_html("Zahlung prüfen",
                            escape(info.get("error", "nicht bestätigt")), "err"), 402)
    if not claim_session(session_id):
        return HTMLResponse(done_html(session_id))
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
                                 loc.get("label", city), name or "Prāśna", gender)
        if "/" in str(loc.get("iana", "")):
            chart["meta"]["tzname"] = loc["iana"]
        chart["meta"]["occupation"] = occupation.strip()
        chart["meta"]["context"] = context.strip()
        chart["prasna_question"] = question
        chart["prasna_mode"] = True

        # ── Prāśna Plus: optionaler Abgleich mit dem Geburtshoroskop ────────
        if bb_day.strip() and bb_month.strip() and bb_year.strip():
            try:
                birth_date = f"{int(bb_day):02d}.{int(bb_month):02d}.{int(bb_year):04d}"
            except ValueError:
                return HTMLResponse(msg_html(
                    "Geburtsdaten unvollständig",
                    "Geburts-Tag, -Monat und -Jahr bitte als Zahlen angeben — "
                    "oder alle Felder leer lassen.", "err"), 400)
        if birth_date.strip() and birth_city.strip():
            jc, err = _build_janma_context(birth_date, birth_time, birth_city,
                                           name, gender)
            if err:
                return HTMLResponse(err, status_code=400)
            chart["janma_context"] = jc

        text = ai_report.generate_interpretation(chart, lang=lang, depth="prasna")
        title = "Prāśna-Deutung" if lang == "de" else "Prāśna Reading"
        pdf = pdf_report.build_pdf(chart, interpretation=text,
                                   interpretation_title=title, variant="customer")
        pdf_tech = pdf_report.build_pdf(chart, interpretation=text,
                                        interpretation_title=title, variant="full")
        html_view = chart_html.build_html(chart, interpretation=text,
                                          interpretation_title=title,
                                          upsell_url=_prasna_upsell_url(session_id))
    except Exception as e:
        # un-claim so the customer can retry
        con = _db(); con.execute("DELETE FROM deliveries WHERE session_id=?", (session_id,))
        con.commit(); con.close()
        import traceback, sys
        traceback.print_exc(file=sys.stderr)
        return HTMLResponse(msg_html("Fehler",
                            "Bitte erneut versuchen — falls es erneut auftritt, kontaktiere uns bitte.", "err"), 500)

    fn = f"Prasna_{y}{mo:02d}{d:02d}.pdf"
    # Frage-Moment cachen, damit Zusatzfragen dasselbe Prāśna-Chart nutzen können
    _CHART_CACHE[session_id] = {
        "prasna": True, "y": y, "mo": mo, "d": d, "hh": hh, "mm": mm,
        "lat": loc["lat"], "lon": loc["lon"], "offset": loc["offset"],
        "label": loc.get("label", city), "name": name, "gender": gender,
        "iana": loc.get("iana", ""), "question": question,
        "birth_date": birth_date.strip(), "birth_time": birth_time.strip(),
        "birth_city": birth_city.strip(),
    }
    _PDF_CACHE[session_id]  = (pdf, fn)
    _PDF_CACHE[session_id + "-technik"] = (
        pdf_tech, fn.replace(".pdf", "_Technische_Daten.pdf"))
    _HTML_CACHE[session_id] = html_view
    return RedirectResponse(url=f"/view/{session_id}", status_code=303)



# ── Varshaphala (age-dependent, AJAX) ────────────────────────────────────────
from fastapi.responses import JSONResponse

@app.get("/varshaphala/{session_id}/{age}")
def varshaphala_age(request: Request, session_id: str, age: int,
                    sun: float = None, lagna: int = None,
                    mo: int = None, d: int = None,
                    lat: float = None, lon: float = None, by: int = None):
    """Recompute Varshaphala for a given age. Birth params come from query args
    (embedded in the page, so they survive a spin-down) or fall back to the disk
    cache. After a spin-down wipes the session store, the paid session is
    re-verified via Stripe so the tab keeps working without a persistent disk."""
    if not _rate_ok(_client_ip(request), limit=60, window=60.0):
        return JSONResponse({"error": "Zu viele Anfragen — bitte kurz warten."},
                            status_code=429)
    have_q = all(v is not None for v in (sun, lagna, mo, d, lat, lon, by))
    # Access control: a session we know, OR — cache gone after a spin-down — a
    # live paid Stripe session (never anonymous compute).
    if not _is_known_session(session_id):
        authed = _is_test_session(session_id) or (have_q and get_paid_session(session_id)[0])
        if not authed:
            return JSONResponse({"error": "Kein Zugriff."}, status_code=403)
    # Prefer explicit query params (robust); fall back to disk cache
    if have_q:
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
        return JSONResponse({"error": "Berechnungsfehler — bitte prüfe die Eingaben oder versuche es später erneut."})

def _norm_gender(g: str) -> str:
    """'männlich'/'male'/'m' → 'male'; 'weiblich'/'frau'/'female'/'f'/'w' → 'female';
    else '' (unknown / 'divers')."""
    g = (g or "").strip().lower()
    if g.startswith(("m",)):        # männlich / male / m
        return "male"
    if g.startswith(("w", "f")):    # weiblich / frau / female / f
        return "female"
    return ""


@app.get("/compatibility/{session_id}")
def compatibility(request: Request, session_id: str,
                  date: str = "", time: str = "12:00", city: str = "",
                  gender: str = "",
                  a_by: int = None, a_mo: int = None, a_d: int = None,
                  a_hh: int = None, a_mm: int = None,
                  a_lat: float = None, a_lon: float = None, a_off: float = None,
                  a_name: str = "", a_gender: str = ""):
    """Compute Ashtakūṭa + Mangal Dosha + house overlays between the report's
    chart (person A) and a second person B (from query args). `gender` is person
    B's gender; person A's is from the cached report or the a_* fallback. The
    gender-directional kūṭas (Varna, Strī-Dīrgha, Rāśi) use the real genders when
    both are known and distinct, otherwise A = groom.

    Person A is rebuilt from the disk cache when present; after a server
    spin-down wipes it, the a_* params embedded in the report page are used —
    the paid session is then re-verified via Stripe, so compatibility keeps
    working across restarts without a persistent disk."""
    from fastapi.responses import JSONResponse
    if not _rate_ok(_client_ip(request), limit=30, window=60.0):
        return JSONResponse({"error": "Zu viele Anfragen — bitte kurz warten."},
                            status_code=429)
    try:
        params = _CHART_CACHE.get(session_id)
        have_fallback = all(v is not None for v in
                            (a_by, a_mo, a_d, a_hh, a_mm, a_lat, a_lon, a_off))
        # Authorisation: a session we already know, OR \u2014 when the cache is gone
        # after a spin-down \u2014 a live paid Stripe session (survives disk loss).
        if not _is_known_session(session_id):
            authed = _is_test_session(session_id)
            if not authed and have_fallback:
                authed = get_paid_session(session_id)[0]
            if not authed:
                return JSONResponse({"error": "Kein Zugriff."}, status_code=403)
        # Person A: from the cache when present, else the page's a_* params.
        if params:
            a = E.generate_chart(
                int(params["birth_year"]), int(params["mo"]), int(params["d"]),
                int(params.get("hh", 12)), int(params.get("mm", 0)),
                float(params["lat"]), float(params["lon"]), float(params.get("offset", 0.0)),
                params.get("label", ""), params.get("name", "Person A"))
            a_gender_eff = params.get("gender", "")
        elif have_fallback:
            a = E.generate_chart(
                int(a_by), int(a_mo), int(a_d), int(a_hh), int(a_mm),
                float(a_lat), float(a_lon), float(a_off), "", a_name or "Person A")
            a_gender_eff = a_gender
        else:
            return JSONResponse({"error": "Sitzung abgelaufen \u2014 bitte Bericht neu erstellen."})
        # Parse person B's date (accept DD.MM.YYYY / YYYY-MM-DD / DD-MM-YYYY)
        date = (date or "").strip()
        if not date or not city.strip():
            return JSONResponse({"error": "Bitte Geburtsdatum und Ort der zweiten Person angeben."})
        if "." in date:
            p = date.split("."); d2, mo2, y2 = int(p[0]), int(p[1]), int(p[2])
        elif "-" in date:
            p = date.split("-")
            if len(p[0]) == 4: y2, mo2, d2 = int(p[0]), int(p[1]), int(p[2])
            else:              d2, mo2, y2 = int(p[0]), int(p[1]), int(p[2])
        else:
            return JSONResponse({"error": f"Unbekanntes Datumsformat: {date}"})
        hh2, mm2 = (int(x) for x in (time or "12:00").split(":"))
        loc = E.resolve_location(city, y2, mo2, d2, hh2, mm2)
        if not loc:
            return JSONResponse({"error": "Ort der zweiten Person nicht gefunden \u2014 bitte Stadt und Land pr\u00fcfen."})
        b = E.generate_chart(y2, mo2, d2, hh2, mm2, loc["lat"], loc["lon"],
                             loc["offset"], loc.get("label", city), "Person B")
        # Determine which chart is the groom for the gender-directional kūṭas.
        # Only override the A=groom default when both genders are known AND
        # distinct (a hetero pairing); otherwise keep A=groom (same-sex/unknown).
        ga = _norm_gender(a_gender_eff)
        gb = _norm_gender(gender)
        male = "b" if (ga == "female" and gb == "male") else "a"
        comp = E.compute_compatibility(a, b, male=male)
        comp["person_b_label"] = loc.get("label", city)
        comp["gender_resolved"] = bool(ga and gb and ga != gb)  # True = real genders used
        comp["male_role"] = male                                 # 'a'=owner groom, 'b'=owner bride
        return JSONResponse(comp)
    except Exception as e:
        import traceback, sys
        traceback.print_exc(file=sys.stderr)
        return JSONResponse({"error": "Berechnungsfehler — bitte prüfe die Eingaben oder versuche es später erneut."})


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


def _regenerate_pdf(session_id: str, variant: str = ""):
    """Rebuild a report PDF from cached birth params + interpretation when the
    cached PDF file is gone but the chart cache survived (eviction, or a PDF build
    that failed at generation time). No new LLM call. Standard single-person
    reports only; returns (pdf_bytes, filename) or None."""
    params = _CHART_CACHE.get(session_id)
    if not params or not params.get("interpretation"):
        return None
    if params.get("prasna") or params.get("partner"):
        return None
    try:
        chart = E.generate_chart(
            int(params["y"]), int(params["mo"]), int(params["d"]),
            int(params.get("hh", 12)), int(params.get("mm", 0)),
            float(params["lat"]), float(params["lon"]), float(params.get("offset", 0.0)),
            params.get("label", ""), params.get("name", ""), params.get("gender", ""))
        if "/" in str(params.get("iana", "")):
            chart["meta"]["tzname"] = params["iana"]
        vk = "full" if variant == "technik" else "customer"
        pdf = pdf_report.build_pdf(
            chart, interpretation=params["interpretation"],
            interpretation_title=params.get("interp_title", "Persönliche Deutung"),
            variant=vk)
        base = params.get("pdf_fn", "AstroVeda_Bericht.pdf")
        fn = base.replace(".pdf", "_Technische_Daten.pdf") if variant == "technik" else base
        key = session_id + "-technik" if variant == "technik" else session_id
        _PDF_CACHE[key] = (pdf, fn)          # re-cache so the next hit is cheap
        return (pdf, fn)
    except Exception:
        _traceback.print_exc(file=_sys.stderr)
        return None


@app.get("/download/{session_id}")
def download_pdf(session_id: str, variant: str = ""):
    key = session_id + "-technik" if variant == "technik" else session_id
    entry = _PDF_CACHE.pop(key, None)
    if not entry and variant == "technik":
        entry = _PDF_CACHE.pop(session_id, None)   # older reports: only one PDF
    if not entry:
        entry = _regenerate_pdf(session_id, variant)   # rebuild if the file was evicted
    if not entry:
        return HTMLResponse(msg_html("Link abgelaufen",
                            "Der Download-Link ist nicht mehr gültig. "
                            "Bitte wende dich an uns.", "err"), 404)
    pdf, fn = entry
    return StreamingResponse(BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{fn}"'})


def _regenerate_view(session_id: str):
    """Rebuild the interactive HTML view from cached birth params + interpretation
    when the rendered HTML is gone but the chart params survived. No new LLM call.
    Returns the HTML string, or None if not recoverable (partner/praśna or missing
    fields). Standard single-person reports only — the common case."""
    params = _CHART_CACHE.get(session_id)
    if not params or not params.get("interpretation"):
        return None
    if params.get("prasna") or params.get("partner"):
        return None            # complex state (2nd chart / praśna mode) — not rebuilt here
    try:
        chart = E.generate_chart(
            int(params["y"]), int(params["mo"]), int(params["d"]),
            int(params.get("hh", 12)), int(params.get("mm", 0)),
            float(params["lat"]), float(params["lon"]), float(params.get("offset", 0.0)),
            params.get("label", ""), params.get("name", ""), params.get("gender", ""))
        if "/" in str(params.get("iana", "")):
            chart["meta"]["tzname"] = params["iana"]
        _ups = _frage_upsell_url(session_id) if params.get("depth") == "premium" else None
        html = chart_html.build_html(
            chart, interpretation=params["interpretation"],
            interpretation_title=params.get("interp_title", "Persönliche Deutung"),
            upsell_url=_ups)
        _HTML_CACHE[session_id] = html      # re-cache so the next hit is cheap
        return html
    except Exception:
        _traceback.print_exc(file=_sys.stderr)
        return None


@app.get("/view/{session_id}", response_class=HTMLResponse)
def view_chart(session_id: str):
    html = _HTML_CACHE.get(session_id)
    if not html:
        html = _regenerate_view(session_id)   # best-effort rebuild from chart cache
    if not html:
        return HTMLResponse(msg_html("Ansicht abgelaufen",
                            "Die interaktive Ansicht ist nicht mehr verfügbar. "
                            "Bitte erstelle einen neuen Bericht.", "err"), 404)
    return HTMLResponse(html)  # keep in cache (not popped)

# ── Zusatzfrage zum Bericht: neue Frage an das GEBURTShoroskop ───────────────
@app.get("/report-frage", response_class=HTMLResponse)
def report_frage(session_id: str = "", ref: str = ""):
    if not session_id:
        return HTMLResponse(msg_html("Kein Zugang", "Fehlende Session-ID.",
                                     "err"), 400)
    if already_done(session_id):
        return HTMLResponse(done_html(session_id))
    ok, info = get_paid_session(session_id, want_depth="frage")
    if not ok:
        return HTMLResponse(msg_html("Kein Zugang",
                            escape(info.get("error", "Zahlung nicht bestätigt.")),
                            "err"), 403)
    anchor = info.get("ref") or (ref if info.get("test") else "")
    params = _CHART_CACHE.get(anchor) if anchor else None
    if not params or params.get("prasna"):
        return HTMLResponse(msg_html(
            "Ursprünglicher Bericht nicht gefunden",
            "Die Zusatzfrage bezieht sich auf einen bestehenden "
            "AstroVeda-Bericht, der auf dem Server nicht mehr verfügbar ist. "
            "Bitte melde dich bei uns — wir helfen sofort weiter.", "err"), 404)
    banner = ('<p class="muted" style="background:rgba(201,168,76,.1);border:1px dashed '
              '#c9a84c;padding:8px 12px;border-radius:4px">⚙ TEST-MODUS – '
              'keine Zahlung nötig.</p>' if info.get("test") else "")
    return HTMLResponse(_page("Zusatzfrage zu deinem Bericht", f"""
<div class="ey"><span class="dot">◆</span> Zusatzfrage · dein Geburtshoroskop</div>
<h1>Deine Zusatzfrage</h1>{banner}
<p>Sie wird an <b>deinem Geburtshoroskop</b> gedeutet
({escape(str(params.get('name','')))} · {escape(str(params.get('label','')))}) —
mit Blick auf die passenden Häuser, Kārakas und deine aktuelle Daśā-Zeit.</p>
<form method="post" action="/report-frage-generate"
  onsubmit="var b=this.querySelector('button');b.textContent='⏳ Wird gedeutet…';setTimeout(function(){{b.disabled=true;}},50);">
<input type="hidden" name="session_id" value="{escape(session_id, quote=True)}">
<input type="hidden" name="ref" value="{escape(anchor, quote=True)}">
<label>Deine Frage</label>
<input name="question" placeholder="z.B. Soll ich das Stellenangebot annehmen?" required>
<div><label>Sprache</label><select name="lang">
  <option value="de">Deutsch</option><option value="en">English</option>
</select></div>
<button type="submit">Frage deuten lassen</button>
</form>"""))


@app.post("/report-frage-generate", response_class=HTMLResponse)
def report_frage_generate(request: Request,
                          session_id: str = Form(...), ref: str = Form(...),
                          question: str = Form(...), lang: str = Form("de")):
    if not _rate_ok(_client_ip(request), limit=10, window=600.0):
        return HTMLResponse(msg_html("Zu viele Anfragen",
                            "Bitte warte einen Moment und versuche es erneut.", "err"), 429)
    _maybe_sweep()
    ok, info = get_paid_session(session_id, want_depth="frage")
    if not ok:
        return HTMLResponse(msg_html("Kein Zugang",
                            escape(info.get("error", "Zahlung nicht bestätigt.")),
                            "err"), 403)
    anchor = info.get("ref") or (ref if info.get("test") else "")
    params = _CHART_CACHE.get(anchor) if anchor else None
    if not params or params.get("prasna"):
        return HTMLResponse(msg_html(
            "Ursprünglicher Bericht nicht gefunden",
            "Der zugehörige Bericht ist auf dem Server nicht mehr verfügbar. "
            "Bitte melde dich bei uns.", "err"), 404)
    if not claim_session(session_id):
        return HTMLResponse(done_html(session_id))
    try:
        chart = E.generate_chart(params["y"], params["mo"], params["d"],
                                 params["hh"], params["mm"],
                                 params["lat"], params["lon"], params["offset"],
                                 params["label"], params.get("name", ""),
                                 params.get("gender", ""))
        if "/" in str(params.get("iana", "")):
            chart["meta"]["tzname"] = params["iana"]
        chart["meta"]["questions"] = [question.strip()]
        text = ai_report.generate_interpretation(chart, lang=lang, depth="frage")
        title = ("Zusatzfrage zu deinem Bericht" if lang == "de"
                 else "Follow-up question to your report")
        pdf = pdf_report.build_pdf(chart, interpretation=text,
                                   interpretation_title=title, variant="customer")
        pdf_tech = pdf_report.build_pdf(chart, interpretation=text,
                                        interpretation_title=title, variant="full")
        html_view = chart_html.build_html(chart, interpretation=text,
                                          interpretation_title=title,
                                          upsell_url=_frage_upsell_url(anchor))
    except Exception as e:
        con = _db(); con.execute("DELETE FROM deliveries WHERE session_id=?", (session_id,))
        con.commit(); con.close()
        import traceback, sys
        traceback.print_exc(file=sys.stderr)
        return HTMLResponse(msg_html("Fehler bei der Berechnung",
                            "Ein interner Fehler ist aufgetreten — bitte erneut versuchen oder uns kontaktieren.", "err"), 500)
    fn = "Zusatzfrage_zum_Bericht.pdf"
    _PDF_CACHE[session_id] = (pdf, fn)
    _PDF_CACHE[session_id + "-technik"] = (
        pdf_tech, fn.replace(".pdf", "_Technische_Daten.pdf"))
    _HTML_CACHE[session_id] = html_view
    return RedirectResponse(url=f"/view/{session_id}",
                            status_code=303)


# ── Prāśna-Zusatzfrage (CHF 18): neue Frage an dasselbe Prāśna-Chart ─────────
@app.get("/prasna-followup", response_class=HTMLResponse)
def prasna_followup(session_id: str = "", ref: str = ""):
    if not session_id:
        return HTMLResponse(msg_html("Kein Zugang", "Fehlende Session-ID.",
                                     "err"), 400)
    if already_done(session_id):
        return HTMLResponse(done_html(session_id))
    ok, info = get_paid_session(session_id, want_depth="prasna_zusatz")
    if not ok:
        return HTMLResponse(msg_html("Kein Zugang",
                            escape(info.get("error", "Zahlung nicht bestätigt.")),
                            "err"), 403)
    anchor = info.get("ref") or (ref if info.get("test") else "")
    params = _CHART_CACHE.get(anchor) if anchor else None
    if not params or not params.get("prasna"):
        return HTMLResponse(msg_html(
            "Ursprüngliches Prāśna nicht gefunden",
            "Die Zusatzfrage bezieht sich auf ein bestehendes Prāśna, das "
            "auf dem Server nicht mehr verfügbar ist. Bitte melde dich bei "
            "uns — wir helfen sofort weiter.", "err"), 404)
    banner = ('<p class="muted" style="background:rgba(201,168,76,.1);border:1px dashed '
              '#c9a84c;padding:8px 12px;border-radius:4px">⚙ TEST-MODUS – '
              'keine Zahlung nötig.</p>' if info.get("test") else "")
    return HTMLResponse(_page("Prāśna — Vertiefungsfrage", f"""
<div class="ey"><span class="dot">◆</span> Prāśna · Vertiefungsfrage</div>
<h1>Deine Vertiefungsfrage</h1>{banner}
<p>Sie wird am <b>selben Prāśna-Chart</b> gedeutet — dem Moment deiner
ursprünglichen Frage:</p>
<p style="background:{PAL['paper2']};border:1px solid {PAL['line']};
  border-radius:6px;padding:10px 14px"><i>«{escape(params.get('question',''))}»</i></p>
<form method="post" action="/prasna-followup-generate"
  onsubmit="var b=this.querySelector('button');b.textContent='⏳ Wird gedeutet…';setTimeout(function(){{b.disabled=true;}},50);">
<input type="hidden" name="session_id" value="{escape(session_id, quote=True)}">
<input type="hidden" name="ref" value="{escape(anchor, quote=True)}">
<label>Deine Vertiefungsfrage</label>
<input name="question" placeholder="z.B. Und wie entwickelt es sich finanziell?" required>
<div><label>Sprache</label><select name="lang">
  <option value="de">Deutsch</option><option value="en">English</option>
</select></div>
<button type="submit">Frage deuten lassen</button>
</form>"""))


@app.post("/prasna-followup-generate", response_class=HTMLResponse)
def prasna_followup_generate(request: Request,
                             session_id: str = Form(...), ref: str = Form(...),
                             question: str = Form(...), lang: str = Form("de")):
    if not _rate_ok(_client_ip(request), limit=10, window=600.0):
        return HTMLResponse(msg_html("Zu viele Anfragen",
                            "Bitte warte einen Moment und versuche es erneut.", "err"), 429)
    _maybe_sweep()
    ok, info = get_paid_session(session_id, want_depth="prasna_zusatz")
    if not ok:
        return HTMLResponse(msg_html("Kein Zugang",
                            escape(info.get("error", "Zahlung nicht bestätigt.")),
                            "err"), 403)
    anchor = info.get("ref") or (ref if info.get("test") else "")
    params = _CHART_CACHE.get(anchor) if anchor else None
    if not params or not params.get("prasna"):
        return HTMLResponse(msg_html(
            "Ursprüngliches Prāśna nicht gefunden",
            "Das zugehörige Prāśna ist auf dem Server nicht mehr verfügbar. "
            "Bitte melde dich bei uns.", "err"), 404)
    if not claim_session(session_id):
        return HTMLResponse(done_html(session_id))
    try:
        chart = E.generate_chart(params["y"], params["mo"], params["d"],
                                 params["hh"], params["mm"],
                                 params["lat"], params["lon"], params["offset"],
                                 params["label"], params.get("name", ""),
                                 params.get("gender", ""))
        if "/" in str(params.get("iana", "")):
            chart["meta"]["tzname"] = params["iana"]
        chart["prasna_question"] = question.strip()
        chart["prasna_mode"] = True
        chart["prasna_followup_of"] = params.get("question", "")
        if params.get("birth_date") and params.get("birth_city"):
            jc, _err = _build_janma_context(
                params["birth_date"], params.get("birth_time", ""),
                params["birth_city"], params.get("name", ""),
                params.get("gender", ""))
            if jc:                      # bei Fehler still ohne Janma weiter
                chart["janma_context"] = jc
        text = ai_report.generate_interpretation(chart, lang=lang,
                                                 depth="prasna_zusatz")
        title = ("Prāśna — Vertiefungsfrage" if lang == "de"
                 else "Prāśna — Follow-up question")
        pdf = pdf_report.build_pdf(chart, interpretation=text,
                                   interpretation_title=title, variant="customer")
        pdf_tech = pdf_report.build_pdf(chart, interpretation=text,
                                        interpretation_title=title, variant="full")
        html_view = chart_html.build_html(chart, interpretation=text,
                                          interpretation_title=title,
                                          upsell_url=_prasna_upsell_url(anchor))
    except Exception:
        con = _db(); con.execute("DELETE FROM deliveries WHERE session_id=?", (session_id,))
        con.commit(); con.close()
        _traceback.print_exc(file=_sys.stderr)
        return HTMLResponse(msg_html("Fehler bei der Berechnung",
                            "Ein interner Fehler ist aufgetreten — bitte erneut versuchen oder uns kontaktieren.", "err"), 500)
    fn = "Prasna_Vertiefungsfrage.pdf"
    _PDF_CACHE[session_id] = (pdf, fn)
    _PDF_CACHE[session_id + "-technik"] = (
        pdf_tech, fn.replace(".pdf", "_Technische_Daten.pdf"))
    _HTML_CACHE[session_id] = html_view
    return RedirectResponse(url=f"/view/{session_id}", status_code=303)


# ── Muhūrta-Kalender API (flache Moduldatei muhurta_route.py) ────────────────
try:
    import muhurta_route as _muh

    def _muhurta_allowed(sid: str) -> bool:
        """Nur für existierende Berichte rechnen (Session im HTML-Cache)."""
        return bool(sid) and _HTML_CACHE.get(sid) is not None

    _muh.register_muhurta_routes(app, authorize=_muhurta_allowed)
except Exception as _muh_err:   # Datei/pyswisseph fehlt → sauber ohne Tab weiterlaufen
    print(f"[muhurta] deaktiviert: {_muh_err}")


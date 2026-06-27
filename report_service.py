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
import smtplib
import sqlite3
from email.message import EmailMessage
from html import escape
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from io import BytesIO

import astro_engine as E
import ai_report
import pdf_report

# ── CONFIG ────────────────────────────────────────────────────────────────────
BASE_URL   = os.environ.get("BASE_URL", "http://localhost:8000")
DEV_NO_STRIPE = os.environ.get("DEV_NO_STRIPE") == "1"
TEST_MODE  = DEV_NO_STRIPE or os.environ.get("TEST_MODE") == "1"
DB_PATH    = os.environ.get("DB_PATH", "deliveries.db")

# Map your Stripe Price IDs -> (depth, human label). Fill in from your Payment Links.
PRICE_DEPTH = {
    "price_BASIS":   ("basis",   "Basis-Bericht"),
    "price_PREMIUM": ("premium", "Premium-Bericht"),
    "price_YEAR":    ("premium", "Jahresbericht"),
    "price_MATCH":   ("premium", "Partnerschafts-Bericht"),
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
        depth = want_depth if want_depth in ("basis", "premium") else "premium"
        return True, {"email": "", "name": "", "depth": depth,
                      "label": f"{depth.capitalize()}-Bericht (TEST)", "test": True}
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
    """Return True if we just claimed it (first time); False if already used."""
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
    con = _db()
    row = con.execute("SELECT 1 FROM deliveries WHERE session_id=?", (session_id,)).fetchone()
    con.close()
    return row is not None


# ── e-mail ────────────────────────────────────────────────────────────────────
def send_pdf_email(to_addr: str, name: str, pdf: bytes, label: str):
    host = os.environ.get("SMTP_HOST")
    if not host or not to_addr:
        return False
    msg = EmailMessage()
    frm = os.environ.get("MAIL_FROM", os.environ.get("SMTP_USER", ""))
    frm_name = os.environ.get("MAIL_FROM_NAME", "Jyotiṣa Reports")
    msg["From"] = f"{frm_name} <{frm}>"
    msg["To"] = to_addr
    if os.environ.get("BCC_OWNER"):
        msg["Bcc"] = os.environ["BCC_OWNER"]
    msg["Subject"] = f"Dein {label}"
    msg.set_content(
        f"Hallo {name or ''},\n\nim Anhang findest du deinen persönlichen {label} als PDF.\n"
        "Der Bericht wurde KI-gestützt aus deinem exakt berechneten Horoskop erstellt und "
        "dient der persönlichen Reflexion.\n\nHerzlich,\nJyotiṣa Reports")
    msg.add_attachment(pdf, maintype="application", subtype="pdf",
                       filename=f"{label.replace(' ', '_')}.pdf")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER"); pw = os.environ.get("SMTP_PASS")
    if port == 465:
        with smtplib.SMTP_SSL(host, port) as srv:
            if user:
                srv.login(user, pw)
            srv.send_message(msg)
    else:
        with smtplib.SMTP(host, port) as srv:
            srv.starttls()
            if user:
                srv.login(user, pw)
            srv.send_message(msg)
    return True


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
background:#fff;font-size:1rem;font-family:inherit}}
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
    banner = ('<p class="muted" style="background:#fff8e8;border:1px dashed #b8902f;'
              'padding:8px 12px;border-radius:4px">⚙ TEST-MODUS – keine Zahlung nötig.</p>'
              if test else "")
    depth_field = ("" if not test else
                   '<label>Stufe (nur Test)</label><select name="depth">'
                   '<option value="premium">Premium</option>'
                   '<option value="basis">Basis</option></select>')
    return _page("Geburtsdaten – " + info["label"], f"""
<div class="ey"><span class="dot">◆</span> {escape(info['label'])}</div>
<h1>Fast geschafft</h1>{banner}
<p>Gib deine Geburtsdaten ein – wir erstellen deinen Bericht sofort und schicken ihn dir
zusätzlich per E-Mail.</p>
<form method="post" action="/generate">
<input type="hidden" name="session_id" value="{escape(session_id)}">
<label>Name</label><input name="name" value="{escape(info.get('name',''))}" required>
<div class="row"><div><label>Geburtsdatum</label>
<input type="date" name="date" min="1800-01-01" max="2100-12-31" required></div>
<div><label>Geburtszeit</label><input type="time" name="time" value="12:00"></div></div>
<label>Geburtsort (Stadt, Land)</label>
<input name="city" placeholder="z.B. Zürich, Schweiz" required>
<div class="row"><div><label>E-Mail (für den Versand)</label>
<input type="email" name="email" value="{escape(info.get('email',''))}" required></div>
<div><label>Sprache</label><select name="lang"><option value="de">Deutsch</option>
<option value="en">English</option></select></div></div>
{depth_field}
<button type="submit">Bericht erstellen</button>
</form>
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
                            "Dieser Bericht wurde bereits erstellt und per E-Mail versendet.", "ok"))
    ok, info = get_paid_session(session_id, want_depth=depth)
    if not ok:
        return HTMLResponse(msg_html("Zahlung prüfen",
                            escape(info.get("error", "Zahlung nicht bestätigt.")), "err"), 402)
    return HTMLResponse(form_html(session_id, info))


@app.post("/generate")
def generate(session_id: str = Form(...), name: str = Form(""), date: str = Form(...),
             time: str = Form("12:00"), city: str = Form(...), email: str = Form(...),
             lang: str = Form("de"), depth: str = Form("")):
    ok, info = get_paid_session(session_id, want_depth=depth)
    if not ok:
        return HTMLResponse(msg_html("Zahlung prüfen",
                            escape(info.get("error", "nicht bestätigt")), "err"), 402)
    if not claim_session(session_id):
        return HTMLResponse(msg_html("Bereits erstellt",
                            "Dieser Bericht wurde bereits erstellt und versendet.", "ok"))

    try:
        y, mo, d = (int(x) for x in date.split("-"))
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
        return HTMLResponse(msg_html("Etwas ist schiefgelaufen",
                            f"Bitte versuche es erneut oder melde dich bei uns. ({escape(str(e))})",
                            "err"), 500)

    email_ok = False
    try:
        email_ok = send_pdf_email(email, name, pdf, info["label"])
    except Exception as mail_err:
        import sys
        print(f"[email] Failed: {mail_err}", file=sys.stderr)

    fn = f"{info['label'].replace(' ', '_')}.pdf"
    email_note = (f'<p class="ok">Der Bericht wurde an <b>{escape(email)}</b> gesendet.</p>'
                  if email_ok else
                  '<p class="muted">E-Mail nicht konfiguriert – bitte unten herunterladen.</p>')
    dl_page = _page(info["label"], f"""
<div class="ey"><span class="dot">◆</span> {escape(info["label"])}</div>
<h1>Bericht bereit</h1>
{email_note}
<a href="/download/{session_id}" style="display:block;margin-top:22px;width:100%;
background:#2b2118;color:#fdf6e9;padding:14px;border-radius:3px;
font-weight:600;font-size:1rem;text-align:center;text-decoration:none;">
⬇ Bericht herunterladen (PDF)</a>
<p class="muted" style="margin-top:14px">Der Link ist einmalig gültig.</p>""")
    _PDF_CACHE[session_id] = (pdf, fn)
    return HTMLResponse(dl_page)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))

# ── in-memory PDF cache for the success-page download ─────────────────────────
# (resets on service restart — that's fine for short-lived downloads)
_PDF_CACHE: dict = {}


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

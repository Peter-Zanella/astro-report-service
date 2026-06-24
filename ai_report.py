"""
ai_report.py — turns a COMPUTED chart (from astro_engine.generate_chart) into a
written interpretation using the Anthropic API.

Key principle: the LLM never computes anything astrological. It only interprets the
exact facts your engine already calculated. That avoids the hallucinated-positions
problem that pure-AI astrology tools have.

Setup (in your deployed environment, NOT the sandbox — needs network):
    pip install anthropic
    export ANTHROPIC_API_KEY="sk-ant-..."

Usage:
    import astro_engine as E, ai_report
    chart = E.generate_chart(1986,6,18,0,30,13.7525,100.4935,7.0,'Bangkok','Maya','Female')
    text = ai_report.generate_interpretation(chart, lang="de", depth="premium")
    print(text)            # -> ready to drop into the PDF
"""

from __future__ import annotations
import json
import os
from typing import Dict


# ── 1. Build a compact, trustworthy "facts" block from the computed chart ──────
def build_facts(chart: Dict) -> str:
    """Extract only the computed astrological facts the model is allowed to use."""
    SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra",
             "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
    f: Dict = {}

    li = chart.get("lagna_idx")
    f["lagna"] = {"sign": SIGNS[li] if li is not None else None,
                  "pos": chart.get("lagna_pos")}

    f["planets"] = {}
    for p, d in chart.get("planets", {}).items():
        if p == "Ascendant":
            continue
        f["planets"][p] = {"sign": d.get("sign"), "house": d.get("house"),
                           "nakshatra": d.get("nakshatra"), "pada": d.get("pada"),
                           "dignity": d.get("dignity"), "degree": d.get("pos")}

    f["yogas"] = [{"name": y.get("name"), "note": y.get("detail")}
                  for y in chart.get("yogas", [])]

    sb = chart.get("shadbala", {})
    if sb:
        P = sb.get("planets", {})
        f["shadbala_rupas"] = {p: P[p]["rupa"] for p in sb.get("order", []) if p in P}
        f["shadbala_strongest"] = sb.get("order", [None])[0]
        f["shadbala_weakest"] = sb.get("order", [None])[-1]

    bb = chart.get("bhavabala", {})
    if bb:
        f["bhavabala_strongest_house"] = bb.get("order", [None])[0]

    pan = chart.get("panchang")
    if pan:
        f["panchang"] = {k: pan.get(k) for k in
                         ("tithi", "vara", "nakshatra", "yoga", "karana")}

    # current dasha — structure varies; include whatever is present, trimmed
    vim = chart.get("vimshottari")
    if vim is not None:
        f["vimshottari"] = _trim(vim)

    f["meta"] = {"name": chart.get("meta", {}).get("name") if isinstance(chart.get("meta"), dict)
                 else None}
    return json.dumps(f, ensure_ascii=False, indent=1, default=str)


def _trim(obj, depth=0):
    """Keep the dasha structure small so the prompt stays cheap."""
    if depth > 2:
        return "…"
    if isinstance(obj, dict):
        return {k: _trim(v, depth + 1) for k, v in list(obj.items())[:8]}
    if isinstance(obj, list):
        return [_trim(x, depth + 1) for x in obj[:6]]
    return obj


# ── 2. Prompts (per language / depth) ─────────────────────────────────────────
_SECTIONS = {
    "de": {
        "basis": ["Aszendent & Grundwesen", "Mond & Gefühlswelt", "Kernthemen & Stärken",
                  "Ein Hinweis für den Alltag"],
        "premium": ["Aszendent & Grundwesen", "Mond, Nakshatra & Gefühlswelt",
                    "Stärken (Shad Bala, Yogas)", "Herausforderungen & Wachstum",
                    "Beziehungen", "Beruf & Berufung", "Aktuelles Timing (Daśā)",
                    "Zusammenfassung"],
    },
    "en": {
        "basis": ["Ascendant & core nature", "Moon & emotional world",
                  "Key themes & strengths", "A note for daily life"],
        "premium": ["Ascendant & core nature", "Moon, nakshatra & emotional world",
                    "Strengths (Shad Bala, yogas)", "Challenges & growth",
                    "Relationships", "Career & calling", "Current timing (daśā)",
                    "Summary"],
    },
}

_SYS = {
    "de": ("Du bist ein erfahrener vedischer Astrologe (Jyotiṣa) und schreibst einen "
           "persönlichen Geburtshoroskop-Bericht. Du deutest AUSSCHLIESSLICH die unten "
           "gelieferten, bereits exakt berechneten Fakten. Du berechnest oder veränderst "
           "KEINE Positionen, Zeichen, Grade oder Daten und erfindest nichts hinzu. "
           "Schreibe warm, klar und alltagstauglich auf Deutsch, ohne Fachjargon-Überladung "
           "(erkläre Begriffe kurz). Keine medizinischen, rechtlichen oder finanziellen "
           "Ratschläge, keine Angst- oder Schicksalssprache, keine garantierten Vorhersagen. "
           "Gliedere den Text mit den vorgegebenen Abschnitts-Überschriften (als Markdown ##)."),
    "en": ("You are an experienced Vedic astrologer (Jyotiṣa) writing a personal birth-chart "
           "report. You interpret ONLY the already-calculated facts provided below. You do NOT "
           "compute or change any positions, signs, degrees or dates, and you invent nothing. "
           "Write warmly, clearly and practically in English, without jargon overload (briefly "
           "explain terms). No medical, legal or financial advice, no fear/fate language, no "
           "guaranteed predictions. Structure the text with the given section headings (as "
           "Markdown ##)."),
}


def build_prompt(facts: str, lang: str, depth: str) -> str:
    secs = _SECTIONS[lang][depth]
    head = ("Hier sind die berechneten Fakten des Horoskops (JSON). Schreibe den Bericht "
            "mit genau diesen Abschnitten:" if lang == "de" else
            "Here are the computed chart facts (JSON). Write the report with exactly these "
            "sections:")
    return f"{head}\n\n{chr(10).join('## ' + s for s in secs)}\n\n--- FACTS ---\n{facts}"


# ── 3. Call the Anthropic API ─────────────────────────────────────────────────
def generate_interpretation(chart: Dict, lang: str = "de", depth: str = "premium",
                            model: str = "claude-sonnet-4-6", max_tokens: int = 3000) -> str:
    """Return the written interpretation. depth ∈ {'basis','premium'}."""
    try:
        import anthropic
    except ImportError as e:
        raise RuntimeError("pip install anthropic") from e
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("Set ANTHROPIC_API_KEY in the environment.")
    if depth not in ("basis", "premium"):
        depth = "premium"

    facts = build_facts(chart)
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=_SYS[lang],
        messages=[{"role": "user", "content": build_prompt(facts, lang, depth)}],
    )
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()


if __name__ == "__main__":
    import astro_engine as E
    c = E.generate_chart(1986, 6, 18, 0, 30, 13.7525, 100.4935, 7.0, "Bangkok", "Demo", "Female")
    print(generate_interpretation(c, lang="de", depth="premium"))

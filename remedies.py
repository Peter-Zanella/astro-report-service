# -*- coding: utf-8 -*-
"""
remedies.py — Upāyas (klassische Ausgleichsmassnahmen) für den Remedies-Tab.
=============================================================================
Muster wie medical.py: astro_engine liefert alle Daten (Würden, Affliktionen,
Shad Bala, Daśās, Transite), dieses Modul LEITET daraus die relevanten
Planeten ab und hinterlegt die klassischen Upāya-Zuordnungen als statische
Tabellen. chart_html rendert nur.

Auswahllogik (klassisch-praktisch):
  1. Aktive Mahā- und Antardaśā-Herren — ihre Qualität prägt die Gegenwart.
  2. Lagna- und Trikona-Herren (1/5/9), wenn geschwächt — stärken lohnt.
  3. Ernsthaft affligierte Planeten — besänftigen.
  4. Sade Sati (Transit-Saturn in 12/1/2 vom Geburtsmond) — Śani-Upāyas.

Sicherheitsprinzip EDELSTEINE: Ein Ratna VERSTÄRKT seinen Planeten. Empfohlen
wird er darum nur für funktionale Wohltäter (Herren von 1, 5, 9, sofern nicht
zugleich Dushthana-Herr); für alle übrigen — insbesondere Übeltäter und
Daśā-Herren in Besänftigung — stehen Mantra, Dāna, Fasten und Verehrung im
Vordergrund. Keine Heils- oder Erfolgsversprechen; deutlicher Disclaimer.
"""
from typing import Dict, List, Optional

from astro_engine import SIGN_LORDS, _MALEFICS

DE = {"Sun": "Sonne", "Moon": "Mond", "Mars": "Mars", "Mercury": "Merkur",
      "Jupiter": "Jupiter", "Venus": "Venus", "Saturn": "Saturn",
      "Rahu": "Rahu", "Ketu": "Ketu"}
GRAHAS = list(DE.keys())

# ── Klassische Upāya-Zuordnungen je Graha ────────────────────────────────────
# Ratna/Metall/Finger nach verbreiteter Konvention; Japa-Zahlen die gängigen
# vedischen Grundzahlen; Dāna und Fastentag klassisch dem Wochentagsherrn
# zugeordnet. Eigene kompakte Formulierungen.
REMEDIES: Dict[str, Dict] = {
    "Sun": {
        "gem": "Rubin", "gem_alt": "Granat, roter Spinell", "metal": "Gold",
        "finger": "Ringfinger", "day": "Sonntag",
        "mantra": "Oṃ hrāṃ hrīṃ hrauṃ saḥ sūryāya namaḥ", "japa": "7'000",
        "dana": "Weizen, Jaggery, Kupfer, rote Kleidung (sonntags)",
        "fast": "Sonntag", "deity": "Sūrya (Āditya-Hṛdayam rezitieren)",
        "color": "Rot, Orange",
    },
    "Moon": {
        "gem": "Perle", "gem_alt": "Mondstein", "metal": "Silber",
        "finger": "kleiner Finger", "day": "Montag",
        "mantra": "Oṃ śrāṃ śrīṃ śrauṃ saḥ candrāya namaḥ", "japa": "11'000",
        "dana": "Reis, Milch, weisse Kleidung, Silber (montags)",
        "fast": "Montag", "deity": "Śiva und Pārvatī",
        "color": "Weiss, Perlmutt",
    },
    "Mars": {
        "gem": "Rote Koralle", "gem_alt": "Karneol", "metal": "Kupfer oder Gold",
        "finger": "Ringfinger", "day": "Dienstag",
        "mantra": "Oṃ krāṃ krīṃ krauṃ saḥ bhaumāya namaḥ", "japa": "10'000",
        "dana": "Rote Linsen (Masoor), Kupfer, Süsses aus Jaggery (dienstags)",
        "fast": "Dienstag", "deity": "Hanumān oder Kārttikeya",
        "color": "Rot",
    },
    "Mercury": {
        "gem": "Smaragd", "gem_alt": "Peridot, grüner Turmalin", "metal": "Gold",
        "finger": "kleiner Finger", "day": "Mittwoch",
        "mantra": "Oṃ brāṃ brīṃ brauṃ saḥ budhāya namaḥ", "japa": "9'000",
        "dana": "Mungbohnen, grüne Kleidung, Bücher für Lernende (mittwochs)",
        "fast": "Mittwoch", "deity": "Viṣṇu (Viṣṇu-Sahasranāma)",
        "color": "Grün",
    },
    "Jupiter": {
        "gem": "Gelber Saphir", "gem_alt": "gelber Topas, Citrin", "metal": "Gold",
        "finger": "Zeigefinger", "day": "Donnerstag",
        "mantra": "Oṃ grāṃ grīṃ grauṃ saḥ gurave namaḥ", "japa": "19'000",
        "dana": "Kichererbsen, Kurkuma, Safran, gelbe Kleidung; Lehrer ehren (donnerstags)",
        "fast": "Donnerstag", "deity": "Bṛhaspati, Viṣṇu; den eigenen Guru ehren",
        "color": "Gelb, Gold",
    },
    "Venus": {
        "gem": "Diamant", "gem_alt": "weisser Saphir, weisser Zirkon",
        "metal": "Silber oder Platin", "finger": "Mittelfinger", "day": "Freitag",
        "mantra": "Oṃ drāṃ drīṃ drauṃ saḥ śukrāya namaḥ", "japa": "16'000",
        "dana": "Reis, Zucker, weisse/bunte Kleidung, Parfum; Frauen ehren (freitags)",
        "fast": "Freitag", "deity": "Lakṣmī",
        "color": "Weiss, Pastell",
    },
    "Saturn": {
        "gem": "Blauer Saphir", "gem_alt": "Amethyst, Iolith",
        "metal": "Eisen (Fassung Silber)", "finger": "Mittelfinger", "day": "Samstag",
        "mantra": "Oṃ prāṃ prīṃ prauṃ saḥ śanaye namaḥ", "japa": "23'000",
        "dana": "Schwarzer Sesam, Urad-Linsen, Senföl, Eisen; Arbeitende und Alte unterstützen (samstags)",
        "fast": "Samstag", "deity": "Hanumān; Śani mit Sesamöl-Licht",
        "color": "Schwarz, Dunkelblau",
    },
    "Rahu": {
        "gem": "Hessonit (Gomedha)", "gem_alt": "—", "metal": "Silber",
        "finger": "Mittelfinger", "day": "Samstag",
        "mantra": "Oṃ bhrāṃ bhrīṃ bhrauṃ saḥ rāhave namaḥ", "japa": "18'000",
        "dana": "Dunkle Decken, schwarzer Sesam; Aussenseiter unterstützen (samstags)",
        "fast": "Samstag", "deity": "Durgā",
        "color": "Rauchgrau",
    },
    "Ketu": {
        "gem": "Katzenauge", "gem_alt": "—", "metal": "Silber",
        "finger": "Ringfinger", "day": "Dienstag",
        "mantra": "Oṃ srāṃ srīṃ srauṃ saḥ ketave namaḥ", "japa": "17'000",
        "dana": "Mehrfarbige Decken, Sesam; spirituelle Sucher unterstützen (dienstags)",
        "fast": "Dienstag", "deity": "Gaṇeśa",
        "color": "Grau, mehrfarbig",
    },
}

_SERIOUS = ("combust", "nodal", "grahana", "gandanta", "sandhi", "yuddha", "debil")


def _serious_aff(aff_list: List[str]) -> List[str]:
    return [a for a in aff_list
            if any(k in a.lower() for k in _SERIOUS)]


def compute_targets(chart: Dict, max_targets: int = 5) -> List[Dict]:
    """Rangliste der Upāya-relevanten Planeten mit Begründung und Ansatz
    ('stärken' → inkl. Ratna-Empfehlung, 'besänftigen' → ohne Ratna)."""
    pls = chart.get("planets", {})
    aff = chart.get("afflictions", {}) or {}
    houses = chart.get("houses", {}) or {}
    sb = ((chart.get("shadbala") or {}).get("planets") or {})

    def rupa(p):
        v = sb.get(p, {}).get("total")
        return round(v / 60.0, 2) if isinstance(v, (int, float)) else None

    def lord_of(hn):
        return SIGN_LORDS.get(houses.get(hn, houses.get(str(hn))))

    lagna_lord = lord_of(1)
    trikona_lords = {lord_of(5), lord_of(9)} - {None}
    dushthana_lords = {lord_of(6), lord_of(8), lord_of(12)} - {None}
    func_benefics = ({lagna_lord} | trikona_lords) - dushthana_lords - {None}

    # Aktive Daśā-Herren
    md = ad = None
    for m in (chart.get("dashas", {}) or {}).get("mahadashas", []):
        if m.get("active"):
            md = m.get("planet")
            for a in m.get("antardashas", []):
                if a.get("active"):
                    ad = a.get("planet")
            break

    # Sade Sati: Transit-Saturn in 12/1/2 vom Geburtsmond (nur Lookup)
    sade_sati = False
    t_sat = (chart.get("transits") or {}).get("Saturn", {}).get("sign_idx")
    n_moon = pls.get("Moon", {}).get("sign_idx")
    if t_sat is not None and n_moon is not None:
        sade_sati = ((t_sat - n_moon) % 12) in (11, 0, 1)

    cand: Dict[str, Dict] = {}

    def add(p, reason, prio):
        if p not in REMEDIES:
            return
        e = cand.setdefault(p, {"planet": p, "reasons": [], "prio": prio})
        e["reasons"].append(reason)
        e["prio"] = min(e["prio"], prio)

    if md:
        add(md, f"Herr deiner aktuellen Mahādaśā — seine Qualität prägt die "
                f"gesamte Lebensphase", 0)
    if ad and ad != md:
        add(ad, "Herr der aktuellen Antardaśā — bestimmt die laufende "
                "Unterperiode", 1)
    if sade_sati:
        add("Saturn", "Sade Sati: Transit-Saturn läuft über die Achse deines "
                      "Geburtsmondes — die klassische Zeit für Śani-Upāyas", 1)

    weak_digs = ("Debilitated", "Enemy's Sign", "Great Enemy's Sign")
    for p in sorted(func_benefics):
        d = pls.get(p, {}).get("dignity", "-")
        r = rupa(p)
        ser = _serious_aff(aff.get(p, []))
        why = []
        if d in weak_digs:
            why.append(f"steht geschwächt ({d})")
        if r is not None and r < 5.0:
            why.append(f"unterdurchschnittliche Shad-Bala-Stärke")
        if ser:
            why.append("ernsthaft affligiert")
        if why:
            role = "Lagna-Herr" if p == lagna_lord else "Trikona-Herr (5/9)"
            add(p, f"{role}, {' und '.join(why)} — Stärkung kommt dem ganzen "
                   f"Horoskop zugute", 2)

    for p in GRAHAS:
        ser = _serious_aff(aff.get(p, []))
        if ser and p not in cand:
            add(p, f"ernsthaft affligiert ({ser[0]})", 3)

    out = sorted(cand.values(), key=lambda e: e["prio"])[:max_targets]
    for e in out:
        p = e["planet"]
        gem_ok = p in func_benefics and not _serious_aff(aff.get(p, []))
        e["approach"] = "stärken" if gem_ok else "besänftigen"
        e["gem_ok"] = gem_ok
    return out


_DISCLAIMER = (
    "Upāyas sind <strong>traditionelle spirituelle Praktiken</strong> der "
    "vedischen Kultur — Angebote zur inneren Ausrichtung, keine Heils-, "
    "Gesundheits- oder Erfolgsversprechen. Edelsteine verstärken ihren "
    "Planeten und sollten nur nach persönlicher Beratung durch eine "
    "erfahrene Jyotiṣa-Fachperson und mit Probezeit getragen werden — "
    "AstroVeda verkauft keine Steine und empfiehlt keine Anbieter. "
    "Mantra, Dāna (Geben) und Fasten stehen jedem offen und gelten "
    "klassisch als die sanftesten und sichersten Wege.")


def _card(p: str, reasons: List[str], approach: str, gem_ok: bool) -> str:
    r = REMEDIES[p]
    gem_line = (f"<div><strong>Edelstein (Ratna):</strong> {r['gem']} "
                f"<span style='color:var(--mu)'>(Alternativen: {r['gem_alt']}; "
                f"{r['metal']}, {r['finger']}, erstmals an einem {r['day']})"
                f"</span></div>"
                if gem_ok else
                f"<div style='color:var(--mu)'><strong>Edelstein:</strong> "
                f"für diesen Planeten in deinem Horoskop bewusst NICHT "
                f"empfohlen — ein Ratna würde ihn verstärken; die sanften "
                f"Wege unten sind hier der klassische Ansatz.</div>")
    why = "".join(f"<li>{w}</li>" for w in reasons)
    return (
        f"<div style='border:1px solid rgba(255,255,255,.14);border-radius:10px;"
        f"padding:14px 16px;margin:0 0 14px'>"
        f"<div style='color:var(--ac);font-size:1.02rem;font-weight:600'>"
        f"{DE[p]} <span style='font-size:.78rem;font-weight:400;"
        f"color:var(--mu)'>&middot; Ansatz: {approach}</span></div>"
        f"<ul style='margin:6px 0 10px;padding-left:18px;font-size:.82rem;"
        f"color:var(--mu);line-height:1.5'>{why}</ul>"
        f"<div style='font-size:.86rem;line-height:1.65'>"
        f"{gem_line}"
        f"<div><strong>Mantra:</strong> {r['mantra']} "
        f"<span style='color:var(--mu)'>(klassische Japa-Zahl {r['japa']}; "
        f"praktisch: 108 Wiederholungen am {r['day']})</span></div>"
        f"<div><strong>D&#257;na (Geben):</strong> {r['dana']}</div>"
        f"<div><strong>Fasten:</strong> {r['fast']} &middot; "
        f"<strong>Verehrung:</strong> {r['deity']} &middot; "
        f"<strong>Farbe:</strong> {r['color']}</div>"
        f"</div></div>")


def render_tab(chart: Dict) -> str:
    """Kompletter innerer HTML-Inhalt des Remedies-Tabs."""
    targets = compute_targets(chart)
    cards = "".join(_card(e["planet"], e["reasons"], e["approach"],
                          e["gem_ok"]) for e in targets)
    if not cards:
        cards = ("<p style='color:var(--mu)'>Keine besonderen Upāya-"
                 "Empfehlungen — die Schlüsselplaneten deines Horoskops "
                 "stehen ordentlich. Die Referenztabelle unten gilt "
                 "allgemein.</p>")

    ref_rows = "".join(
        f"<tr><td>{DE[p]}</td><td>{REMEDIES[p]['gem']}</td>"
        f"<td>{REMEDIES[p]['mantra']}</td><td>{REMEDIES[p]['fast']}</td>"
        f"<td>{REMEDIES[p]['deity']}</td></tr>"
        for p in GRAHAS)

    return (
        f"<div style='border:1px solid rgba(217,194,122,.5);border-radius:8px;"
        f"padding:10px 14px;font-size:.8rem;line-height:1.5;color:var(--mu);"
        f"margin-bottom:14px'>{_DISCLAIMER}</div>"
        f"<p class='sh'>Deine pers&ouml;nlichen Up&#257;yas</p>"
        f"<p style='font-size:.84rem;color:var(--mu);line-height:1.5'>"
        f"Abgeleitet aus deinem Horoskop: die Herren deiner laufenden "
        f"Da&scaron;&#257;-Perioden, geschw&auml;chte Schl&uuml;sselplaneten "
        f"und ernsthafte Affliktionen. Ein einzelner Weg, ehrlich gepflegt, "
        f"wirkt klassisch mehr als alle gleichzeitig.</p>"
        f"{cards}"
        f"<p class='sh'>Referenz: Up&#257;yas aller neun Grahas</p>"
        f"<details><summary style='cursor:pointer;color:var(--mu);"
        f"font-size:.82rem'>Tabelle anzeigen</summary>"
        f"<div class='ow'><table class='dt'><thead><tr><th>Graha</th>"
        f"<th>Ratna</th><th>Mantra</th><th>Fastentag</th><th>Verehrung</th>"
        f"</tr></thead><tbody>{ref_rows}</tbody></table></div></details>"
        f"<p style='font-size:.74rem;color:var(--mu);margin-top:14px'>"
        f"Zuordnungen nach der klassischen Up&#257;ya-Tradition (BPHS, "
        f"Ratna- und Japa-Kapitel; gebr&auml;uchliche Konventionen f&uuml;r "
        f"Metall und Finger). Edelstein-Empfehlungen nur f&uuml;r funktionale "
        f"Wohlt&auml;ter deines Lagnas.</p>")

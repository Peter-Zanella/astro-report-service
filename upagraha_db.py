# -*- coding: utf-8 -*-
"""
upagraha_db.py — Statische Kurzdeutungen der Upagrahas (Natur + Hauswirkung).
=============================================================================
Reines Text-Modul (kein Rechnen) nach dem Muster von pada_db/panchang_db.
astro_engine berechnet Position und Haus; dieses Modul liefert dazu:

  • NATURE[key]           — Kurzcharakter des Upagraha (1-2 Sätze)
  • HOUSE_TEXTS[key][h]   — klassische Hauswirkung (BPHS-Systematik, eigene
                            kompakte Formulierung) für Gulika/Māndi und die
                            fünf sonnenbasierten Upagrahas
  • describe(key, house)  — (Natur, Haustext) für die Anzeige

Für Kāla, Mṛtyu, Ardhaprahara und Yamaghaṇṭaka existiert keine kanonische
Haus-für-Haus-Liste in den Klassikern; sie erhalten Charaktertext plus ein
generisches Wirkprinzip auf die Themen des besetzten Hauses.
"""
from typing import Optional, Tuple

NATURE = {
    "Gulika": ("Sohn Saturns und wichtigster Upagraha: Punkt der Schwere, "
               "Verzögerung und karmischen Last. Wo Gulika steht, ist "
               "Disziplin, Geduld und Vorsicht gefragt — im Prāśna gilt er "
               "als Störfaktor, der verborgene Belastungen anzeigt."),
    "Mandi": ("Zweiter Saturn-Punkt, aus der Mitte des Saturn-Abschnitts: "
              "wirkt wie Gulika, aber subtiler und mehr nach innen — als "
              "leise Trägheit oder unterschwellige Schwere im besetzten "
              "Bereich."),
    "Kala": ("Punkt des Sonnen-Abschnitts: Zeit- und Autoritätsdruck, "
             "verzehrende Schärfe. Zeigt, wo Verantwortung und Termindruck "
             "besonders spürbar werden."),
    "Mrityu": ("Punkt des Mars-Abschnitts: Schnitte, Reibung und "
               "Konfliktenergie. Mahnt im besetzten Bereich zu Umsicht bei "
               "Auseinandersetzungen, Eile und Verletzungsrisiken."),
    "Ardhaprahara": ("Punkt des Merkur-Abschnitts: nervöse Unruhe, "
                     "Zerstreuung und Störungen in Kommunikation und "
                     "Planung. Ruft nach Ordnung der Gedanken."),
    "Yamaghantaka": ("Punkt des Jupiter-Abschnitts und mildester der "
                     "Zeit-Upagrahas: Ernst, Pflichtgefühl und eine "
                     "disziplinierende, mitunter sogar stützende Note."),
    "Dhuma": ("»Rauch« — der erste Sonnen-Upagraha: Vernebelung, Reizung "
              "und trockene Hitze. Verschleiert die Themen des besetzten "
              "Hauses und macht sie ruheloser."),
    "Vyatipata": ("»Unglück/Umsturz« — Punkt der Turbulenz: plötzliche "
                  "Wendungen und Umschwünge in den Angelegenheiten des "
                  "besetzten Hauses."),
    "Parivesha": ("»Halo/Hof um die Sonne« — Umhüllung: bindet und "
                  "begrenzt, kann aber auch wie ein Schutzring wirken. Der "
                  "ambivalenteste der Sonnen-Upagrahas."),
    "Indrachapa": ("»Regenbogen Indras« — Glanz und Trugbild: kurzlebige "
                   "Erfolge, Faszination und Illusionen in den Themen des "
                   "besetzten Hauses."),
    "Upaketu": ("»Fahne Ketus« — Signalpunkt unmittelbar vor der Sonne: "
                "feine Störungen, plötzliche Impulse und eine geistig-"
                "spirituelle Reizbarkeit."),
}

# ── Hauswirkungen (1–12) — kompakte Eigenformulierungen nach BPHS-Systematik ─
HOUSE_TEXTS = {
    "Gulika": {
        1:  "Belastet Vitalität und Selbstbild; Körper, Auftreten und Gesundheit verlangen Disziplin.",
        2:  "Mahnt zu Sorgfalt bei Sprache, Finanzen und Ernährung; Familienthemen fordern Ernsthaftigkeit.",
        3:  "Vergleichsweise günstig: zäher Mut und Durchhaltewille; Geschwisterthemen werden ernst genommen.",
        4:  "Innere Unruhe im häuslichen Bereich; Immobilien- und Mutter-Themen mit Bedacht angehen.",
        5:  "Fordert Geduld bei Kindern, Bildung und Spekulation; Risiko lieber meiden.",
        6:  "Stark platziert: Gegner und Krankheiten werden niedergehalten (Upachaya-Wirkung).",
        7:  "Partnerschaft braucht Reife; Bindungen kommen spät oder tragen ernsten Charakter.",
        8:  "Tiefe Transformations- und Okkultthemen; bei Risiken und fremdem Gut doppelt vorsichtig sein.",
        9:  "Prüft Glaube und Glück; Lehrer- und Vater-Themen erhalten Gewicht und Ernst.",
        10: "Beruflicher Aufstieg mit Hindernissen, aber zäh und beständig durch Ausdauer.",
        11: "Gewinne kommen langsam, dafür beständig; Verbindungen zu älteren, ernsten Menschen.",
        12: "Rückzug und Ausgaben begrenzen; spirituelle Praxis ist das beste Ventil.",
    },
    "Dhuma": {
        1:  "Hitziges, rastloses Selbst; Reizbarkeit und Ungeduld wollen gezügelt sein.",
        2:  "Scharfe Rede und schwankende Mittel; Worte und Ausgaben abkühlen lassen.",
        3:  "Tatkraft mit Härte; gute Kampf- und Durchsetzungskraft.",
        4:  "Unruhe im Zuhause; innerer Friede braucht bewusste Pflege.",
        5:  "Bildungs- und Kinderthemen stehen unter Anspannung; Druck herausnehmen.",
        6:  "Besiegt Feinde und Hindernisse — hier wirkt der Rauch nach aussen, nicht gegen einen selbst.",
        7:  "Spannungen und Reibungshitze in Partnerschaften.",
        8:  "Gefahr durch Übereifer; auf Reisen und bei Risiken achtsam bleiben.",
        9:  "Prüfungen im Glauben; das Glück wirkt unstet.",
        10: "Ehrgeizig, aber ruhelos im Beruf; Erfolge verlangen Abkühlung zwischendurch.",
        11: "Gewinne durch Mühe und brennenden Ehrgeiz.",
        12: "Zerstreuung und Ausgaben; Schlaf und Regeneration bewusst schützen.",
    },
    "Vyatipata": {
        1:  "Wechselhafte Lebensführung; Umbrüche prägen die Persönlichkeit.",
        2:  "Unstete Finanzen; Erspartes klug und konservativ sichern.",
        3:  "Mut in Krisen; im Geschwister- und Umfeldbereich Turbulenzen.",
        4:  "Wohnortswechsel und bewegtes Familienleben.",
        5:  "Sprunghafte Interessen; Kinder- und Bildungsfragen brauchen Ruhe.",
        6:  "Wendungen treffen die Gegner — für Gesundheit und Konflikte eher günstig.",
        7:  "Turbulente Beziehungsphasen; Stabilität bewusst aufbauen.",
        8:  "Plötzliche Ereignisse; Absicherung und Vorsorge sind wichtig.",
        9:  "Glaubenswechsel und unkonventionelle Weltsicht.",
        10: "Karrierewenden; Flexibilität wird zur eigentlichen Stärke.",
        11: "Schwankende Einkünfte, aber auch überraschende Gewinne.",
        12: "Abrupte Verluste vermeiden; Loslassen will gelernt sein.",
    },
    "Parivesha": {
        1:  "Sanftes, umhülltes Wesen; Neigung, sich anzupassen und zu fügen.",
        2:  "Bewahrende Hand bei Geld und Familie.",
        3:  "Zurückhaltender Mut; diplomatisch statt konfrontativ.",
        4:  "Schützender häuslicher Rahmen; starkes Bedürfnis nach Geborgenheit.",
        5:  "Idealistische Bildung; behütete Kinder- und Herzensthemen.",
        6:  "Konflikte werden eingehegt und entschärft.",
        7:  "Bindungsorientiert bis zur Abhängigkeit; gesunde Grenzen wahren.",
        8:  "Stille Transformationen; Erbschafts- und Tabuthemen im Hintergrund.",
        9:  "Fromme, traditionsnahe Ausrichtung.",
        10: "Solide, aber wenig glanzvolle Laufbahn; Verlässlichkeit als Kapital.",
        11: "Gewinne über Netzwerke, Fürsprache und Wohlwollen.",
        12: "Rückzug als Schutz; Hang zur Weltflucht im Auge behalten.",
    },
    "Indrachapa": {
        1:  "Charismatischer Schein; das Selbstbild regelmässig an der Wirklichkeit prüfen.",
        2:  "Glänzende, aber flüchtige Mittel; Substanz vor Glanz.",
        3:  "Kühne Auftritte und kurzlebige Initiativen.",
        4:  "Das Heim als Bühne; Schönheit im häuslichen Umfeld.",
        5:  "Kreative Höhenflüge und ansteckende Begeisterung.",
        6:  "Täuscht Gegner und Hindernisse — ein taktischer Vorteil.",
        7:  "Verzauberung in Beziehungen; mit Ernüchterungen rechnen.",
        8:  "Faszination für das Verborgene und Geheimnisvolle.",
        9:  "Schillernde Ideale; nach tragfähiger Substanz suchen.",
        10: "Glanzvolle, aber schwankende Reputation.",
        11: "Schnelle, unbeständige Gewinne.",
        12: "Illusionen kosten Kraft; Klarheit und Erdung üben.",
    },
    "Upaketu": {
        1:  "Feinnerviges, waches Selbst mit rascher Auffassung.",
        2:  "Pointierte Rede; Impulse bei Geldentscheiden zügeln.",
        3:  "Geistige Initiative und plötzliche, mutige Einsätze.",
        4:  "Frühe Aufbrüche vom Elternhaus; bewegtes Innenleben.",
        5:  "Blitzartige Ideen und intuitives Lernen.",
        6:  "Durchschlagskraft gegen Hindernisse und Widersacher.",
        7:  "Elektrisierende, aber unruhige Bindungen.",
        8:  "Abrupte Einsichten; ausgeprägter Forscherdrang.",
        9:  "Spiritueller Funke; Impulse zu Pilgerschaft und Sinnsuche.",
        10: "Markante, sprunghafte Berufsimpulse.",
        11: "Unerwartete Chancen aus dem Umfeld.",
        12: "Sehnsucht nach Transzendenz; Erdung bewusst pflegen.",
    },
}
# Māndi wirkt wie Gulika, nur milder — gleiche Haustexte
HOUSE_TEXTS["Mandi"] = HOUSE_TEXTS["Gulika"]

HOUSE_THEMES = {
    1: "Körper, Selbst und Auftreten", 2: "Finanzen, Familie und Sprache",
    3: "Mut, Initiative und Geschwister", 4: "Zuhause, Mutter und inneren Frieden",
    5: "Kinder, Bildung und Kreativität", 6: "Gesundheit, Alltag und Widersacher",
    7: "Partnerschaft und Begegnung", 8: "Wandlung, Krisen und Verborgenes",
    9: "Glück, Glaube und Lehrer", 10: "Beruf, Ruf und Verantwortung",
    11: "Gewinne, Freunde und Ziele", 12: "Rückzug, Verluste und Spiritualität",
}

_MILD = {"Yamaghantaka"}          # eher stützend
_GENERIC_NOTE = {
    "Kala": "bringt dort Zeit- und Verantwortungsdruck hinein",
    "Mrityu": "mahnt dort zu Umsicht bei Konflikten und Eile",
    "Ardhaprahara": "streut dort Unruhe und Zerstreuung ein",
    "Yamaghantaka": "bringt dort Ernst und ordnende Pflicht hinein — oft stützend",
}


def describe(key: str, house: Optional[int]) -> Tuple[str, str]:
    """(Kurzcharakter, Haustext) — Haustext leer, wenn kein Haus bekannt."""
    nature = NATURE.get(key, "")
    if not house:
        return nature, ""
    ht = HOUSE_TEXTS.get(key, {}).get(house)
    if ht:
        prefix = "Wie Gulika, nur milder: " if key == "Mandi" else ""
        return nature, prefix + ht
    theme = HOUSE_THEMES.get(house, "")
    note = _GENERIC_NOTE.get(key, "wirkt dort auf die Hausthemen")
    mild = (" Ohne kanonische Haus-für-Haus-Regel in den Klassikern; "
            "Wirkung nach der Hausnatur — fordernder in Kendras und bei "
            "Lagna oder Mond, gemildert in 3, 6 und 11.")
    return nature, f"In Haus {house} ({theme}): {note}.{mild if key not in _MILD else ''}"

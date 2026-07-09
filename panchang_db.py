"""
panchang_db.py — Statische Deutungstabelle für die fünf Pañcāṅga-Elemente.

Reine Nachschlage-Daten (keine Berechnung): astro_engine bestimmt Tithi, Vara,
Nakshatra, Nitya-Yoga und Karaṇa; dieses Modul liefert die klassischen
Kurzdeutungen dazu — für PDF-Bericht und Web-Ansicht.

Quellen: Varahamihira (Brihat Samhita), Muhurta-Klassiker (Muhurta Chintamani).
"""

# ── Paksha (Mondphase) ────────────────────────────────────────────────────────
PAKSHAS = {
    "Shukla": "Zunehmender Mond (Shukla Paksha) — aufbauende, nach aussen "
              "gerichtete Energie; begünstigt Wachstum, Neubeginn und Sichtbarkeit.",
    "Krishna": "Abnehmender Mond (Krishna Paksha) — verinnerlichende, vollendende "
               "Energie; begünstigt Abschluss, Loslassen und innere Arbeit.",
}

# ── Tithi-Gruppen (klassische Fünfergruppen) ─────────────────────────────────
TITHI_GROUPS = {
    "Nanda":  "Nanda («Freude», Tithis 1/6/11) — günstig für Neubeginn, Feste und Kreatives.",
    "Bhadra": "Bhadra («Gedeihen», Tithis 2/7/12) — günstig für Gesundheit, Arbeit und Aufbau.",
    "Jaya":   "Jaya («Sieg», Tithis 3/8/13) — günstig für Durchsetzung und Wettbewerb.",
    "Rikta":  "Rikta («leer», Tithis 4/9/14) — klassisch schwach für Neubeginn; "
              "stark für Loslassen, Reinigung und Beenden.",
    "Purna":  "Pūrṇa («Fülle», Tithis 5/10/15) — Vollendung, Reife und Erfüllung.",
}

_TITHI_GROUP_OF = {1: "Nanda", 2: "Bhadra", 3: "Jaya", 4: "Rikta", 5: "Purna",
                   6: "Nanda", 7: "Bhadra", 8: "Jaya", 9: "Rikta", 10: "Purna",
                   11: "Nanda", 12: "Bhadra", 13: "Jaya", 14: "Rikta", 15: "Purna"}

# ── Die 15 Tithi-Namen (je Paksha) + Amavasya ────────────────────────────────
TITHIS = {
    "Pratipada":  "1. Mondtag (Herr: Agni) — Beginn, Initialkraft, erster Impuls; "
                  "eine Geburt an Pratipada betont Pioniergeist und Anfangsenergie.",
    "Dvitiya":    "2. Mondtag (Herr: Brahma) — Fundament und Paarbildung; betont "
                  "Beständigkeit, Zusammenarbeit und geduldigen Aufbau.",
    "Tritiya":    "3. Mondtag (Herrin: Gauri) — Tatkraft und Gestaltung; betont "
                  "Durchsetzungsfähigkeit und schöpferische Umsetzung.",
    "Chaturthi":  "4. Mondtag (Herr: Ganesha/Yama) — Hindernisse und deren "
                  "Überwindung; betont Zähigkeit, Prüfungen und Disziplin.",
    "Panchami":   "5. Mondtag (Herr: Naga) — Fülle, Heilkraft und Wissen; betont "
                  "Lernfähigkeit, Heilung und geistige Tiefe.",
    "Shashthi":   "6. Mondtag (Herr: Kartikeya) — Kampfkraft und Gesundheit; "
                  "betont Wettbewerbsstärke, Disziplin und Vitalität.",
    "Saptami":    "7. Mondtag (Herr: Surya) — solare Kraft und Bewegung; betont "
                  "Reisen, Sichtbarkeit und schöpferisches Wirken.",
    "Ashtami":    "8. Mondtag (Herr: Rudra/Shiva) — Intensität und Wandlung; "
                  "betont Transformationskraft, Ernst und Durchbrüche.",
    "Navami":     "9. Mondtag (Herrin: Durga) — Schutz- und Kampfkraft; betont "
                  "Mut, Widerstandskraft und das Überwinden von Gegnern.",
    "Dashami":    "10. Mondtag (Herr: Dharma/Yama) — Ordnung und Erfolg; betont "
                  "Pflichterfüllung, Gerechtigkeitssinn und Anerkennung.",
    "Ekadashi":   "11. Mondtag (Herr: Vishnu) — spirituelle Läuterung; betont "
                  "Hingabe, Fasten- und Reinigungsqualität, geistige Klarheit.",
    "Dvadashi":   "12. Mondtag (Herr: Vishnu/Aditya) — Vollzug und Weihe; betont "
                  "Grosszügigkeit, Abschluss von Vorhaben und Dankbarkeit.",
    "Trayodashi": "13. Mondtag (Herr: Kamadeva/Shiva) — Anziehung und Genuss; "
                  "betont Charme, Lebensfreude und sinnliche Gestaltungskraft.",
    "Chaturdashi": "14. Mondtag (Herr: Kali/Shiva) — höchste Intensität des "
                   "Paksha; betont Tiefe, Entschlossenheit und die Kraft, "
                   "Altes radikal abzuschliessen.",
    "Purnima":    "Vollmond (Herr: Soma/Mond) — maximale lunare Fülle; betont "
                  "Empfindsamkeit, Ausstrahlung und emotionale Reife.",
    "Amavasya":   "Neumond (Herren: Pitris, die Ahnen) — Innenschau und "
                  "Ahnenverbindung; betont Tiefe, Rückzug und Neubeginn aus der Stille.",
}

# ── Vara (Wochentag) ─────────────────────────────────────────────────────────
VARAS = {
    "Sunday":    "Sonntag (Herr: Sonne/Surya) — Würde, Vitalität, Autorität; die "
                 "Seele und das Selbst stehen im Vordergrund.",
    "Monday":    "Montag (Herr: Mond/Chandra) — Gefühl, Fürsorge, Empfänglichkeit; "
                 "das innere Erleben prägt den Tag.",
    "Tuesday":   "Dienstag (Herr: Mars/Mangala) — Tatkraft, Mut, Durchsetzung; "
                 "Energie und Konfliktfähigkeit sind betont.",
    "Wednesday": "Mittwoch (Herr: Merkur/Budha) — Verstand, Sprache, Handel; "
                 "Kommunikation und Beweglichkeit sind betont.",
    "Thursday":  "Donnerstag (Herr: Jupiter/Guru) — Weisheit, Expansion, Segen; "
                 "Lehre, Sinn und Wachstum sind betont.",
    "Friday":    "Freitag (Herr: Venus/Shukra) — Liebe, Schönheit, Harmonie; "
                 "Genuss, Kunst und Beziehung sind betont.",
    "Saturday":  "Samstag (Herr: Saturn/Shani) — Disziplin, Dauer, Reifung; "
                 "Ernsthaftigkeit, Struktur und Karma-Arbeit sind betont.",
}

# ── Die 27 Nitya-Yogas (Sonne+Mond-Längensumme) ──────────────────────────────
# (Text, malefisch) — malefisch nach klassischer Muhurta-Lehre
NITYA_YOGAS = {
    "Vishkambha": ("Gestützt/aufgestellt — anfängliche Hindernisse, die zu "
                   "Standfestigkeit reifen; nach Überwindung sieghaft.", True),
    "Priti":      ("Zuneigung — liebevolle, verbindende Qualität; begünstigt "
                   "Beziehungen und Freude.", False),
    "Ayushman":   ("Langlebigkeit — vitale, gesundende Qualität; verleiht "
                   "Ausdauer und Lebenskraft.", False),
    "Saubhagya":  ("Glück — begünstigende, freudige Qualität; verleiht Anmut "
                   "und günstige Fügungen.", False),
    "Shobhana":   ("Glanz — strahlende, verschönernde Qualität; verleiht "
                   "Ausstrahlung und Erfolg.", False),
    "Atiganda":   ("Grosse Klippe — herausfordernde Qualität; verlangt Vorsicht "
                   "und lehrt Krisenfestigkeit.", True),
    "Sukarma":    ("Gutes Wirken — tugendhaftes, aufbauendes Handeln; verleiht "
                   "Fleiss und verdiente Früchte.", False),
    "Dhriti":     ("Beständigkeit — ausdauernde, geduldige Qualität; verleiht "
                   "Halt und Verlässlichkeit.", False),
    "Shoola":     ("Stachel/Speer — scharfe, durchdringende Qualität; verlangt "
                   "Achtsamkeit, verleiht aber Fokus.", True),
    "Ganda":      ("Knoten/Klippe — verknotete Qualität; verlangt Geduld beim "
                   "Lösen von Verstrickungen.", True),
    "Vriddhi":    ("Wachstum — mehrende, expandierende Qualität; begünstigt "
                   "Zunahme in allen Belangen.", False),
    "Dhruva":     ("Der Fixe/Polarstern — unerschütterliche Qualität; verleiht "
                   "Stabilität und Dauer.", False),
    "Vyaghata":   ("Schlag/Erschütterung — abrupte Qualität; verlangt Umsicht, "
                   "verleiht aber Durchschlagskraft.", True),
    "Harshana":   ("Freude — erheiternde, beflügelnde Qualität; verleiht "
                   "Optimismus und Leichtigkeit.", False),
    "Vajra":      ("Diamant/Donnerkeil — harte, unbeugsame Qualität; verlangt "
                   "Flexibilität, verleiht aber Härte im guten Sinn.", True),
    "Siddhi":     ("Vollendung — gelingende, meisternde Qualität; begünstigt "
                   "Erfolg und Vollbringen.", False),
    "Vyatipata":  ("Umsturz — instabile Qualität; verlangt besondere Vorsicht "
                   "und lehrt Wandlungsfähigkeit.", True),
    "Variyan":    ("Der Erlesene — komfortable, bevorzugte Qualität; verleiht "
                   "Annehmlichkeit und Wahlfreiheit.", False),
    "Parigha":    ("Eiserner Riegel — blockierende Qualität; verlangt Geduld "
                   "vor Hindernissen, verleiht aber Schutzkraft.", True),
    "Shiva":      ("Der Gütige — segensreiche, friedvolle Qualität; verleiht "
                   "Wohlwollen und inneren Frieden.", False),
    "Siddha":     ("Der Vollendete — erfüllende, könnende Qualität; begünstigt "
                   "Meisterschaft und spirituelle Reife.", False),
    "Sadhya":     ("Das Erreichbare — zielstrebige Qualität; verleiht die "
                   "Fähigkeit, Vorhaben zu Ende zu führen.", False),
    "Shubha":     ("Das Glückverheissende — reine, günstige Qualität; verleiht "
                   "Wohlergehen und Ansehen.", False),
    "Shukla":     ("Das Helle — klare, lichte Qualität; verleiht Reinheit des "
                   "Denkens und Ausstrahlung.", False),
    "Brahma":     ("Das Schöpferische — weihevolle, weise Qualität; verleiht "
                   "Wahrhaftigkeit und schöpferische Autorität.", False),
    "Indra":      ("Der Königliche — führende, ehrenvolle Qualität; verleiht "
                   "Führungsanspruch und Hilfsbereitschaft.", False),
    "Vaidhriti":  ("Auseinanderhaltend — spaltende Qualität; verlangt "
                   "Integrationsarbeit, verleiht aber Unterscheidungskraft.", True),
}

# ── Die 11 Karaṇas (halbe Tithis) ────────────────────────────────────────────
# 7 bewegliche (rotieren) + 4 fixe (an feste Positionen gebunden)
KARANAS = {
    "Bava":        "Beweglich (Symbol: Löwe) — kraftvolle, gesunde Qualität; "
                   "günstig für Beginn und Stärkung.",
    "Balava":      "Beweglich (Symbol: Tiger) — lernende, geistliche Qualität; "
                   "günstig für Studium und Weihen.",
    "Kaulava":     "Beweglich (Symbol: Eber) — verbindende Qualität; günstig "
                   "für Freundschaft und Bündnisse.",
    "Taitila":     "Beweglich (Symbol: Esel) — beharrliche Qualität; günstig "
                   "für Haus, Bau und Bestand.",
    "Gara":        "Beweglich (Symbol: Elefant) — nährende Qualität; günstig "
                   "für Landwirtschaft, Pflege und Aufbau.",
    "Vanija":      "Beweglich (Symbol: Kuh) — handelnde Qualität; günstig für "
                   "Handel, Austausch und Verhandlung.",
    "Vishti":      "Beweglich (Bhadra; Symbol: Hahn) — klassisch gemieden für "
                   "glückverheissende Unternehmungen; stark für Abbruch, "
                   "Trennung und das Beenden von Altem.",
    "Shakuni":     "Fix (Symbol: Vogel) — listige, heilkundige Qualität; "
                   "günstig für Heilmittel und strategisches Handeln.",
    "Chatushpada": "Fix (Symbol: Vierfüssler) — erdende Qualität; günstig für "
                   "Tiere, Ahnenrituale und Bodenständiges.",
    "Naga":        "Fix (Symbol: Schlange) — tiefgründige, okkulte Qualität; "
                   "verlangt Behutsamkeit, verleiht Durchdringung.",
    "Kimstughna":  "Fix — stille, keimhafte Qualität des Neumond-Übergangs; "
                   "günstig für Verborgenes und Vorbereitendes.",
}

# ── Kurzdeutungen der 27 Nakshatras (für den Pañcāṅga-Kontext) ──────────────
NAKSHATRA_BRIEF = {
    "Ashwini":          "Devata: Ashvini-Kumaras (Heiler) · Symbol: Pferdekopf — "
                        "schnelle, heilende, pionierhafte Energie.",
    "Bharani":          "Devata: Yama · Symbol: Yoni — tragende, gebärende, "
                        "transformierende Lebenskraft.",
    "Krittika":         "Devata: Agni · Symbol: Klinge/Flamme — schneidende "
                        "Klarheit, Läuterung, Entschiedenheit.",
    "Rohini":           "Devata: Brahma · Symbol: Ochsenkarren — fruchtbare, "
                        "schöpferische, geniessende Fülle.",
    "Mrigashira":       "Devata: Soma · Symbol: Hirschkopf — suchende, neugierige, "
                        "feinfühlige Energie.",
    "Ardra":            "Devata: Rudra · Symbol: Träne — stürmische, reinigende "
                        "Intensität; Wandlung durch Krise.",
    "Punarvasu":        "Devata: Aditi · Symbol: Köcher — erneuernde, heimkehrende, "
                        "grossherzige Energie.",
    "Pushya":           "Devata: Brihaspati · Symbol: Kuh-Euter — nährende, "
                        "schützende, segensreiche Qualität.",
    "Ashlesha":         "Devata: Nagas · Symbol: Schlange — durchdringende, "
                        "psychologische, umschlingende Tiefe.",
    "Magha":            "Devata: Pitris (Ahnen) · Symbol: Thron — königliche "
                        "Würde, Herkunft, Vermächtnis.",
    "Purva Phalguni":   "Devata: Bhaga · Symbol: Bett/Hängematte — geniessende, "
                        "kreative, gesellige Lebensfreude.",
    "Uttara Phalguni":  "Devata: Aryaman · Symbol: Bett(-pfosten) — verlässliche "
                        "Hilfe, Bund, grosszügige Ordnung.",
    "Hasta":            "Devata: Savitar · Symbol: Hand — Geschick, Handwerk, "
                        "heilende und gestaltende Hände.",
    "Chitra":           "Devata: Tvashtar/Vishvakarma · Symbol: Juwel — "
                        "gestaltende Brillanz, Form- und Schönheitssinn.",
    "Swati":            "Devata: Vayu · Symbol: Spross im Wind — unabhängige, "
                        "bewegliche, ausgleichende Energie.",
    "Vishakha":         "Devata: Indra-Agni · Symbol: Triumphtor — zielstrebige "
                        "Entschlossenheit, Erfolg nach Anstrengung.",
    "Anuradha":         "Devata: Mitra · Symbol: Lotus — Freundschaft, Hingabe, "
                        "Verbindungskraft durch Krisen hindurch.",
    "Jyeshtha":         "Devata: Indra · Symbol: Amulett — Schutzverantwortung, "
                        "Seniorität, Prüfungen der Macht.",
    "Mula":             "Devata: Nirriti · Symbol: Wurzelbündel — radikale "
                        "Wurzelarbeit, Auflösung, Wahrheitssuche.",
    "Purva Ashadha":    "Devata: Apas (Wasser) · Symbol: Fächer — unbesiegbare "
                        "Begeisterung, reinigender Vorwärtsdrang.",
    "Uttara Ashadha":   "Devata: Vishvadevas · Symbol: Stosszahn — dauerhafter "
                        "Sieg, universelle Verantwortung.",
    "Shravana":         "Devata: Vishnu · Symbol: Ohr — Hören, Lernen, "
                        "Überlieferung; Weisheit durch Zuhören.",
    "Dhanishtha":       "Devata: Vasus · Symbol: Trommel — Rhythmus, Wohlstand, "
                        "Ruhm durch gemeinschaftliches Wirken.",
    "Shatabhisha":      "Devata: Varuna · Symbol: leerer Kreis — heilende "
                        "Verborgenheit, Forschergeist, Eigenweg.",
    "Purva Bhadrapada": "Devata: Aja Ekapada · Symbol: Schwertpaar/Bahre — "
                        "visionäre Intensität, Läuterungsfeuer.",
    "Uttara Bhadrapada": "Devata: Ahirbudhnya · Symbol: Zwillingsbeine — stille "
                         "Tiefe, tragende Weisheit, Gelassenheit.",
    "Revati":           "Devata: Pushan · Symbol: Fisch — geleitende Fürsorge, "
                        "sichere Wege, mitfühlender Abschluss.",
}


def _norm_tithi_num(n):
    """tithi_num 1–30 → 1–15 (beide Pakshas teilen die Namensreihe)."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return None
    return ((n - 1) % 15) + 1


def describe(pan: dict) -> list:
    """[(Element, Wert, Deutung), …] für ein panchang-Dict aus astro_engine.
    Fehlende oder unbekannte Werte werden still übersprungen."""
    rows = []
    if not pan:
        return rows
    # Tithi: "Krishna Chaturdashi" → Paksha + Name
    tithi = str(pan.get("tithi", "")).strip()
    if tithi:
        parts = tithi.split()
        paksha = parts[0] if parts and parts[0] in PAKSHAS else pan.get("paksha")
        name = parts[-1] if parts else ""
        txt = TITHIS.get(name, "")
        grp = _TITHI_GROUP_OF.get(_norm_tithi_num(pan.get("tithi_num")))
        if grp:
            txt = (txt + " " if txt else "") + TITHI_GROUPS.get(grp, "")
        if paksha in PAKSHAS and name not in ("Purnima", "Amavasya"):
            txt = (txt + " " if txt else "") + PAKSHAS[paksha]
        if txt:
            rows.append(("Tithi", tithi, txt))
    vara = pan.get("vara")
    if vara in VARAS:
        rows.append(("Vara", vara, VARAS[vara]))
    nak = pan.get("nakshatra")
    if nak in NAKSHATRA_BRIEF:
        lord = pan.get("nakshatra_lord")
        val = f"{nak}" + (f" (Herr: {lord})" if lord else "")
        rows.append(("Nakshatra", val, NAKSHATRA_BRIEF[nak]))
    yoga = pan.get("yoga")
    if yoga in NITYA_YOGAS:
        txt, mal = NITYA_YOGAS[yoga]
        tag = " Klassisch als herausfordernder Nitya-Yoga eingestuft." if mal else ""
        rows.append(("Yoga", yoga, txt + tag))
    kar = pan.get("karana")
    if kar in KARANAS:
        rows.append(("Karana", kar, KARANAS[kar]))
    return rows


def is_malefic_yoga(name: str) -> bool:
    e = NITYA_YOGAS.get(name)
    return bool(e and e[1])

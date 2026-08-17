# Roadmap / Ideensammlung

Internes Notizdokument, kein Teil der ausgelieferten Integration (HACS
installiert bei Kategorie *Integration* ohnehin nur
`custom_components/urlaubszaehler/`, siehe `CLAUDE.md`). Hier werden Ideen
für künftige Versionen gesammelt, bevor sie umgesetzt werden – nichts in
diesem Dokument ist bereits gebaut.

## Verbindliche Rahmenbedingung für alle Punkte

**Bestandsschutz beim Bearbeiten:** Neue Felder (Transportmittel usw.) müssen
bei bereits angelegten Urlauben *nachträglich editierbar* sein, ohne den
Eintrag löschen und neu anlegen zu müssen. Konkret heißt das:

* Neue Felder brauchen einen sinnvollen Default (z. B. Transportmittel
  "unbekannt"), damit `urlaubszaehler.add_vacation` mit gleicher `urlaub_id`
  weiterhin auch *ohne* das neue Feld funktioniert (Abwärtskompatibilität für
  bestehende Automatisierungen).
* Der neue Blueprint-Input muss beim Bearbeiten einer bestehenden
  Automatisierung in der UI erscheinen und ausfüllbar sein – nicht nur beim
  Neuanlegen. Nach dem Speichern greift wie gehabt der bestehende
  "gleiche `urlaub_id` = Update"-Mechanismus.
* Genauso beim Karten-Dialog: falls dort eine Bearbeitungsmöglichkeit für
  bestehende Einträge entsteht (aktuell gibt es nur "Urlaub anlegen"), muss
  sie auch die neuen Felder abdecken.

## Geplant für v1.0.5

### 1. Transportmittel beim Anlegen eines Urlaubs auswählen — erledigt
Beim Anlegen (Karten-Dialog und Blueprint) auswählbar, wie die Anreise
erfolgt: Flugzeug, Auto, Bahn, Schiff oder Unbekannt (Standard), jeweils mit
Icon in Blueprint und Karten-Dialog.

Optional mit Standardwert `unbekannt` umgesetzt (siehe Entscheidung oben):
`vol.Optional(ATTR_TRANSPORTMITTEL, default="unbekannt")` im Service-Schema,
`Vacation.transportmittel` mit demselben Default, `Vacation.from_dict()`
liefert für ältere gespeicherte Urlaube ohne dieses Feld ebenfalls
`unbekannt` (Bestandsschutz getestet). Fünf neue Tests in
`test_urlaube.py`/`test_blueprint.py`, komplette Suite (69 Tests) grün.

*Geänderte Stellen:* `const.py`, `models.py`, `manager.py`, `__init__.py`
(Service-Schema + Antworten), `sensor.py` (Attribut), `services.yaml`,
Blueprint-YAML (neuer Input, beide `add_vacation`-Aufrufe), Karten-Dialog in
`tools/urlaubszaehler-card.src.js`, README (Attribut- und Service-Tabelle).

### 2. Ungefähre Reisedauer — Berechnung erledigt, Kartenanzeige offen
Faustformel je Transportmittel steht als eigenes Modul
`custom_components/urlaubszaehler/distanz.py`: Haversine-Entfernung ×
Umwegfaktor je Verkehrsmittel, geteilt durch eine angenommene
Durchschnittsgeschwindigkeit, plus Pauschale für Pausen (Auto: alle 4,5 Std.
eine 30-Min-Pause) bzw. Vorlauf (Flugzeug: 2 Std.). Deterministisch, kein
Netzwerkzugriff. Werte wie mit dem Nutzer abgestimmt:

| Transportmittel | Geschwindigkeit | Umwegfaktor | Pausen/Vorlauf |
|---|---|---|---|
| Flugzeug | 800 km/h | 1,0 | + 2 Std. Vorlauf |
| Auto | 90 km/h | ×1,3 | alle 4,5 Std. 30 Min |
| Bahn | 120 km/h | ×1,2 | keine |
| Schiff | 35 km/h | ×1,1 | keine |

Fähren o. Ä. bewusst nicht berücksichtigt (siehe „Zu klärende Details" unten,
Punkt 2 – mit dem Nutzer geklärt: einfach akzeptieren).

Neue Sensor-Attribute: `entfernung_km` (immer vorhanden, sobald Koordinaten
bekannt sind – unabhängig vom Transportmittel, deckt auch Punkt 5 unten ab),
`reisedauer_std` und `reisedauer_text` (nur, wenn zusätzlich ein
Transportmittel bekannt ist). 17 neue Tests (`test_distanz.py` + Integration
in `test_urlaube.py`), komplette Suite (86 Tests) grün.

**Anzeige in der Liste — ebenfalls erledigt:** dritte Rasterzeile
(`grid-template-areas`, sowohl Normal- als auch die gestapelte
460-px-Ansicht) mit einer neuen `.reise`-Zeile pro Eintrag, z. B.
„🚗 ca. 14 Std. · 780 km" oder nur „2650 km", wenn kein Transportmittel
bekannt ist. Kein Text an den Bogen der Karte (bewusst, siehe Klärung
„Platz auf der Karte" unten) – nur der Zielname bleibt dort stehen. Per
Playwright-Screenshot in Normal- und gestapelter Ansicht optisch geprüft,
keine Kollisionen. Ollama-Anbindung als Alternative bewusst nicht verfolgt.

Punkt 4 der Roadmap (Icons *auf* dem Kartenbogen/-marker selbst) ist davon
unabhängig und steht noch aus – die `TRANSPORTMITTEL_EMOJI`-Zuordnung dafür
liegt bereits zentral in `urlaubszaehler-card.src.js` bereit.

*Geänderte/neue Stellen:* `distanz.py` (neu), `models.py` (drei neue
`Vacation`-Methoden), `sensor.py` (drei neue Attribute),
`tools/urlaubszaehler-card.src.js` (`_urlaubeLesen`, `_listeZeichnen`, CSS).

### 3. Ankunftszeit erst kurz vorher anzeigen — erledigt
Weit im Voraus steht nur die **Reisedauer** (`reisedauer_text`, z. B.
„ca. 14 Std."), die konkrete **Ankunftsuhrzeit** ersetzt sie erst ab
`ANKUNFTSZEIT_SCHWELLE` (2 Tage vor Abreise, `const.py`) – vorher wäre eine
exakte Uhrzeit bei einer ohnehin groben Schätzung unpassend präzise. Neue
Attribute `ankunft()`/`ankunftszeit_text()` in `models.py`, dabei automatisch
in der **Ortszeit am Ziel** (siehe Punkt 1 unten – `zielzeit.py`, neue
Abhängigkeit `timezonefinder`). Die Karte zeigt in der Liste automatisch die
Ankunftszeit statt der Dauer, sobald das Attribut befüllt ist. 8 neue Tests
(`test_zielzeit.py` + Integration/Schwellwert in `test_urlaube.py`, inkl.
`freezer`), komplette Suite (91 Tests) grün.

### 4. Transportmittel-Icons auf der Karte — erledigt
Das bereits vorhandene `TRANSPORTMITTEL_EMOJI`-Mapping (siehe Punkt 2) wird
jetzt auch am Zielpunkt selbst genutzt: Ein kleines Emoji (✈️🚗🚆🚢) sitzt
knapp über dem farbigen Punkt jedes Ziels, mit demselben Halo-Effekt
(`stroke` in Kartenhintergrundfarbe) wie die Ortsnamen, damit es auf jedem
Hintergrund lesbar bleibt. Bei Transportmittel "unbekannt" bleibt es beim
bisherigen reinen Punkt, kein Icon. Rein visuell, keine neue Abhängigkeit,
kein zusätzlicher Netzwerkaufruf – per Playwright-Screenshot geprüft (auch
herangezoomt, da die Emoji bei Kartengröße recht klein sind).

*Geänderte Stelle:* `tools/urlaubszaehler-card.src.js` (`_karteZeichnen`,
neue CSS-Klasse `.transportmittel-icon`).

### 5. Entfernung in km anzeigen — erledigt
Kam mit Schritt 2/3 mit: `entfernung_km`-Attribut, in der Liste angezeigt.

## Zu klärende Details vor der Umsetzung

Punkte, die bei der Umsetzung sonst erst spät auffallen. Die Befunde zur
Karte stammen aus einer Durchsicht von `tools/urlaubszaehler-card.src.js`.

### 1. Zeitzone am Ziel (betrifft Punkt 3) — erledigt
Bei Fernreisen ist eine Ankunftszeit in Heimatzeit irreführend: Berlin → New
York, Abflug 10:00, 8 Std Flug – Ankunft ist nicht 18:00, sondern 12:00
Ortszeit am Ziel. Genau bei Langstrecken ist die Anzeige am interessantesten.

Umgesetzt wie entschieden: `timezonefinder==8.2.5` als erste Abhängigkeit der
Integration (`manifest.json` → `requirements`), neues Modul `zielzeit.py`.
Bestimmt die IANA-Zeitzone rein aus den Koordinaten, **komplett offline**
(eigene Grenzdaten, kein Netzwerkaufruf) – die Datenschutz-Linie des Projekts
bleibt unangetastet, README entsprechend ergänzt. Die Umrechnung übernimmt
`zoneinfo` aus der Standardbibliothek. Einziger Wermutstropfen: Das Paket
bringt rund **65 MB** an Zeitzonen-Geodaten mit (`du -sh` im venv geprüft) –
spürbar größer als der Rest der Integration zusammen. War dem Nutzer beim
Entscheid bewusst ("auch mit Zusatzpaket"), aber hier nochmal explizit
festgehalten, falls das bei einem zukünftigen Update noch mal überrascht.

### 2. Auto und Bahn zu Zielen über Wasser (betrifft Punkt 2)
Luftlinie × Straßenfaktor kennt keine Fähren: „Mit dem Auto nach Mallorca"
ergäbe rund 15 Stunden und ignoriert die Überfahrt komplett. Entweder bewusst
akzeptieren (es geht ausdrücklich um grobe Werte) oder einen dezenten Hinweis
zeigen, wenn Transportmittel und Route unplausibel wirken.

### 3. Platz auf der Karte (betrifft Punkt 2 und 5)
Die Beschriftungen sind heute nur der Zielname bei 11 px. Die
Kollisionsvermeidung rechnet mit Kästchen von etwa 80 × 13 px und maximal
sechs Ausweichversuchen nach unten; ob ein Label links oder rechts vom Punkt
steht, hängt an einer festen Schwelle bei 72 % der Kartenbreite. Ein Label wie
„Gardasee · ca. 8 Std · 780 km" ist rund dreimal so breit und sprengt beide
Heuristiken, besonders auf Handybreite.

**Empfehlung:** Dauer und Entfernung in die Liste unter der Karte setzen,
nicht an den Bogen.

### 4. Platz in der Listenzeile (betrifft Punkt 2 und 5)
Jede Zeile ist ein festes Raster (`punkt | ziel | count` /
`punkt | wer | ab`), unter 460 px Breite auf zwei Spalten gestapelt. Für Dauer
und Entfernung ist keine Zelle frei – eine dritte Rasterzeile oder eine
Zusammenlegung sollte vorab festgelegt werden, inklusive der gestapelten
Ansicht.

### 5. Fehlende Koordinaten (betrifft Punkt 2 und 5)
Antwortet Nominatim gerade nicht, steht in der Liste schon heute „Ort nicht
gefunden" (`ohneOrt`). Ohne Koordinaten gibt es auch keine Entfernung und
keine Dauer – dieser Fall braucht dieselbe saubere Behandlung, sonst erscheint
„0 km, ca. 0 Std".

### 6. Bearbeiten direkt aus der Karte — erledigt
Ein Klick auf eine Zeile öffnet für Administratoren jetzt den vorhandenen
Anlege-Dialog im Bearbeiten-Modus, vorbefüllt aus der zugehörigen
Blueprint-Automatisierung (Teilnehmer, Ziel, Datum/Uhrzeit, Transportmittel,
Geräte). Titel und Knopf wechseln auf „Urlaub bearbeiten"/„Speichern". Beim
Speichern wird **dieselbe** Automatisierungs-ID weiterverwendet – exakt der
Aufruf, den Home Assistants eigener Automatisierungs-Editor auch macht,
aktualisiert also den bestehenden Eintrag statt einen zweiten anzulegen
(erfüllt damit die Bestandsschutz-Rahmenbedingung von oben).

Technisch: der Blueprint leitet `urlaub_id` aus der eigenen `entity_id` ab
(`this.entity_id | replace('automation.', '')`) – der Rückweg
(`"automation." + urlaubId`) liefert also zuverlässig dieselbe
Automatisierung zurück, ohne eine weitere Zuordnungstabelle zu brauchen.
Deren `attributes.id` (die interne Config-ID) wird für
`GET/POST config/automation/config/{id}` gebraucht.

**Absichtlich nicht enthalten:** Löschen aus der Karte. Das würde nicht nur
den Urlaub, sondern die ganze Automatisierung entfernen müssen (sonst legt
sie den Urlaub beim nächsten Lauf einfach neu an) – ein eigener, größerer
Schritt, den ursprünglich niemand angefragt hat. Entfernen bleibt wie bisher
über Konfigurieren → Geplante Urlaube entfernen oder
`urlaubszaehler.remove_vacation` möglich.

**Rückfall abgesichert:** Existiert keine passende Automatisierung (z. B. ein
Urlaub, der per Dienstaufruf ohne Blueprint angelegt wurde), öffnet der Klick
stattdessen wie bisher die normale Detailansicht – kein kaputter Dialog.
Nicht-Administratoren sehen ebenfalls unverändert nur die Detailansicht.

Per Playwright funktional geprüft (nicht nur optisch): Vorbefüllung korrekt,
Speichern schickt den POST an dieselbe Automatisierungs-ID, und der
Rückfall auf `hass-more-info` löst zuverlässig aus, wenn keine
Automatisierung gefunden wird.

*Geänderte Stelle:* `tools/urlaubszaehler-card.src.js`
(`_bearbeitenLaden` neu, `_dialogOeffnen`/`_speichern` erweitert,
Klick-Handler in `_listeZeichnen`).

### 7. Desktop-Zentrierungsfehler — erledigt
Vom Nutzer ursprünglich gemeldet („im Desktop-Modus sieht die Karte
verschoben aus"), aber nie reproduziert: Eine Messung bei 1920 px ergab in
Sections, Masonry und Panel jeweils eine exakt zentrierte Karte. Ein vom
Nutzer nachgereichter Screenshot (Desktop-Modus im mobilen Browser) zeigte die
Karte ebenfalls sauber zentriert; vermutlich hatte der zuvor aktive
Dashboard-Bearbeiten-Modus die Wahrnehmung verzerrt. Nutzer bestätigt: passt
jetzt. Kein Blocker mehr für 1.0.5.

## Geprüft und bewusst nicht verfolgt

Damit diese Ideen nicht in einer künftigen Runde erneut vorgeschlagen werden:

* **Rückreisedatum / zweiter Countdown** – nicht gewünscht, komplett verworfen.
* **Reise-Kalendereintrag** (`calendar`-Entity pro Urlaub) – nicht gewünscht.
* **Packliste als To-do-Liste** – nicht gewünscht.
* **Freitext-/Notizfeld** (Budget, Buchungsnummer o. Ä.) – nicht gewünscht.
* **Echte Urlaubs-Historie** statt Löschen nach 24 h – nicht gewünscht.

## Offene Fragen für die Umsetzungsrunde

* Pflichtfeld oder optional: Transportmittel?
* Genaue Faktoren/Geschwindigkeiten der Faustformel je Transportmittel
  (müssen noch festgelegt werden).
* Soll die optionale Ollama-Anbindung (Punkt 2, zweiter Absatz) überhaupt
  verfolgt werden, oder reicht dauerhaft die Faustformel?

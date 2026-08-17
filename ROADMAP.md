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

### 1. Transportmittel beim Anlegen eines Urlaubs auswählen
Beim Anlegen (Karten-Dialog und/oder Blueprint) auswählen, wie die Anreise
erfolgt – z. B. Flugzeug, Auto, Bahn, Schiff, jeweils mit passendem Icon.

*Betroffene Stellen:* `const.py` (neue `ATTR_`/`CONF_`-Konstante),
`models.py` (`Vacation`-Feld), `__init__.py` (Service-Schema), Blueprint-YAML
(neuer Input), Karten-Dialog in `tools/urlaubszaehler-card.src.js`.

### 2. Ungefähre Reisedauer auf der Kartenlinie anzeigen
Auf/neben dem gestrichelten Bogen zum Ziel eine grobe Dauer einblenden (keine
exakte Navigation, "Pi mal Daumen").

- **Standardweg:** feste Faustformel je Transportmittel – Luftlinienentfernung
  (Haversine, aus den vorhandenen Koordinaten) × Straßenfaktor je
  Verkehrsmittel, geteilt durch eine angenommene Durchschnittsgeschwindigkeit,
  plus Pauschale für Pausen (z. B. Auto: alle ~4,5 Std. eine 30-Min-Pause).
  Deterministisch, kein Netzwerkzugriff nötig, passt zur bestehenden
  "möglichst wenig externe Aufrufe"-Linie. Bildet länderspezifisch andere
  Reisezeiten automatisch über die echte Entfernung ab, ohne eigene
  Ländertabelle.
- **Optionale Verfeinerung/Alternative (später, nicht Standard):** Schätzung
  über den vorhandenen Ollama/Qwen-3B-vServer des Nutzers erfragen (HA hat
  eine `ollama`-Integration bzw. lässt sich per REST ansprechen). Käme mit
  einer zusätzlichen Abhängigkeit von der Erreichbarkeit des vServers und
  nicht-deterministischen, zu parsenden Antworten – deshalb höchstens
  optionale Ergänzung, nicht Ersatz für die Faustformel.

*Betroffene Stellen:* neue Berechnung in `models.py` (oder eigenes Modul),
neues Sensor-Attribut, Darstellung in `tools/urlaubszaehler-card.src.js`.

### 3. Ankunftszeit erst kurz vorher anzeigen
Weit im Voraus nur die **Reisedauer** zeigen (z. B. "ca. 8 Stunden"), die
konkrete **Ankunftsuhrzeit** (Start + Dauer) erst ab einem Schwellwert von
1–2 Tagen vor Abreise – vorher wäre eine exakte Uhrzeit bei einer ohnehin
groben Schätzung unpassend präzise. Kleine, isolierte Logikänderung an der
bestehenden `nachricht`/Attribut-Berechnung in `models.py`.

### 4. Transportmittel-Icons auf der Karte
Passend zu Punkt 1 – der Bogen bzw. ein kleines Symbol am Zielpunkt sieht je
nach Transportmittel anders aus (Flugzeug/Auto/Zug/Schiff), rein visuell,
kein zusätzlicher Netzwerkaufruf.

### 5. Entfernung in km anzeigen
Ergänzt die Dauer um eine harte Zahl (aus denselben Koordinaten per
Haversine), keine neue Abhängigkeit.

## Zu klärende Details vor der Umsetzung

Punkte, die bei der Umsetzung sonst erst spät auffallen. Die Befunde zur
Karte stammen aus einer Durchsicht von `tools/urlaubszaehler-card.src.js`.

### 1. Zeitzone am Ziel (betrifft Punkt 3)
Bei Fernreisen ist eine Ankunftszeit in Heimatzeit irreführend: Berlin → New
York, Abflug 10:00, 8 Std Flug – Ankunft ist nicht 18:00, sondern 12:00
Ortszeit am Ziel. Genau bei Langstrecken ist die Anzeige am interessantesten.

**Entschieden:** Ortszeit am Reiseziel anzeigen, dafür wird eine Abhängigkeit
in Kauf genommen (`manifest.json` → `requirements`, bislang leer). Ein Paket
wie `timezonefinder` liefert aus Koordinaten die IANA-Zeitzone und arbeitet
dabei **offline** (eigene Grenzdaten, kein Netzwerkaufruf) – die
Datenschutz-Linie des Projekts bleibt damit unangetastet. Die eigentliche
Umrechnung übernimmt `zoneinfo` aus der Standardbibliothek.

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

### 6. Bearbeiten direkt aus der Karte
Ergänzt die verbindliche Rahmenbedingung oben um den eigentlichen
Komfortgewinn: Ein Klick auf eine Zeile öffnet heute nur die Detailansicht
(`hass-more-info`); bearbeiten geht ausschließlich über Einstellungen →
Automatisierungen. Der vorhandene Anlege-Dialog ließe sich vorbefüllt zum
Bearbeiten wiederverwenden.

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

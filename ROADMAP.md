# Roadmap / Ideensammlung

Internes Notizdokument, kein Teil der ausgelieferten Integration (HACS
installiert bei Kategorie *Integration* ohnehin nur
`custom_components/urlaubszaehler/`, siehe `CLAUDE.md`). Hier werden Ideen
für künftige Versionen gesammelt, bevor sie umgesetzt werden – nichts in
diesem Dokument ist bereits gebaut.

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

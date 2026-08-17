# 🏖️ Urlaubszähler

Zähle die Tage bis zum Urlaub – eine Home-Assistant-Integration, die für jeden
geplanten Urlaub einen eigenen Countdown-Sensor erzeugt, inklusive Blueprint zum
Anlegen neuer Urlaube und für Push-Benachrichtigungen zu festen Vorlaufzeiten.

<p align="center">
  <img src="https://raw.githubusercontent.com/frecem/Urlaubszaehler/main/docs/bilder/06-karte-hell.png" width="49%" alt="Urlaubszähler-Karte im hellen Design">
  <img src="https://raw.githubusercontent.com/frecem/Urlaubszaehler/main/docs/bilder/07-karte-dunkel.png" width="49%" alt="Urlaubszähler-Karte im dunklen Design">
</p>

*Alle Bilder sind echte Aufnahmen aus einer laufenden Home-Assistant-Instanz
(2026.2) mit dieser Integration. Sie zeigen ausschließlich erfundene
Beispieldaten – siehe [Datenschutz](#8-datenschutz).*

* Einrichtung komplett über die UI (Config Flow) – **keine Helfer von Hand anlegen**.
  `input_datetime`, `input_text` & Co. sind nicht nötig; die Integration verwaltet
  alle Daten intern in ihrem eigenen Speicher (`.storage/urlaubszaehler.<entry_id>`).
* Beliebig viele Urlaube parallel.
* Countdown stoppt bei `0 Tage, 0 Stunden, 0 Minuten` – es wird nicht negativ
  weitergerechnet.
* Der Sensor wird **exakt 24 Stunden nach dem Reisezeitpunkt** automatisch und
  restlos entfernt (auch aus der Entitäten-Registry).

Mindestversion: **Home Assistant 2024.11**

<details>
<summary><strong>Was ist neu in 1.0.2?</strong></summary>

* Die Integration liefert jetzt ein eigenes Marken-Icon mit
  (`custom_components/urlaubszaehler/brand/`), sichtbar unter
  *Einstellungen → Geräte & Dienste*. Im HACS-Installationsdialog selbst
  taucht es wegen eines aktuell offenen HACS-Fehlers
  ([hacs/integration#5223](https://github.com/hacs/integration/issues/5223))
  noch nicht auf – das liegt an HACS, nicht an dieser Integration, und
  erledigt sich von selbst, sobald HACS das behebt.
* Ein Platzhaltername im Einrichtungsdialog („z. B. Papa, Fiene, Mama")
  wurde entfernt und durch generische Rollenbezeichnungen ersetzt.
* Alle Bilder in dieser Anleitung werden jetzt über absolute Adressen
  eingebunden, damit sie auch beim Öffnen des Repositorys direkt aus Home
  Assistant/HACS heraus korrekt angezeigt werden.

</details>

---

## 1. Installation über HACS (empfohlen)

[![Repository zu HACS hinzufügen](https://raw.githubusercontent.com/frecem/Urlaubszaehler/main/docs/badges/hacs.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=frecem&repository=Urlaubszaehler&category=integration)

Ein Klick auf den Knopf öffnet HACS direkt bei diesem Repository. Falls der
Knopf nicht funktioniert (etwa weil „My Home Assistant" nicht eingerichtet ist),
geht es von Hand genauso:

1. **HACS** öffnen → oben rechts **⋮** → **Benutzerdefinierte Repositories**
2. Repository: `https://github.com/frecem/Urlaubszaehler`
   Kategorie: **Integration** → **Hinzufügen**
3. In HACS nach `Urlaubszähler` suchen → **Herunterladen**
4. Home Assistant **neu starten**

**Damit ist alles installiert.** Die Integration bringt die Lovelace-Karte, den
Blueprint und die Beispiel-Kartenkonfigurationen mit; nichts davon muss von Hand
kopiert oder eingetragen werden:

| Was | Wohin es kommt | Wann |
|---|---|---|
| Die Integration | `custom_components/urlaubszaehler/` | durch HACS |
| Der Blueprint | `blueprints/automation/urlaubszaehler/` | beim ersten Start der Integration |
| Die Lovelace-Karte | wird unter `/urlaubszaehler/urlaubszaehler-card.js` ausgeliefert und automatisch ins Frontend geladen | beim Start der Integration |
| Beispiel-Karten | `custom_components/urlaubszaehler/lovelace/urlaubszaehler_karte.yaml` | durch HACS |

Ein **Eintrag unter Dashboards → Ressourcen ist nicht nötig** – die Integration
meldet die Karte selbst an. Nach dem Neustart einmal den Browser hart neu laden
(Strg + F5), dann steht „Urlaubszähler" in der Kartenauswahl.

> Der Blueprint wird bei einem Update der Integration aktualisiert – es sei
> denn, du hast ihn selbst angepasst. Eigene Änderungen bleiben erhalten.

### Installation ohne HACS

Den Ordner `custom_components/urlaubszaehler/` aus diesem Repository nach
`config/custom_components/` kopieren und Home Assistant neu starten. Mehr ist
auch hier nicht nötig – Karte und Blueprint kommen mit.

---

## 2. Einrichten

[![Integration hinzufügen](https://raw.githubusercontent.com/frecem/Urlaubszaehler/main/docs/badges/integration.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=urlaubszaehler)

Oder von Hand: **Einstellungen → Geräte & Dienste → Integration hinzufügen** →
nach `Urlaubszähler` suchen.

1. **Schritt 1:** Anzahl der Personen und Anzahl der Familien eintragen.
2. **Schritt 2:** Namen der Personen eintragen (z. B. `Papa`, `Mama`).
3. **Schritt 3:** Familiennamen eintragen und optional festlegen, welche
   Personen zu einer Familie gehören.

| Schritt 1 | Schritt 2 | Schritt 3 |
|---|---|---|
| ![Anzahl](https://raw.githubusercontent.com/frecem/Urlaubszaehler/main/docs/bilder/01-einrichtung-anzahl.png) | ![Personen](https://raw.githubusercontent.com/frecem/Urlaubszaehler/main/docs/bilder/02-einrichtung-personen.png) | ![Familien](https://raw.githubusercontent.com/frecem/Urlaubszaehler/main/docs/bilder/03-einrichtung-familien.png) |

Danach existiert je Person und Familie eine Entität, z. B.
`binary_sensor.urlaubszahler_papa` – diese Namen tauchen im Blueprint zur
Auswahl auf. Alle Entitäten hängen an einem gemeinsamen Gerät:

![Geräteseite](https://raw.githubusercontent.com/frecem/Urlaubszaehler/main/docs/bilder/08-geraeteseite.png)

> Namen später ändern: **Einstellungen → Geräte & Dienste → Urlaubszähler →
> Konfigurieren**. Dort lassen sich auch geplante Urlaube vorzeitig löschen.

---

## 3. Einen Urlaub anlegen

### Aus der Karte heraus (am schnellsten)

Die Karte hat unten den Knopf **„＋ Urlaub anlegen"**. Er öffnet ein Fenster mit
Wer / Wohin / Wann und den Mobilgeräten für die Erinnerungen:

<p align="center">
  <img src="https://raw.githubusercontent.com/frecem/Urlaubszaehler/main/docs/bilder/09-urlaub-anlegen.png" width="70%" alt="Dialog zum Anlegen eines Urlaubs">
</p>

Beim Speichern legt die Karte im Hintergrund eine ganz normale Automatisierung
aus dem Blueprint an – mit Countdown-Sensor **und** allen Push-Erinnerungen. Du
findest sie danach unter *Einstellungen → Automatisierungen* und kannst sie dort
weiter anpassen.

Der Knopf erscheint nur für Administratoren (nur die dürfen Automatisierungen
anlegen) und lässt sich über die Option `show_add: false` ausblenden.

### Über den Blueprint

**Einstellungen → Automatisierungen & Szenen → Blueprints** →
*Urlaubszähler – Urlaub anlegen & erinnern* anklicken.

Taucht der Blueprint nicht sofort auf, einmal über **Entwicklerwerkzeuge → YAML
→ Blueprints neu laden** aktualisieren.

| Feld | Bedeutung |
|---|---|
| **Wer fährt in den Urlaub?** | Eine Person, mehrere Personen oder eine ganze Familie |
| **Wohin geht die Reise?** | Freitext, z. B. `Gardasee` |
| **Wann geht es los?** | Datum **und** genaue Uhrzeit |
| **Mobilgeräte** | Geräte mit der HA-App, die Push bekommen |
| **Vorlaufzeiten** | Standard: 60, 40, 20, 10, 5 und 1 Tag vorher |
| **Uhrzeit der Erinnerung** | Standard: 09:00 Uhr |

![Blueprint-Formular](https://raw.githubusercontent.com/frecem/Urlaubszaehler/main/docs/bilder/04-blueprint.png)

Beim **Speichern** der Automatisierung wird der Sensor sofort erzeugt. Für jeden
weiteren Urlaub legst du einfach eine weitere Automatisierung aus demselben
Blueprint an.

---

## 4. Der Sensor

Pro Urlaub entsteht eine Entität wie `sensor.urlaubszahler_urlaub_papa_und_mama_gardasee`.

**Status:** der Reisebeginn als **Unix-Zeit (Dezimal, Sekunden)**. Die Uhrzeit
wird in der in Home Assistant eingestellten Zeitzone (z. B. `Europe/Berlin`)
interpretiert, inklusive Sommer-/Winterzeit. Aus diesem einen Wert lassen sich
Tage, Stunden und Minuten jederzeit exakt ableiten – im Sensor selbst wie auch
in jeder Lovelace-Karte.

**Attribute:**

| Attribut | Beispiel |
|---|---|
| `nachricht` | `Der Urlaub von Papa und Mama ist in 12 Tagen, 5 Stunden und 42 Minuten. Die Reise geht nach Gardasee.` |
| `wer` / `namen` | `Papa und Mama` / `["Papa", "Mama"]` |
| `ziel` | `Gardasee` |
| `transportmittel` | `flugzeug`, `auto`, `bahn`, `schiff` oder `unbekannt` (Standard) |
| `start` / `start_zeitstempel` | `2026-08-14T07:30:00+02:00` / `1786764600.0` |
| `tage`, `stunden`, `minuten` | `12`, `5`, `42` (stoppen bei `0`) |
| `verbleibende_sekunden` | `1058520` |
| `gestartet` | `true`, sobald der Reisezeitpunkt erreicht ist |
| `wird_geloescht_am` | `2026-08-15T07:30:00+02:00` |
| `zeitzone` | `Europe/Berlin` |
| `breitengrad` / `laengengrad` | `45.65` / `10.65` (für die Karte, sonst `null`) |
| `koordinaten_quelle` | `geocoding`, `manuell` oder `null` |
| `gefunden_als` | `Lago di Garda, Italia` |

---

## 5. Die Urlaubszähler-Karte fürs Dashboard

Die Integration bringt eine eigene Lovelace-Karte mit. Sie
zeigt alle geplanten Urlaube als kompakte Liste und darüber eine Weltkarte:
vom Standort des Home-Assistant-Servers führt zu jedem Reiseziel ein
gestrichelter Bogen. Der Kartenausschnitt richtet sich automatisch nach
Zuhause und allen Zielen; mehrere Reisen zum selben Ort laufen nebeneinander
statt übereinander.

**Einrichten:** nichts zu tun. Die Karte wird von der Integration ausgeliefert
und angemeldet. Dashboard bearbeiten → **Karte hinzufügen** → „Urlaubszähler".

**Optionen** (auch im grafischen Editor der Karte einstellbar):

| Option | Standard | Bedeutung |
|---|---|---|
| `title` | `Urlaubszähler` | Überschrift, leer lassen blendet sie aus |
| `show_map` | `true` | Weltkarte anzeigen |
| `map_height` | `260` | Höhe der Karte in Pixeln |
| `max` | `0` | Höchstzahl angezeigter Urlaube (`0` = alle) |
| `show_add` | `true` | Knopf „＋ Urlaub anlegen" unten in der Karte |
| `entities` | – | Feste Sensor-Auswahl statt automatischer Erkennung |

```yaml
type: custom:urlaubszaehler-card
title: 🏖️ Urlaubszähler
show_map: true
map_height: 260
```

![Dashboard mit der Karte](https://raw.githubusercontent.com/frecem/Urlaubszaehler/main/docs/bilder/05-dashboard-hell.png)

Ein Klick auf eine Zeile öffnet die Detailansicht des jeweiligen Sensors.
Reiseziele ohne Koordinaten erscheinen in der Liste mit dem Hinweis
„Ort nicht gefunden", aber nicht auf der Karte.

Fertige Konfigurationen zum Kopieren – auch reine Bordmittel-Karten ohne die
eigene Karte – stehen in
[`custom_components/urlaubszaehler/lovelace/urlaubszaehler_karte.yaml`](custom_components/urlaubszaehler/lovelace/urlaubszaehler_karte.yaml).
Nach der Installation liegt die Datei auch auf deinem Server.

### Woher kommen die Koordinaten?

Beim Anlegen eines Urlaubs schlägt die Integration den Ortsnamen einmalig bei
**OpenStreetMap/Nominatim** nach und speichert das Ergebnis. Jeder Ort wird nur
einmal abgefragt; weitere Reisen zum selben Ziel nutzen den Zwischenspeicher.
Ist ein Ortsname mehrdeutig oder unbekannt, lässt sich im Blueprint
*„Zielort selbst auf der Karte setzen"* einschalten und der Punkt von Hand
setzen – manuelle Koordinaten haben immer Vorrang.

Ohne Internetverbindung schlägt nur die Ortssuche fehl; der Urlaub wird
trotzdem angelegt und der Countdown läuft normal. Ein fehlgeschlagener Versuch
wird alle 30 Minuten wiederholt – war OpenStreetMap nur kurz nicht erreichbar,
taucht das Ziel später von allein auf der Karte auf.

### Karte neu bauen

Die Länderumrisse stammen von [Natural Earth](https://www.naturalearthdata.com/)
(gemeinfrei) und stecken vereinfacht und delta-kodiert (~35 KB) direkt in der
Karte – es werden keine Kartenkacheln von fremden Servern nachgeladen. Nach
Änderungen an `tools/urlaubszaehler-card.src.js`:

```bash
python3 tools/build_card.py
```

---

## 6. Services

| Service | Zweck |
|---|---|
| `urlaubszaehler.add_vacation` | Urlaub anlegen bzw. bei gleicher `urlaub_id` aktualisieren |
| `urlaubszaehler.remove_vacation` | Urlaub und Sensor sofort entfernen |
| `urlaubszaehler.list_vacations` | Alle Urlaube inkl. Restzeit zurückgeben |

```yaml
action: urlaubszaehler.add_vacation
data:
  teilnehmer:
    - binary_sensor.urlaubszahler_papa
    - binary_sensor.urlaubszahler_mama
  ziel: Gardasee
  start: "2026-08-14 07:30:00"
  urlaub_id: sommerurlaub_2026
  transportmittel: auto  # optional, Standard: unbekannt
```

---

## 7. Tests

Die Integration wird gegen ein echtes Home Assistant getestet
(`pytest-homeassistant-custom-component`):

```bash
python3 -m venv .venv && .venv/bin/pip install homeassistant pytest-homeassistant-custom-component
.venv/bin/python -m pytest
```

Abgedeckt sind unter anderem der vollständige Einrichtungsdialog, die drei
Services, das Auflösen von Teilnehmern, das Zwischenspeichern der Koordinaten,
der Countdown-Stopp bei 0, das Löschen exakt 24 Stunden nach der Abreise
(inklusive Zeitumstellung), der Neustart – und der Blueprint selbst: er wird
von Home Assistant geladen, zu einer echten Automatisierung gemacht und für
jede der sechs Vorlaufzeiten geprüft.

---

## 8. Datenschutz

Kurz gesagt: Die Integration verlässt dein Netzwerk nur an einer einzigen
Stelle, und die kannst du abschalten.

**Was das Haus verlässt**

| Wann | Wohin | Was |
|---|---|---|
| Beim Anlegen eines Urlaubs, einmal je Reiseziel | `nominatim.openstreetmap.org` | Der eingetippte Ortsname (z. B. „Gardasee"), die eingestellte Sprache und ein Kennzeichen der Integration als User-Agent |

Das Ergebnis wird dauerhaft gespeichert; derselbe Ort wird kein zweites Mal
abgefragt. Es werden **keine** Namen, Reisedaten, Koordinaten deines Zuhauses
oder Gerätekennungen übertragen. Nominatim ist ein Dienst der OpenStreetMap
Foundation (Sitz in Großbritannien);
[Datenschutzhinweise](https://wiki.osmfoundation.org/wiki/Privacy_Policy).

**So vermeidest du auch diese eine Anfrage:** Im Blueprint *„Zielort selbst auf
der Karte setzen"* einschalten und den Punkt von Hand setzen. Dann findet gar
keine Ortssuche statt und die Integration arbeitet vollständig offline.

**Was das Haus nicht verlässt**

* Die Weltkarte steckt als Vektorgrafik in der Karte selbst – es werden
  **keine Kartenkacheln** von fremden Servern geladen. Kein Google Maps,
  kein Mapbox, keine Zählpixel.
* Keine Telemetrie, keine Nutzungsstatistik, keine externen Schriftarten
  oder Skripte.
* Alle Urlaubsdaten liegen ausschließlich in
  `.storage/urlaubszaehler.<entry_id>` auf deinem eigenen Server.
* Push-Nachrichten laufen über die Home-Assistant-App und nehmen den Weg, den
  du dort ohnehin nutzt.

**Zu den Bildern in dieser Anleitung**

Alle Screenshots wurden mit erfundenen Beispieldaten erzeugt: „Papa", „Mama",
„Kind", „Familie Muster". Der Heimatmarker auf der Karte liegt auf dem
geografischen Mittelpunkt Deutschlands (51,1657° N / 10,4515° O) und damit auf
keiner Wohnanschrift. Die Badges oben liegen als SVG im Repository, damit beim
Betrachten der Anleitung – auch innerhalb von HACS – keine Anfrage an einen
fremden Server entsteht.

---

## 9. Gut zu wissen

* **Auto-Delete:** Ein Hintergrundtask prüft minütlich; der Sensor verschwindet
  in der Minute, in der `Reisezeitpunkt + 24 h` überschritten wird.
* Der Blueprint wird von der Integration bereitgestellt und bei Updates
  erneuert – eigene Änderungen daran bleiben unangetastet.
* Löschst du die Automatisierung, bleibt der Sensor bis zum Auto-Delete bestehen.
  Sofort entfernen: **Urlaubszähler → Konfigurieren → Geplante Urlaube entfernen**
  oder `urlaubszaehler.remove_vacation`.
* Die Karte wird unter `/urlaubszaehler/urlaubszaehler-card.js` ausgeliefert.
  Die Versionsnummer hängt an der URL, damit der Browser nach einem Update
  nicht die alte Fassung aus dem Zwischenspeicher nimmt.
* Push-Nachrichten nutzen `notify.mobile_app_<Gerätename>`. Erscheint kein
  Gerät zur Auswahl, ist die Home-Assistant-App auf dem Handy noch nicht
  eingerichtet.
* Die Benachrichtigungen zählen **ganze Kalendertage** – „60 Tage vorher"
  meldet sich also an dem Tag, der 60 Kalendertage vor dem Abreisedatum liegt.

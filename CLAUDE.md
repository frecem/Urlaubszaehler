# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Sprache

Code, Kommentare, Docstrings, Bezeichner, Commit-Messages, README und die
Benutzeroberfläche sind **auf Deutsch**. Neue Beiträge halten sich daran
(Ausnahme: Home-Assistant-eigene API-Namen und `translations/en.json`).

## Befehle

Tests laufen gegen ein echtes Home Assistant über
`pytest-homeassistant-custom-component`. Das braucht **Python ≥ 3.12** – ein
System-Python 3.11 kann Home Assistant nicht installieren (PyRIC scheitert beim
Bauen). In dieser Umgebung liegt `/usr/bin/python3.13`.

```bash
# Umgebung anlegen
uv venv --python 3.13 .venv && .venv/bin/pip install homeassistant pytest-homeassistant-custom-component
# oder: python3.13 -m venv .venv && .venv/bin/pip install homeassistant pytest-homeassistant-custom-component

.venv/bin/python -m pytest                    # alle Tests (pytest.ini: testpaths=tests, asyncio_mode=auto)
.venv/bin/python -m pytest tests/test_blueprint.py -q          # eine Datei
.venv/bin/python -m pytest tests/test_urlaube.py::test_24_stunden_auch_bei_zeitumstellung -q   # ein Test
```

Karte neu bauen (nach jeder Änderung an `tools/urlaubszaehler-card.src.js`):

```bash
python3 tools/build_card.py     # erzeugt custom_components/urlaubszaehler/frontend/urlaubszaehler-card.js
node --check custom_components/urlaubszaehler/frontend/urlaubszaehler-card.js
```

`custom_components/urlaubszaehler/frontend/urlaubszaehler-card.js` ist
**generiert** – niemals von Hand bearbeiten. Das Skript lädt die Natural-Earth-
Länderumrisse (Cache: `tools/.ne_50m_countries.geojson`, gitignoriert),
vereinfacht sie per Ramer-Douglas-Peucker, kodiert sie zigzag/varint-delta und
setzt sie an die Stelle von `__WORLD__` in der Quelldatei. Ein Round-Trip-Assert
im Skript stellt sicher, dass die Kodierung verlustfrei bleibt.

## Architektur

### Alles steckt im Integrationsordner – wegen HACS

HACS installiert bei Kategorie *Integration* **ausschließlich**
`custom_components/urlaubszaehler/`. Deshalb liegen dort auch Dinge, die
sonst woanders lägen:

* `frontend/urlaubszaehler-card.js` – die Lovelace-Karte
* `blueprints/automation/urlaubszaehler/urlaub_anlegen.yaml` – der Blueprint
* `lovelace/urlaubszaehler_karte.yaml` – Beispielkonfiguration der Karte

Nichts außerhalb dieses Ordners wird beim Nutzer landen. Neue mitzuliefernde
Dateien müssen dort hinein.

### Auslieferung von Karte und Blueprint (`card.py`, `blueprints.py`)

`card.py` registriert die Datei per `async_register_static_paths` unter
`/urlaubszaehler/urlaubszaehler-card.js` und trägt sie als **Lovelace-Ressource**
ein (`LOVELACE_DATA` → `resources.async_create_item`), mit `?v=<Version>` gegen
den Browser-Cache. **Nicht** auf `frontend.add_extra_js_url` umstellen: das lädt
das Modul *vor* dem Scoped-Custom-Element-Registry-Polyfill, die Karte landet in
der nativen Registry und Home Assistant meldet „Custom element doesn't exist".

`blueprints.py` kopiert den Blueprint ins Konfigurationsverzeichnis, aber nur
dann überschreibend, wenn die Prüfsumme der Datei auf der Platte der zuletzt
geschriebenen entspricht (`STORE_BLUEPRINT_PRUEFSUMME` im `Store`). So bleiben
Änderungen des Nutzers erhalten. Danach wird der Blueprint-Cache zurückgesetzt.

### Datenfluss eines Urlaubs

1. Karte (eigener Dialog) oder Blueprint ruft `urlaubszaehler.add_vacation`
   (`teilnehmer`, `ziel`, `start`, optional `urlaub_id`, `koordinaten`).
2. `UrlaubszaehlerManager` (`manager.py`) löst Teilnehmer auf, geokodiert das
   Ziel über Nominatim (`geocoding.py`, gecacht im `Store`), legt ein
   `Vacation`-Objekt (`models.py`) an und feuert `SIGNAL_VACATION_ADDED`.
3. `sensor.py` erzeugt daraufhin sofort eine `UrlaubSensor`-Entität; die
   Teilnehmer-`binary_sensor`s abonnieren dieselben Signale in
   `async_added_to_hass` (sonst hinken sie bis zu 30 s hinterher).
4. Ein Minutentask (`PURGE_INTERVAL`) ruft `async_purge_expired`; ein
   30-Minuten-Task trägt fehlende Koordinaten nach
   (`async_koordinaten_nachtragen`, greift bei Nominatim-503).

Der Sensorzustand ist der **Unix-Zeitstempel der Abreise** (Dezimalsekunden);
Tage/Stunden/Minuten und die fertige `nachricht` stehen in den Attributen und
werden in `extra_state_attributes` live berechnet. Die Restzeit wird bei 0
abgeschnitten (`Restzeit.from_seconds` → `max(0, …)`), nie negativ.

### Zwei Fallstricke, die schon Fehler verursacht haben

* **Auto-Delete rechnet über UTC.** `models.Vacation.delete_at` addiert die 24
  Stunden auf die UTC-Zeit, nicht auf die lokale – lokale Addition ergibt an der
  Zeitumstellung 23 bzw. 25 echte Stunden. Test dafür existiert für beide
  Umstellungen.
* **Entfernen heißt Registry-Eintrag entfernen.** `async_remove()` löscht nur
  den State. Der Sensor muss über
  `entity_registry.async_get_entity_id(Platform.SENSOR, DOMAIN, unique_id)` +
  `registry.async_remove(entity_id)` verschwinden, sonst bleibt eine Leiche im
  Entitätenregister.

### Entity-IDs

Home Assistant transliteriert beim Slugify `ä → a`. Das Gerät heißt
„Urlaubszähler", die IDs lauten also **`urlaubszahler_*`** (ohne „e"):
`binary_sensor.urlaubszahler_papa`,
`sensor.urlaubszahler_urlaub_<wer>_<ziel>`. Beim Schreiben von Doku oder Tests
ist das die häufigste Fehlerquelle. `suggested_object_id` zu setzen führt zu
doppelten Präfixen – bereits versucht und wieder verworfen.

### Blueprint (`urlaub_anlegen.yaml`)

Trigger: `automation_reloaded` und `homeassistant_started` (beide id `anlegen`)
sowie die tägliche Erinnerungszeit (id `erinnern`). Zwei Eigenheiten von Home
Assistant bestimmen den Aufbau:

* `automation_reloaded` feuert, **bevor** die Trigger einer gerade gespeicherten
  Automatisierung angehängt sind – die Automatisierung verpasst ihr eigenes
  Ereignis. Deshalb ruft der Kartendialog nach dem Speichern zusätzlich
  `automation.trigger` mit `skip_condition: true` auf (`_sofortAusfuehren`
  pollt bis zu 12 × 400 ms auf die neue Entität).
* Der `homeassistant: start`-Trigger lauscht auf kein Ereignis und feuert nur,
  wenn er beim Start bereits hing → stattdessen `event_type: homeassistant_started`.

Die Aktion legt den Urlaub bei **jedem** Lauf neu an bzw. frischt ihn auf
(gleiche `urlaub_id` = Update). Push-Benachrichtigungen bei 60/40/20/10/5/1 Tagen
gehen an die im Blueprint gewählten `notify.mobile_app_*`-Dienste und zählen
ganze Kalendertage.

## Versionen synchron halten

Bei einem Release müssen übereinstimmen:
`custom_components/urlaubszaehler/manifest.json` → `version`,
`KARTEN_VERSION` in `tools/urlaubszaehler-card.src.js` (und damit in der
generierten Karte) sowie der Git-Tag.

## Tests

`tests/conftest.py` stellt die Fixtures `eintrag` und `eingerichtet` bereit und
mockt Geocoding autouse (`_kein_echtes_geocoding`) – Tests gehen nie ins Netz.
`pytest-homeassistant-custom-component` teilt sich ein Konfigurationsverzeichnis
zwischen Tests, deshalb räumt `_sauberes_konfigverzeichnis` den Blueprint-Ordner
vor und nach jedem Test weg; ohne das beeinflussen sich die Blueprint-Tests
gegenseitig.

`tests/test_blueprint.py` lädt den Blueprint tatsächlich, macht daraus eine
echte Automatisierung und prüft jede der sechs Vorlaufzeiten. Wer den Blueprint
ändert, ändert damit auch diese Tests.

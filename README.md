# 🏖️ Urlaubszähler

Zähle die Tage bis zum Urlaub – eine Home-Assistant-Integration, die für jeden
geplanten Urlaub einen eigenen Countdown-Sensor erzeugt, inklusive Blueprint zum
Anlegen neuer Urlaube und für Push-Benachrichtigungen zu festen Vorlaufzeiten.

* Einrichtung komplett über die UI (Config Flow) – **keine Helfer von Hand anlegen**.
  `input_datetime`, `input_text` & Co. sind nicht nötig; die Integration verwaltet
  alle Daten intern in ihrem eigenen Speicher (`.storage/urlaubszaehler.<entry_id>`).
* Beliebig viele Urlaube parallel.
* Countdown stoppt bei `0 Tage, 0 Stunden, 0 Minuten` – es wird nicht negativ
  weitergerechnet.
* Der Sensor wird **exakt 24 Stunden nach dem Reisezeitpunkt** automatisch und
  restlos entfernt (auch aus der Entitäten-Registry).

Mindestversion: **Home Assistant 2024.11**

---

## 1. Wohin gehören die Dateien?

Alles relativ zu deinem Home-Assistant-Konfigurationsverzeichnis (dort, wo auch
die `configuration.yaml` liegt):

```
config/
├── custom_components/
│   └── urlaubszaehler/          ← kompletter Ordner aus diesem Repo
│       ├── __init__.py
│       ├── manifest.json
│       ├── const.py
│       ├── models.py
│       ├── manager.py
│       ├── config_flow.py
│       ├── sensor.py
│       ├── binary_sensor.py
│       ├── services.yaml
│       ├── strings.json
│       └── translations/
│           ├── de.json
│           └── en.json
└── blueprints/
    └── automation/
        └── urlaubszaehler/
            └── urlaub_anlegen.yaml
```

Die Datei `lovelace/urlaubszaehler_karte.yaml` wird **nicht** kopiert – daraus
fügst du dir nur die gewünschte Karte ins Dashboard ein.

### Installation über HACS (alternativ)

HACS → Integrationen → ⋮ → *Benutzerdefinierte Repositories* → dieses Repository
als Kategorie *Integration* hinzufügen → installieren.

---

## 2. Aktivieren nach dem Neustart

1. Home Assistant **neu starten** (Entwicklerwerkzeuge → Neu starten).
2. **Einstellungen → Geräte & Dienste → Integration hinzufügen** → nach
   `Urlaubszähler` suchen.
3. **Schritt 1:** Anzahl der Personen und Anzahl der Familien eintragen.
4. **Schritt 2:** Namen der Personen eintragen (z. B. `Papa`, `Fiene`).
5. **Schritt 3:** Familiennamen eintragen und optional festlegen, welche
   Personen zu einer Familie gehören.

Danach existiert je Person und Familie eine Entität, z. B.
`binary_sensor.urlaubszaehler_papa` – diese Namen tauchen im Blueprint zur
Auswahl auf.

> Namen später ändern: **Einstellungen → Geräte & Dienste → Urlaubszähler →
> Konfigurieren**. Dort lassen sich auch geplante Urlaube vorzeitig löschen.

### Blueprint aktivieren

Nach dem Neustart: **Einstellungen → Automatisierungen & Szenen → Blueprints**.
Taucht *„Urlaubszähler – Urlaub anlegen & erinnern"* nicht sofort auf, einmal
über **Entwicklerwerkzeuge → YAML → Blueprints neu laden** aktualisieren.

---

## 3. Einen Urlaub anlegen

**Einstellungen → Automatisierungen → Automatisierung erstellen → Aus Blueprint**
→ *Urlaubszähler – Urlaub anlegen & erinnern*.

| Feld | Bedeutung |
|---|---|
| **Wer fährt in den Urlaub?** | Eine Person, mehrere Personen oder eine ganze Familie |
| **Wohin geht die Reise?** | Freitext, z. B. `Gardasee` |
| **Wann geht es los?** | Datum **und** genaue Uhrzeit |
| **Mobilgeräte** | Geräte mit der HA-App, die Push bekommen |
| **Vorlaufzeiten** | Standard: 60, 40, 20, 10, 5 und 1 Tag vorher |
| **Uhrzeit der Erinnerung** | Standard: 09:00 Uhr |

Beim **Speichern** der Automatisierung wird der Sensor sofort erzeugt. Für jeden
weiteren Urlaub legst du einfach eine weitere Automatisierung aus demselben
Blueprint an.

---

## 4. Der Sensor

Pro Urlaub entsteht eine Entität wie `sensor.urlaubszaehler_urlaub_papa_gardasee`.

**Status:** der Reisebeginn als **Unix-Zeit (Dezimal, Sekunden)**. Die Uhrzeit
wird in der in Home Assistant eingestellten Zeitzone (z. B. `Europe/Berlin`)
interpretiert, inklusive Sommer-/Winterzeit. Aus diesem einen Wert lassen sich
Tage, Stunden und Minuten jederzeit exakt ableiten – im Sensor selbst wie auch
in jeder Lovelace-Karte.

**Attribute:**

| Attribut | Beispiel |
|---|---|
| `nachricht` | `Der Urlaub von Papa und Fiene ist in 12 Tagen, 5 Stunden und 42 Minuten. Die Reise geht nach Gardasee.` |
| `wer` / `namen` | `Papa und Fiene` / `["Papa", "Fiene"]` |
| `ziel` | `Gardasee` |
| `start` / `start_zeitstempel` | `2026-08-14T07:30:00+02:00` / `1786764600.0` |
| `tage`, `stunden`, `minuten` | `12`, `5`, `42` (stoppen bei `0`) |
| `verbleibende_sekunden` | `1058520` |
| `gestartet` | `true`, sobald der Reisezeitpunkt erreicht ist |
| `wird_geloescht_am` | `2026-08-15T07:30:00+02:00` |
| `zeitzone` | `Europe/Berlin` |

Fertige Karten für das Dashboard: siehe
[`lovelace/urlaubszaehler_karte.yaml`](lovelace/urlaubszaehler_karte.yaml).

---

## 5. Services

| Service | Zweck |
|---|---|
| `urlaubszaehler.add_vacation` | Urlaub anlegen bzw. bei gleicher `urlaub_id` aktualisieren |
| `urlaubszaehler.remove_vacation` | Urlaub und Sensor sofort entfernen |
| `urlaubszaehler.list_vacations` | Alle Urlaube inkl. Restzeit zurückgeben |

```yaml
action: urlaubszaehler.add_vacation
data:
  teilnehmer:
    - binary_sensor.urlaubszaehler_papa
    - binary_sensor.urlaubszaehler_fiene
  ziel: Gardasee
  start: "2026-08-14 07:30:00"
  urlaub_id: sommerurlaub_2026
```

---

## 6. Gut zu wissen

* **Auto-Delete:** Ein Hintergrundtask prüft minütlich; der Sensor verschwindet
  in der Minute, in der `Reisezeitpunkt + 24 h` überschritten wird.
* Löschst du die Automatisierung, bleibt der Sensor bis zum Auto-Delete bestehen.
  Sofort entfernen: **Urlaubszähler → Konfigurieren → Geplante Urlaube entfernen**
  oder `urlaubszaehler.remove_vacation`.
* Push-Nachrichten nutzen `notify.mobile_app_<Gerätename>`. Erscheint kein
  Gerät zur Auswahl, ist die Home-Assistant-App auf dem Handy noch nicht
  eingerichtet.
* Die Benachrichtigungen zählen **ganze Kalendertage** – „60 Tage vorher"
  meldet sich also an dem Tag, der 60 Kalendertage vor dem Abreisedatum liegt.

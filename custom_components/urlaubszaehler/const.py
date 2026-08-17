"""Konstanten für die Urlaubszähler-Integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "urlaubszaehler"
PLATFORMS: Final = [Platform.BINARY_SENSOR, Platform.SENSOR]

STORAGE_VERSION: Final = 1

# Mitgelieferte Lovelace-Karte
CARD_DATEI: Final = "frontend/urlaubszaehler-card.js"
CARD_URL: Final = f"/{DOMAIN}/urlaubszaehler-card.js"
DATA_CARD_REGISTRIERT: Final = f"{DOMAIN}_card_url"

# Mitgelieferter Blueprint
BLUEPRINT_QUELLE: Final = "blueprints/automation/urlaubszaehler/urlaub_anlegen.yaml"
BLUEPRINT_ZIEL: Final = "blueprints/automation/urlaubszaehler/urlaub_anlegen.yaml"
STORE_BLUEPRINT_PRUEFSUMME: Final = "blueprint_pruefsumme"

# Config-Flow / Options
CONF_PERSON_COUNT: Final = "anzahl_personen"
CONF_FAMILY_COUNT: Final = "anzahl_familien"
CONF_PERSONEN: Final = "personen"
CONF_FAMILIEN: Final = "familien"
CONF_NAME: Final = "name"
CONF_MITGLIEDER: Final = "mitglieder"

# Teilnehmer-Arten
ART_PERSON: Final = "person"
ART_FAMILIE: Final = "familie"

# Unique-ID-Präfixe
UID_PARTICIPANT: Final = "teilnehmer"
UID_VACATION: Final = "urlaub"

# Dispatcher-Signale (pro Config-Entry)
SIGNAL_VACATION_ADDED: Final = f"{DOMAIN}_vacation_added_{{}}"
SIGNAL_VACATION_REMOVED: Final = f"{DOMAIN}_vacation_removed_{{}}"

# Services
SERVICE_ADD_VACATION: Final = "add_vacation"
SERVICE_REMOVE_VACATION: Final = "remove_vacation"
SERVICE_LIST_VACATIONS: Final = "list_vacations"

ATTR_TEILNEHMER: Final = "teilnehmer"
ATTR_ZIEL: Final = "ziel"
ATTR_START: Final = "start"
ATTR_URLAUB_ID: Final = "urlaub_id"
ATTR_ENTRY_ID: Final = "entry_id"
ATTR_KOORDINATEN: Final = "koordinaten"
ATTR_TRANSPORTMITTEL: Final = "transportmittel"

# Transportmittel für die Anreise. "unbekannt" ist bewusst der Standardwert:
# das Feld ist optional, bestehende Urlaube ohne Angabe bleiben gültig.
TRANSPORTMITTEL_STANDARD: Final = "unbekannt"
TRANSPORTMITTEL_OPTIONEN: Final = [
    "flugzeug",
    "auto",
    "bahn",
    "schiff",
    TRANSPORTMITTEL_STANDARD,
]

# Der Sensor verschwindet exakt 24 Stunden nach dem Reisezeitpunkt.
AUTO_DELETE_AFTER: Final = timedelta(hours=24)

# Aktualisierungsintervall der Countdown-Attribute.
UPDATE_INTERVAL: Final = timedelta(seconds=30)

# Intervall, in dem nach abgelaufenen Urlauben gesucht wird.
PURGE_INTERVAL: Final = timedelta(minutes=1)

# Abstand, in dem fehlende Zielkoordinaten erneut gesucht werden. War
# OpenStreetMap beim Anlegen kurz nicht erreichbar, holt das den Ort nach.
GEOCODE_RETRY_INTERVAL: Final = timedelta(minutes=30)

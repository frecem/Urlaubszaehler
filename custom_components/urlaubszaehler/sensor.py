"""Countdown-Sensoren für jeden geplanten Urlaub."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    SIGNAL_VACATION_ADDED,
    SIGNAL_VACATION_REMOVED,
    UID_VACATION,
    UPDATE_INTERVAL,
)
from .manager import UrlaubszaehlerManager
from .models import Vacation

SCAN_INTERVAL = UPDATE_INTERVAL


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Sensoren für bestehende Urlaube anlegen und auf neue reagieren."""
    manager: UrlaubszaehlerManager = hass.data[DOMAIN][entry.entry_id]
    bekannte: dict[str, UrlaubSensor] = {}

    @callback
    def _urlaub_hinzugefuegt(urlaub: Vacation) -> None:
        if (vorhanden := bekannte.get(urlaub.urlaub_id)) is not None:
            vorhanden.uebernehme(urlaub)
            return
        sensor = UrlaubSensor(manager, urlaub)
        bekannte[urlaub.urlaub_id] = sensor
        async_add_entities([sensor])

    @callback
    def _urlaub_entfernt(urlaub_id: str) -> None:
        sensor = bekannte.pop(urlaub_id, None)
        if sensor is None:
            return
        # Der Eintrag muss aus der Entitäten-Registry verschwinden, sonst
        # bliebe die Entität als "nicht verfügbar" zurück.
        registry = er.async_get(hass)
        entity_id = registry.async_get_entity_id(
            Platform.SENSOR, DOMAIN, sensor.unique_id
        )
        if entity_id:
            registry.async_remove(entity_id)
        else:
            hass.async_create_task(sensor.async_remove(force_remove=True))

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, SIGNAL_VACATION_ADDED.format(entry.entry_id), _urlaub_hinzugefuegt
        )
    )
    entry.async_on_unload(
        async_dispatcher_connect(
            hass, SIGNAL_VACATION_REMOVED.format(entry.entry_id), _urlaub_entfernt
        )
    )

    for urlaub in manager.vacations.values():
        _urlaub_hinzugefuegt(urlaub)


class UrlaubSensor(SensorEntity):
    """Ein Sensor pro Urlaub.

    Der Status ist der Reisebeginn als Unix-Zeit (Dezimal). Daraus lassen sich
    Tage, Stunden und Minuten jederzeit exakt ableiten - im Sensor selbst
    (Attribute) wie auch in einer Lovelace-Karte.
    """

    _attr_has_entity_name = True
    _attr_should_poll = True
    _attr_icon = "mdi:beach"

    def __init__(self, manager: UrlaubszaehlerManager, urlaub: Vacation) -> None:
        """Sensor aufbauen."""
        self._manager = manager
        self._urlaub = urlaub
        self._attr_unique_id = (
            f"{manager.entry.entry_id}_{UID_VACATION}_{urlaub.urlaub_id}"
        )
        self._attr_name = f"Urlaub {urlaub.wer} {urlaub.ziel}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, manager.entry.entry_id)},
            name="Urlaubszähler",
            manufacturer="Urlaubszähler",
            model="Urlaubs-Countdown",
            entry_type=None,
        )

    @callback
    def uebernehme(self, urlaub: Vacation) -> None:
        """Geänderte Urlaubsdaten übernehmen (gleiche Urlaub-ID)."""
        self._urlaub = urlaub
        self._attr_name = f"Urlaub {urlaub.wer} {urlaub.ziel}"
        if self.hass is not None:
            self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        """Reisebeginn als Unix-Zeitstempel (Sekunden, Dezimal)."""
        return round(self._urlaub.start_ts, 3)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Alle für Karten und Automationen nützlichen Werte."""
        jetzt = dt_util.utcnow()
        rest = self._urlaub.restzeit(jetzt)
        heimat_lat = self.hass.config.latitude
        heimat_lon = self.hass.config.longitude
        entfernung = self._urlaub.entfernung_km(heimat_lat, heimat_lon)
        return {
            "urlaub_id": self._urlaub.urlaub_id,
            "wer": self._urlaub.wer,
            "namen": self._urlaub.namen,
            "arten": self._urlaub.arten,
            "mitglieder": self._urlaub.mitglieder,
            "ziel": self._urlaub.ziel,
            "transportmittel": self._urlaub.transportmittel,
            # Grobe Schätzung, keine echte Routenberechnung - siehe distanz.py.
            "entfernung_km": round(entfernung) if entfernung is not None else None,
            "reisedauer_std": self._urlaub.reisedauer_stunden(heimat_lat, heimat_lon),
            "reisedauer_text": self._urlaub.reisedauer_text(heimat_lat, heimat_lon),
            # Erst kurz vor der Abreise befüllt - siehe ANKUNFTSZEIT_SCHWELLE.
            "ankunftszeit_text": self._urlaub.ankunftszeit_text(
                heimat_lat, heimat_lon, jetzt
            ),
            # Für die Weltkarte der Lovelace-Karte:
            "breitengrad": self._urlaub.breitengrad,
            "laengengrad": self._urlaub.laengengrad,
            "koordinaten_quelle": self._urlaub.koordinaten_quelle,
            "gefunden_als": self._urlaub.gefunden_als,
            "start": self._urlaub.start.isoformat(),
            "start_zeitstempel": self._urlaub.start_ts,
            "zeitzone": str(self._urlaub.start.tzinfo),
            "tage": rest.tage,
            "stunden": rest.stunden,
            "minuten": rest.minuten,
            "verbleibende_sekunden": rest.sekunden,
            "gestartet": rest.sekunden == 0,
            "wird_geloescht_am": self._urlaub.delete_at.isoformat(),
            "wird_geloescht_zeitstempel": self._urlaub.delete_ts,
            "nachricht": self._urlaub.nachricht(jetzt),
        }

    async def async_update(self) -> None:
        """Attribute regelmäßig neu berechnen (Countdown)."""
        # Die Werte werden in extra_state_attributes live berechnet; hier ist
        # nur sicherzustellen, dass der Sensor als aktuell gilt.
        self._attr_available = self._urlaub.urlaub_id in self._manager.vacations

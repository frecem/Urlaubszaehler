"""Je eine Entität pro Person und Familie.

Diese Entitäten dienen als auswählbare "Helfer" im Blueprint ("Wer fährt in
den Urlaub?") und zeigen an, ob für den Teilnehmer ein Urlaub geplant ist.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    ART_FAMILIE,
    CONF_MITGLIEDER,
    CONF_NAME,
    DOMAIN,
    UID_PARTICIPANT,
    UPDATE_INTERVAL,
)
from .manager import UrlaubszaehlerManager

SCAN_INTERVAL = UPDATE_INTERVAL


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Teilnehmer-Entitäten anlegen."""
    manager: UrlaubszaehlerManager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        TeilnehmerSensor(manager, teilnehmer) for teilnehmer in manager.participants
    )


class TeilnehmerSensor(BinarySensorEntity):
    """Zeigt an, ob für eine Person oder Familie ein Urlaub geplant ist."""

    _attr_has_entity_name = True
    _attr_should_poll = True

    def __init__(
        self, manager: UrlaubszaehlerManager, teilnehmer: dict[str, Any]
    ) -> None:
        """Teilnehmer-Entität aufbauen."""
        self._manager = manager
        self._teilnehmer = teilnehmer
        self._attr_name = teilnehmer[CONF_NAME]
        self._attr_unique_id = (
            f"{manager.entry.entry_id}_{UID_PARTICIPANT}_{teilnehmer['slug']}"
        )
        self._attr_icon = (
            "mdi:account-group"
            if teilnehmer["art"] == ART_FAMILIE
            else "mdi:account"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, manager.entry.entry_id)},
            name="Urlaubszähler",
            manufacturer="Urlaubszähler",
            model="Urlaubs-Countdown",
        )

    @property
    def is_on(self) -> bool:
        """True, wenn mindestens ein Urlaub geplant ist."""
        return bool(self._manager.vacations_for(self._teilnehmer[CONF_NAME]))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Name, Art und geplante Urlaube des Teilnehmers."""
        jetzt = dt_util.utcnow()
        urlaube = self._manager.vacations_for(self._teilnehmer[CONF_NAME])
        attribute: dict[str, Any] = {
            # 'anzeigename' wird vom Blueprint ausgelesen.
            "anzeigename": self._teilnehmer[CONF_NAME],
            "art": self._teilnehmer["art"],
            "mitglieder": self._teilnehmer[CONF_MITGLIEDER],
            "anzahl_urlaube": len(urlaube),
            "urlaube": [
                {
                    "urlaub_id": urlaub.urlaub_id,
                    "ziel": urlaub.ziel,
                    "start": urlaub.start.isoformat(),
                    "start_zeitstempel": urlaub.start_ts,
                    "tage": urlaub.restzeit(jetzt).tage,
                }
                for urlaub in urlaube
            ],
        }
        if urlaube:
            naechster = urlaube[0]
            rest = naechster.restzeit(jetzt)
            attribute.update(
                {
                    "naechstes_ziel": naechster.ziel,
                    "naechster_start": naechster.start.isoformat(),
                    "naechster_start_zeitstempel": naechster.start_ts,
                    "naechste_tage": rest.tage,
                    "naechste_stunden": rest.stunden,
                    "naechste_minuten": rest.minuten,
                    "nachricht": naechster.nachricht(jetzt),
                }
            )
        return attribute

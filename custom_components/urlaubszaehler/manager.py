"""Verwaltung der Teilnehmer und der geplanten Urlaube."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util, slugify

from .const import (
    ART_FAMILIE,
    ART_PERSON,
    CONF_FAMILIEN,
    CONF_MITGLIEDER,
    CONF_NAME,
    CONF_PERSONEN,
    DOMAIN,
    SIGNAL_VACATION_ADDED,
    SIGNAL_VACATION_REMOVED,
    STORAGE_VERSION,
)
from .models import Vacation

_LOGGER = logging.getLogger(__name__)


class UrlaubszaehlerManager:
    """Hält Teilnehmer (aus dem Config-Flow) und Urlaube (persistent gespeichert).

    Alle benötigten "Helfer" werden hier intern verwaltet - der Nutzer muss
    weder ``input_datetime`` noch ``input_text`` von Hand anlegen.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialisiere den Manager."""
        self.hass = hass
        self.entry = entry
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self.vacations: dict[str, Vacation] = {}

    # ------------------------------------------------------------------
    # Teilnehmer
    # ------------------------------------------------------------------
    @property
    def _config(self) -> dict[str, Any]:
        return {**self.entry.data, **self.entry.options}

    @property
    def participants(self) -> list[dict[str, Any]]:
        """Alle Personen und Familien als einheitliche Liste."""
        teilnehmer: list[dict[str, Any]] = []
        for name in self._config.get(CONF_PERSONEN, []):
            teilnehmer.append(
                {
                    "slug": slugify(name),
                    CONF_NAME: name,
                    "art": ART_PERSON,
                    CONF_MITGLIEDER: [],
                }
            )
        for familie in self._config.get(CONF_FAMILIEN, []):
            name = familie[CONF_NAME]
            teilnehmer.append(
                {
                    "slug": slugify(name),
                    CONF_NAME: name,
                    "art": ART_FAMILIE,
                    CONF_MITGLIEDER: list(familie.get(CONF_MITGLIEDER, [])),
                }
            )
        return teilnehmer

    def participant_by_slug(self, slug: str) -> dict[str, Any] | None:
        """Teilnehmer anhand des Slugs finden."""
        return next((t for t in self.participants if t["slug"] == slug), None)

    def participant_by_name(self, name: str) -> dict[str, Any] | None:
        """Teilnehmer anhand des Namens finden (Groß-/Kleinschreibung egal)."""
        gesucht = slugify(name)
        return next((t for t in self.participants if t["slug"] == gesucht), None)

    def vacations_for(self, name: str) -> list[Vacation]:
        """Alle Urlaube, an denen ein Teilnehmer beteiligt ist."""
        gesucht = slugify(name)
        treffer = [
            urlaub
            for urlaub in self.vacations.values()
            if gesucht in {slugify(n) for n in urlaub.namen}
            or gesucht in {slugify(m) for m in urlaub.mitglieder}
        ]
        return sorted(treffer, key=lambda urlaub: urlaub.start)

    # ------------------------------------------------------------------
    # Persistenz
    # ------------------------------------------------------------------
    async def async_load(self) -> None:
        """Gespeicherte Urlaube laden."""
        daten = await self._store.async_load()
        if not daten:
            return
        for eintrag in daten.get("vacations", []):
            try:
                urlaub = Vacation.from_dict(eintrag)
            except (KeyError, TypeError, ValueError):
                _LOGGER.warning("Ungültiger gespeicherter Urlaub: %s", eintrag)
                continue
            self.vacations[urlaub.urlaub_id] = urlaub

    async def async_save(self) -> None:
        """Urlaube speichern."""
        await self._store.async_save(
            {"vacations": [urlaub.as_dict() for urlaub in self.vacations.values()]}
        )

    async def async_remove_storage(self) -> None:
        """Speicher restlos entfernen (beim Löschen der Integration)."""
        await self._store.async_remove()

    # ------------------------------------------------------------------
    # Urlaube
    # ------------------------------------------------------------------
    def build_id(self, namen: list[str], ziel: str, start: datetime) -> str:
        """Erzeuge eine stabile ID, falls der Aufrufer keine mitgibt."""
        roh = f"{'_'.join(namen)}_{ziel}_{start.strftime('%Y%m%d%H%M')}"
        return slugify(roh) or f"urlaub_{int(start.timestamp())}"

    async def async_add_vacation(
        self,
        namen: list[str],
        ziel: str,
        start: datetime,
        urlaub_id: str | None = None,
        arten: list[str] | None = None,
        mitglieder: list[str] | None = None,
    ) -> Vacation:
        """Urlaub anlegen oder - bei gleicher ID - aktualisieren."""
        urlaub = Vacation(
            urlaub_id=urlaub_id or self.build_id(namen, ziel, start),
            namen=namen,
            ziel=ziel,
            start=start,
            arten=arten or [],
            mitglieder=mitglieder or [],
        )
        self.vacations[urlaub.urlaub_id] = urlaub
        await self.async_save()

        # Die Sensor-Plattform legt bei bekannter ID keinen zweiten Sensor an,
        # sondern übernimmt die neuen Daten in die bestehende Entität.
        async_dispatcher_send(
            self.hass, SIGNAL_VACATION_ADDED.format(self.entry.entry_id), urlaub
        )
        _LOGGER.debug("Urlaub angelegt/aktualisiert: %s", urlaub.as_dict())
        return urlaub

    async def async_remove_vacation(self, urlaub_id: str) -> bool:
        """Urlaub und zugehörigen Sensor restlos entfernen."""
        if urlaub_id not in self.vacations:
            return False
        del self.vacations[urlaub_id]
        await self.async_save()
        async_dispatcher_send(
            self.hass, SIGNAL_VACATION_REMOVED.format(self.entry.entry_id), urlaub_id
        )
        _LOGGER.debug("Urlaub entfernt: %s", urlaub_id)
        return True

    async def async_purge_expired(self, jetzt: datetime | None = None) -> None:
        """Alle Urlaube löschen, die länger als 24 Stunden zurückliegen."""
        jetzt = jetzt or dt_util.utcnow()
        abgelaufen = [
            urlaub_id
            for urlaub_id, urlaub in self.vacations.items()
            if urlaub.ist_abgelaufen(jetzt)
        ]
        for urlaub_id in abgelaufen:
            await self.async_remove_vacation(urlaub_id)

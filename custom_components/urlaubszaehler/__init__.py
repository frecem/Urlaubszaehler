"""Die Urlaubszähler-Integration für Home Assistant."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_ENTRY_ID,
    ATTR_START,
    ATTR_TEILNEHMER,
    ATTR_URLAUB_ID,
    ATTR_ZIEL,
    ATTR_KOORDINATEN,
    CONF_MITGLIEDER,
    CONF_NAME,
    DOMAIN,
    PLATFORMS,
    PURGE_INTERVAL,
    SERVICE_ADD_VACATION,
    SERVICE_LIST_VACATIONS,
    SERVICE_REMOVE_VACATION,
    UID_PARTICIPANT,
    UID_VACATION,
)
from .blueprints import async_blueprint_bereitstellen
from .card import async_karte_anmelden
from .manager import UrlaubszaehlerManager

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

ADD_VACATION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_TEILNEHMER): vol.All(cv.ensure_list, [cv.string]),
        vol.Required(ATTR_ZIEL): cv.string,
        vol.Required(ATTR_START): cv.datetime,
        vol.Optional(ATTR_URLAUB_ID): cv.string,
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        # Manuell gesetzte Zielkoordinaten (z. B. aus dem Karten-Feld des
        # Blueprints). Haben Vorrang vor der automatischen Suche.
        vol.Optional(ATTR_KOORDINATEN): vol.Schema(
            {
                vol.Required("latitude"): vol.Coerce(float),
                vol.Required("longitude"): vol.Coerce(float),
            },
            extra=vol.REMOVE_EXTRA,
        ),
    }
)

REMOVE_VACATION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_URLAUB_ID): cv.string,
        vol.Optional(ATTR_ENTRY_ID): cv.string,
    }
)

LIST_VACATIONS_SCHEMA = vol.Schema({vol.Optional(ATTR_ENTRY_ID): cv.string})


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Die Integration wird ausschließlich über die UI eingerichtet."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Einen Config-Entry einrichten."""
    manager = UrlaubszaehlerManager(hass, entry)
    await manager.async_load()
    await manager.async_purge_expired()

    # Karte und Blueprint kommen mit der Integration - der Nutzer muss nichts
    # von Hand kopieren oder eintragen.
    await async_karte_anmelden(hass)
    pruefsumme = await async_blueprint_bereitstellen(
        hass, manager.blueprint_pruefsumme
    )
    if pruefsumme != manager.blueprint_pruefsumme:
        manager.blueprint_pruefsumme = pruefsumme
        await manager.async_save()

    _cleanup_stale_entities(hass, entry, manager)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _aufraeumen(_now) -> None:
        """Abgelaufene Urlaube entfernen und fehlende Koordinaten nachtragen."""
        await manager.async_purge_expired()
        await manager.async_koordinaten_nachtragen()

    entry.async_on_unload(
        async_track_time_interval(hass, _aufraeumen, PURGE_INTERVAL)
    )
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Einen Config-Entry entladen."""
    entladen = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if entladen:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            for service in (
                SERVICE_ADD_VACATION,
                SERVICE_REMOVE_VACATION,
                SERVICE_LIST_VACATIONS,
            ):
                hass.services.async_remove(DOMAIN, service)
    return entladen


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Beim Löschen der Integration auch den internen Speicher entfernen."""
    await UrlaubszaehlerManager(hass, entry).async_remove_storage()


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Nach Änderungen in den Optionen neu laden."""
    await hass.config_entries.async_reload(entry.entry_id)


def _cleanup_stale_entities(
    hass: HomeAssistant, entry: ConfigEntry, manager: UrlaubszaehlerManager
) -> None:
    """Entitäten entfernen, deren Person/Familie/Urlaub es nicht mehr gibt."""
    registry = er.async_get(hass)
    gueltige_teilnehmer = {
        f"{entry.entry_id}_{UID_PARTICIPANT}_{t['slug']}" for t in manager.participants
    }
    gueltige_urlaube = {
        f"{entry.entry_id}_{UID_VACATION}_{urlaub_id}" for urlaub_id in manager.vacations
    }
    for eintrag in list(er.async_entries_for_config_entry(registry, entry.entry_id)):
        unique_id = eintrag.unique_id
        if f"_{UID_PARTICIPANT}_" in unique_id and unique_id not in gueltige_teilnehmer:
            registry.async_remove(eintrag.entity_id)
        elif f"_{UID_VACATION}_" in unique_id and unique_id not in gueltige_urlaube:
            registry.async_remove(eintrag.entity_id)


def _get_manager(hass: HomeAssistant, call: ServiceCall) -> UrlaubszaehlerManager:
    """Passenden Manager zum Service-Aufruf ermitteln."""
    managers: dict[str, UrlaubszaehlerManager] = hass.data.get(DOMAIN, {})
    if not managers:
        raise ServiceValidationError(
            "Die Integration 'Urlaubszähler' ist nicht eingerichtet."
        )
    entry_id = call.data.get(ATTR_ENTRY_ID)
    if entry_id:
        if entry_id not in managers:
            raise ServiceValidationError(
                f"Unbekannte entry_id '{entry_id}' für den Urlaubszähler."
            )
        return managers[entry_id]
    return next(iter(managers.values()))


def _resolve_teilnehmer(
    hass: HomeAssistant, manager: UrlaubszaehlerManager, eingaben: list[str]
) -> tuple[list[str], list[str], list[str]]:
    """Entity-IDs oder Klartextnamen zu Namen/Arten/Mitgliedern auflösen."""
    registry = er.async_get(hass)
    namen: list[str] = []
    arten: list[str] = []
    mitglieder: list[str] = []

    for eingabe in eingaben:
        teilnehmer = None
        if "." in eingabe:
            eintrag = registry.async_get(eingabe)
            praefix = f"{manager.entry.entry_id}_{UID_PARTICIPANT}_"
            if eintrag and eintrag.unique_id.startswith(praefix):
                teilnehmer = manager.participant_by_slug(
                    eintrag.unique_id[len(praefix) :]
                )
            if teilnehmer is None:
                zustand = hass.states.get(eingabe)
                anzeige = (
                    zustand.attributes.get("anzeigename")
                    or (zustand.name if zustand else None)
                    or eingabe
                )
                teilnehmer = manager.participant_by_name(anzeige)
                if teilnehmer is None:
                    namen.append(anzeige)
                    continue
        else:
            teilnehmer = manager.participant_by_name(eingabe)
            if teilnehmer is None:
                namen.append(eingabe)
                continue

        namen.append(teilnehmer[CONF_NAME])
        arten.append(teilnehmer["art"])
        mitglieder.extend(teilnehmer[CONF_MITGLIEDER])

    # Reihenfolge erhalten, Dubletten entfernen.
    namen = list(dict.fromkeys(namen))
    mitglieder = list(dict.fromkeys(m for m in mitglieder if m not in namen))
    return namen, arten, mitglieder


def _async_register_services(hass: HomeAssistant) -> None:
    """Die Services der Integration registrieren (nur einmal)."""
    if hass.services.has_service(DOMAIN, SERVICE_ADD_VACATION):
        return

    async def async_add_vacation(call: ServiceCall) -> ServiceResponse:
        manager = _get_manager(hass, call)
        namen, arten, mitglieder = _resolve_teilnehmer(
            hass, manager, call.data[ATTR_TEILNEHMER]
        )
        if not namen:
            raise ServiceValidationError(
                "Es wurde niemand ausgewählt, der in den Urlaub fährt."
            )
        koordinaten = call.data.get(ATTR_KOORDINATEN) or {}
        urlaub = await manager.async_add_vacation(
            namen=namen,
            ziel=call.data[ATTR_ZIEL],
            start=call.data[ATTR_START],
            urlaub_id=call.data.get(ATTR_URLAUB_ID),
            arten=arten,
            mitglieder=mitglieder,
            breitengrad=koordinaten.get("latitude"),
            laengengrad=koordinaten.get("longitude"),
        )
        return {
            ATTR_URLAUB_ID: urlaub.urlaub_id,
            "wer": urlaub.wer,
            "ziel": urlaub.ziel,
            "start": urlaub.start.isoformat(),
            "start_zeitstempel": urlaub.start_ts,
            "breitengrad": urlaub.breitengrad,
            "laengengrad": urlaub.laengengrad,
            "koordinaten_quelle": urlaub.koordinaten_quelle,
            "nachricht": urlaub.nachricht(),
        }

    async def async_remove_vacation(call: ServiceCall) -> ServiceResponse:
        manager = _get_manager(hass, call)
        urlaub_id = call.data[ATTR_URLAUB_ID]
        entfernt = await manager.async_remove_vacation(urlaub_id)
        return {ATTR_URLAUB_ID: urlaub_id, "entfernt": entfernt}

    async def async_list_vacations(call: ServiceCall) -> ServiceResponse:
        manager = _get_manager(hass, call)
        urlaube: list[dict[str, Any]] = []
        for urlaub in sorted(manager.vacations.values(), key=lambda u: u.start):
            rest = urlaub.restzeit()
            urlaube.append(
                {
                    ATTR_URLAUB_ID: urlaub.urlaub_id,
                    "wer": urlaub.wer,
                    "namen": urlaub.namen,
                    "ziel": urlaub.ziel,
                    "start": urlaub.start.isoformat(),
                    "start_zeitstempel": urlaub.start_ts,
                    "tage": rest.tage,
                    "stunden": rest.stunden,
                    "minuten": rest.minuten,
                    "nachricht": urlaub.nachricht(),
                }
            )
        return {"urlaube": urlaube, "anzahl": len(urlaube)}

    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_VACATION,
        async_add_vacation,
        schema=ADD_VACATION_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_VACATION,
        async_remove_vacation,
        schema=REMOVE_VACATION_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LIST_VACATIONS,
        async_list_vacations,
        schema=LIST_VACATIONS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )

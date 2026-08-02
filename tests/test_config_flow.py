"""Tests für die Einrichtung über die Benutzeroberfläche."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from homeassistant.data_entry_flow import FlowResultType

from custom_components.urlaubszaehler.const import (
    CONF_FAMILIEN,
    CONF_FAMILY_COUNT,
    CONF_MITGLIEDER,
    CONF_NAME,
    CONF_PERSON_COUNT,
    CONF_PERSONEN,
    DOMAIN,
)


async def test_kompletter_ablauf(hass):
    """Anzahl -> Personennamen -> Familiennamen -> Eintrag."""
    ergebnis = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert ergebnis["type"] is FlowResultType.FORM
    assert ergebnis["step_id"] == "user"

    ergebnis = await hass.config_entries.flow.async_configure(
        ergebnis["flow_id"], {CONF_PERSON_COUNT: 3, CONF_FAMILY_COUNT: 1}
    )
    assert ergebnis["step_id"] == "personen"
    assert list(ergebnis["data_schema"].schema) == ["Person 1", "Person 2", "Person 3"]

    ergebnis = await hass.config_entries.flow.async_configure(
        ergebnis["flow_id"],
        {"Person 1": "Papa", "Person 2": "Fiene", "Person 3": "Mama"},
    )
    assert ergebnis["step_id"] == "familien"

    ergebnis = await hass.config_entries.flow.async_configure(
        ergebnis["flow_id"],
        {
            "Familie 1": "Familie Frece",
            "Mitglieder von Familie 1": ["Papa", "Fiene"],
        },
    )
    assert ergebnis["type"] is FlowResultType.CREATE_ENTRY
    assert ergebnis["data"][CONF_PERSONEN] == ["Papa", "Fiene", "Mama"]
    assert ergebnis["data"][CONF_FAMILIEN] == [
        {CONF_NAME: "Familie Frece", CONF_MITGLIEDER: ["Papa", "Fiene"]}
    ]


async def test_ohne_familien(hass):
    """Bei 0 Familien wird der dritte Schritt übersprungen."""
    ergebnis = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    ergebnis = await hass.config_entries.flow.async_configure(
        ergebnis["flow_id"], {CONF_PERSON_COUNT: 1, CONF_FAMILY_COUNT: 0}
    )
    assert ergebnis["step_id"] == "personen"
    ergebnis = await hass.config_entries.flow.async_configure(
        ergebnis["flow_id"], {"Person 1": "Papa"}
    )
    assert ergebnis["type"] is FlowResultType.CREATE_ENTRY
    assert ergebnis["data"][CONF_FAMILIEN] == []


async def test_leere_namen_werden_abgefangen(hass):
    """Nur Leerzeichen als Name führt zu einer Fehlermeldung."""
    ergebnis = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    ergebnis = await hass.config_entries.flow.async_configure(
        ergebnis["flow_id"], {CONF_PERSON_COUNT: 2, CONF_FAMILY_COUNT: 0}
    )
    ergebnis = await hass.config_entries.flow.async_configure(
        ergebnis["flow_id"], {"Person 1": "   ", "Person 2": ""}
    )
    assert ergebnis["type"] is FlowResultType.FORM
    assert ergebnis["errors"] == {"base": "keine_namen"}


async def test_doppelte_namen_werden_zusammengefasst(hass):
    """Zweimal derselbe Name ergibt nur einen Teilnehmer."""
    ergebnis = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    ergebnis = await hass.config_entries.flow.async_configure(
        ergebnis["flow_id"], {CONF_PERSON_COUNT: 2, CONF_FAMILY_COUNT: 0}
    )
    ergebnis = await hass.config_entries.flow.async_configure(
        ergebnis["flow_id"], {"Person 1": "Papa", "Person 2": "Papa"}
    )
    assert ergebnis["data"][CONF_PERSONEN] == ["Papa"]


async def test_nur_eine_instanz(hass, eingerichtet):
    """Ein zweiter Eintrag wird abgelehnt."""
    ergebnis = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert ergebnis["type"] is FlowResultType.ABORT
    assert ergebnis["reason"] == "single_instance_allowed"


async def test_optionen_namen_aendern(hass, eingerichtet):
    """Über 'Konfigurieren' lassen sich Namen nachträglich ändern."""
    ergebnis = await hass.config_entries.options.async_init(eingerichtet.entry_id)
    assert ergebnis["type"] is FlowResultType.MENU

    ergebnis = await hass.config_entries.options.async_configure(
        ergebnis["flow_id"], {"next_step_id": "namen"}
    )
    ergebnis = await hass.config_entries.options.async_configure(
        ergebnis["flow_id"], {CONF_PERSON_COUNT: 2, CONF_FAMILY_COUNT: 0}
    )
    ergebnis = await hass.config_entries.options.async_configure(
        ergebnis["flow_id"], {"Person 1": "Papa", "Person 2": "Oma"}
    )
    assert ergebnis["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert hass.states.get("binary_sensor.urlaubszahler_oma") is not None
    # Fiene und die Familie sind restlos verschwunden.
    assert hass.states.get("binary_sensor.urlaubszahler_fiene") is None
    assert hass.states.get("binary_sensor.urlaubszahler_familie_frece") is None


async def test_optionen_ohne_urlaube(hass, eingerichtet):
    """Ohne geplante Urlaube gibt es nichts zu löschen."""
    ergebnis = await hass.config_entries.options.async_init(eingerichtet.entry_id)
    ergebnis = await hass.config_entries.options.async_configure(
        ergebnis["flow_id"], {"next_step_id": "urlaube"}
    )
    assert ergebnis["type"] is FlowResultType.ABORT
    assert ergebnis["reason"] == "keine_urlaube"


async def test_optionen_urlaub_loeschen(hass, eingerichtet, in_tagen):
    """Ein geplanter Urlaub lässt sich vorzeitig entfernen."""
    await hass.services.async_call(
        DOMAIN,
        "add_vacation",
        {"teilnehmer": ["Papa"], "ziel": "Gardasee", "start": in_tagen(12),
         "urlaub_id": "sommer"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.urlaubszahler_urlaub_papa_gardasee") is not None

    ergebnis = await hass.config_entries.options.async_init(eingerichtet.entry_id)
    ergebnis = await hass.config_entries.options.async_configure(
        ergebnis["flow_id"], {"next_step_id": "urlaube"}
    )
    assert ergebnis["type"] is FlowResultType.FORM
    ergebnis = await hass.config_entries.options.async_configure(
        ergebnis["flow_id"], {"loeschen": ["sommer"]}
    )
    assert ergebnis["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert hass.states.get("sensor.urlaubszahler_urlaub_papa_gardasee") is None

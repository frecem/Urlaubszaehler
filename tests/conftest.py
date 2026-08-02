"""Gemeinsame Vorbereitungen für die Tests."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.urlaubszaehler.const import (
    CONF_FAMILIEN,
    CONF_FAMILY_COUNT,
    CONF_MITGLIEDER,
    CONF_NAME,
    CONF_PERSON_COUNT,
    CONF_PERSONEN,
    DOMAIN,
)

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def _custom_integrations(enable_custom_integrations):
    """Custom Components in allen Tests laden."""
    yield


@pytest.fixture(autouse=True)
def _kein_echtes_geocoding(monkeypatch):
    """Nominatim niemals wirklich aufrufen."""
    orte = {
        "Gardasee": (45.65, 10.65),
        "Lappland": (67.90, 24.00),
        "Mallorca": (39.57, 2.65),
    }
    aufrufe: list[str] = []

    async def _attrappe(hass, ziel):
        aufrufe.append(ziel)
        if ziel not in orte:
            return None
        breite, laenge = orte[ziel]
        return {
            "breitengrad": breite,
            "laengengrad": laenge,
            "gefunden_als": f"{ziel}, Europa",
        }

    monkeypatch.setattr(
        "custom_components.urlaubszaehler.manager.async_geocode", _attrappe
    )
    return aufrufe


@pytest.fixture
def geocode_aufrufe(_kein_echtes_geocoding):
    """Liste der nachgeschlagenen Ortsnamen."""
    return _kein_echtes_geocoding


@pytest.fixture
def eintrag() -> MockConfigEntry:
    """Ein eingerichteter Urlaubszähler mit zwei Personen und einer Familie."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Urlaubszähler",
        data={
            CONF_PERSON_COUNT: 2,
            CONF_FAMILY_COUNT: 1,
            CONF_PERSONEN: ["Papa", "Fiene"],
            CONF_FAMILIEN: [
                {CONF_NAME: "Familie Frece", CONF_MITGLIEDER: ["Papa", "Fiene"]}
            ],
        },
    )


@pytest.fixture
async def eingerichtet(hass, eintrag) -> MockConfigEntry:
    """Der Eintrag ist geladen und die Plattformen sind aufgebaut."""
    eintrag.add_to_hass(hass)
    assert await hass.config_entries.async_setup(eintrag.entry_id)
    await hass.async_block_till_done()
    return eintrag


@pytest.fixture
def in_tagen():
    """Hilfsfunktion für einen Zeitpunkt in der Zukunft (lokale Zeit)."""

    def _bauen(tage: float = 10) -> str:
        ziel = datetime.now() + timedelta(days=tage)
        return ziel.strftime("%Y-%m-%d %H:%M:%S")

    return _bauen

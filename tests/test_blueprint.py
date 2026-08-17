"""End-to-End-Tests für den Blueprint.

Der Blueprint wird von Home Assistant selbst geladen, zu einer echten
Automatisierung gemacht und ausgelöst - damit sind Schema, Eingaben,
Templates und Serviceaufrufe geprüft.
"""

from __future__ import annotations

import pathlib
import shutil
from datetime import datetime, timedelta

import pytest
from homeassistant.components import automation
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.urlaubszaehler.const import DOMAIN

BLUEPRINT_PFAD = "urlaubszaehler/urlaub_anlegen.yaml"
QUELLE = (
    pathlib.Path(__file__).parent.parent
    / "custom_components"
    / "urlaubszaehler"
    / "blueprints"
    / "automation"
    / "urlaubszaehler"
    / "urlaub_anlegen.yaml"
)

PAPA = "binary_sensor.urlaubszahler_papa"
FIENE = "binary_sensor.urlaubszahler_mama"


@pytest.fixture
def blueprint_installiert(hass: HomeAssistant):
    """Den Blueprint in das Konfigurationsverzeichnis der Testinstanz legen."""
    ziel = pathlib.Path(hass.config.config_dir) / "blueprints" / "automation"
    ziel.mkdir(parents=True, exist_ok=True)
    (ziel / "urlaubszaehler").mkdir(exist_ok=True)
    shutil.copy(QUELLE, ziel / BLUEPRINT_PFAD)
    return ziel


@pytest.fixture
def handy(hass: HomeAssistant) -> str:
    """Ein Gerät mit der Home-Assistant-App vortäuschen."""
    eintrag = MockConfigEntry(domain="mobile_app", title="Mobile App")
    eintrag.add_to_hass(hass)
    geraet = dr.async_get(hass).async_get_or_create(
        config_entry_id=eintrag.entry_id,
        identifiers={("mobile_app", "test-handy")},
        name="Papas Handy",
    )
    return geraet.id


async def automatisierung_bauen(hass, eingaben: dict) -> None:
    """Eine Automatisierung aus dem Blueprint einrichten."""
    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: {
                "id": "urlaub_gardasee",
                "use_blueprint": {"path": BLUEPRINT_PFAD, "input": eingaben},
            }
        },
    )
    await hass.async_block_till_done()


def in_tagen(tage: int, uhrzeit: str = "07:30:00") -> str:
    """Datum in N Kalendertagen als Selector-Format."""
    return f"{(dt_util.now() + timedelta(days=tage)).strftime('%Y-%m-%d')} {uhrzeit}"


# ---------------------------------------------------------------------------


async def test_blueprint_ist_gueltig(hass, blueprint_installiert):
    """Home Assistant akzeptiert das Blueprint-Schema."""
    from homeassistant.components.blueprint import models

    assert await async_setup_component(hass, automation.DOMAIN, {})
    domain_blueprints = hass.data["blueprint"][automation.DOMAIN]
    blueprint = await domain_blueprints.async_get_blueprint(BLUEPRINT_PFAD)

    assert isinstance(blueprint, models.Blueprint)
    assert blueprint.name == "Urlaubszähler – Urlaub anlegen & erinnern"
    # Alle im Blueprint erwarteten Eingaben sind vorhanden.
    assert set(blueprint.inputs) >= {
        "teilnehmer",
        "ziel",
        "start",
        "ziel_manuell",
        "ziel_koordinaten",
        "mobilgeraete",
        "vorlaufzeiten",
        "erinnerungszeit",
        "zusaetzliche_aktion",
    }


async def test_urlaub_wird_beim_speichern_angelegt(
    hass, eingerichtet, blueprint_installiert, handy
):
    """Nach dem Anlegen der Automatisierung existiert der Sensor."""
    await automatisierung_bauen(
        hass,
        {
            "teilnehmer": [PAPA, FIENE],
            "ziel": "Gardasee",
            "start": in_tagen(60),
            "mobilgeraete": [handy],
        },
    )

    # Das Speichern einer Automatisierung löst 'automation_reloaded' aus.
    hass.bus.async_fire("automation_reloaded")
    await hass.async_block_till_done()

    zustand = hass.states.get("sensor.urlaubszahler_urlaub_papa_und_mama_gardasee")
    assert zustand is not None
    assert zustand.attributes["wer"] == "Papa und Mama"
    assert zustand.attributes["ziel"] == "Gardasee"
    assert zustand.attributes["breitengrad"] == 45.65
    # 60 Kalendertage; je nach Tageszeit sind das 59 oder 60 volle Tage.
    assert zustand.attributes["tage"] in (59, 60)
    # Kein Transportmittel angegeben -> Blueprint-Standard "unbekannt".
    assert zustand.attributes["transportmittel"] == "unbekannt"


async def test_transportmittel_aus_dem_blueprint(
    hass, eingerichtet, blueprint_installiert, handy
):
    """Ein gewähltes Transportmittel landet im Sensor-Attribut."""
    await automatisierung_bauen(
        hass,
        {
            "teilnehmer": [PAPA],
            "ziel": "Gardasee",
            "start": in_tagen(60),
            "transportmittel": "auto",
            "mobilgeraete": [handy],
        },
    )
    hass.bus.async_fire("automation_reloaded")
    await hass.async_block_till_done()

    zustand = hass.states.get("sensor.urlaubszahler_urlaub_papa_gardasee")
    assert zustand.attributes["transportmittel"] == "auto"


async def test_urlaub_wird_nach_neustart_wiederhergestellt(
    hass, eingerichtet, blueprint_installiert, handy
):
    """Der Sensor entsteht auch nach einem Neustart von Home Assistant."""
    await automatisierung_bauen(
        hass,
        {
            "teilnehmer": [PAPA],
            "ziel": "Mallorca",
            "start": in_tagen(20),
            "mobilgeraete": [handy],
        },
    )
    # 'homeassistant_started' feuert erst, wenn alle Integrationen geladen sind.
    hass.bus.async_fire("homeassistant_started")
    await hass.async_block_till_done()

    assert hass.states.get("sensor.urlaubszahler_urlaub_papa_mallorca") is not None


async def test_manuelle_koordinaten_aus_dem_blueprint(
    hass, eingerichtet, blueprint_installiert, handy, geocode_aufrufe
):
    """Mit eingeschalteter Option wird der Kartenpunkt verwendet."""
    await automatisierung_bauen(
        hass,
        {
            "teilnehmer": [PAPA],
            "ziel": "Gardasee",
            "start": in_tagen(30),
            "ziel_manuell": True,
            "ziel_koordinaten": {"latitude": 45.1, "longitude": 10.9, "radius": 50},
            "mobilgeraete": [handy],
        },
    )
    hass.bus.async_fire("automation_reloaded")
    await hass.async_block_till_done()

    zustand = hass.states.get("sensor.urlaubszahler_urlaub_papa_gardasee")
    assert zustand.attributes["breitengrad"] == 45.1
    assert zustand.attributes["koordinaten_quelle"] == "manuell"
    assert geocode_aufrufe == []


async def test_vergangene_reise_wird_nicht_angelegt(
    hass, eingerichtet, blueprint_installiert, handy
):
    """Liegt die Abreise in der Vergangenheit, entsteht kein Sensor."""
    await automatisierung_bauen(
        hass,
        {
            "teilnehmer": [PAPA],
            "ziel": "Gardasee",
            "start": in_tagen(-5),
            "mobilgeraete": [handy],
        },
    )
    hass.bus.async_fire("automation_reloaded")
    await hass.async_block_till_done()

    assert hass.states.get("sensor.urlaubszahler_urlaub_papa_gardasee") is None


# ---------------------------------------------------------------------------
# Benachrichtigungen
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tage_vorher", "erwartet"),
    [
        (60, True),
        (40, True),
        (20, True),
        (10, True),
        (5, True),
        (1, True),
        (59, False),
        (41, False),
        (11, False),
        (2, False),
        (0, False),
    ],
)
async def test_push_zu_den_vorlaufzeiten(
    hass, eingerichtet, blueprint_installiert, handy, freezer, tage_vorher, erwartet
):
    """Genau an den sechs Vorlaufzeiten wird benachrichtigt, sonst nicht."""
    # Kurz vor der Erinnerungszeit starten.
    jetzt = dt_util.now().replace(hour=8, minute=59, second=0, microsecond=0)
    freezer.move_to(jetzt)

    benachrichtigungen = async_mock_service(hass, "notify", "mobile_app_papas_handy")

    await automatisierung_bauen(
        hass,
        {
            "teilnehmer": [PAPA],
            "ziel": "Gardasee",
            "start": in_tagen(tage_vorher, "18:00:00"),
            "mobilgeraete": [handy],
            "erinnerungszeit": "09:00:00",
        },
    )

    freezer.move_to(jetzt + timedelta(minutes=1))
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
    await hass.async_block_till_done()

    assert bool(benachrichtigungen) is erwartet
    if erwartet:
        nachricht = benachrichtigungen[0].data["message"]
        assert f"in {tage_vorher} " in nachricht
        assert "Papa" in nachricht
        assert "Gardasee" in nachricht


async def test_push_an_mehrere_geraete(
    hass, eingerichtet, blueprint_installiert, freezer
):
    """Alle ausgewählten Mobilgeräte werden benachrichtigt."""
    eintrag = MockConfigEntry(domain="mobile_app", title="Mobile App")
    eintrag.add_to_hass(hass)
    registry = dr.async_get(hass)
    geraete = [
        registry.async_get_or_create(
            config_entry_id=eintrag.entry_id,
            identifiers={("mobile_app", name)},
            name=name,
        ).id
        for name in ("Handy Papa", "Handy Mama")
    ]
    rufe_a = async_mock_service(hass, "notify", "mobile_app_handy_papa")
    rufe_b = async_mock_service(hass, "notify", "mobile_app_handy_mama")

    jetzt = dt_util.now().replace(hour=8, minute=59, second=0, microsecond=0)
    freezer.move_to(jetzt)

    await automatisierung_bauen(
        hass,
        {
            "teilnehmer": [PAPA],
            "ziel": "Gardasee",
            "start": in_tagen(10, "18:00:00"),
            "mobilgeraete": geraete,
            "erinnerungszeit": "09:00:00",
        },
    )

    freezer.move_to(jetzt + timedelta(minutes=1))
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
    await hass.async_block_till_done()

    assert len(rufe_a) == 1
    assert len(rufe_b) == 1


async def test_eigene_vorlaufzeiten(
    hass, eingerichtet, blueprint_installiert, handy, freezer
):
    """Abgewählte Vorlaufzeiten lösen keine Benachrichtigung aus."""
    jetzt = dt_util.now().replace(hour=8, minute=59, second=0, microsecond=0)
    freezer.move_to(jetzt)
    benachrichtigungen = async_mock_service(hass, "notify", "mobile_app_papas_handy")

    await automatisierung_bauen(
        hass,
        {
            "teilnehmer": [PAPA],
            "ziel": "Gardasee",
            "start": in_tagen(60, "18:00:00"),
            "mobilgeraete": [handy],
            "erinnerungszeit": "09:00:00",
            "vorlaufzeiten": ["10", "1"],
        },
    )

    freezer.move_to(jetzt + timedelta(minutes=1))
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
    await hass.async_block_till_done()

    assert benachrichtigungen == []


async def test_manueller_start_legt_urlaub_an(
    hass, eingerichtet, blueprint_installiert, handy
):
    """Ein manuelles "Ausführen" legt den Urlaub an.

    Diesen Weg nutzt die Lovelace-Karte: Home Assistant feuert
    'automation_reloaded', bevor die Trigger einer frisch gespeicherten
    Automatisierung hängen - sie verpasst also ihr eigenes Ereignis.
    """
    await automatisierung_bauen(
        hass,
        {
            "teilnehmer": [PAPA],
            "ziel": "Gardasee",
            "start": in_tagen(25),
            "mobilgeraete": [handy],
        },
    )
    # Bewusst KEIN 'automation_reloaded'.
    assert hass.states.get("sensor.urlaubszahler_urlaub_papa_gardasee") is None

    automatisierungen = [z.entity_id for z in hass.states.async_all("automation")]
    assert automatisierungen, "keine Automatisierung angelegt"
    await hass.services.async_call(
        "automation",
        "trigger",
        {"entity_id": automatisierungen[0], "skip_condition": True},
        blocking=True,
    )
    await hass.async_block_till_done()

    zustand = hass.states.get("sensor.urlaubszahler_urlaub_papa_gardasee")
    assert zustand is not None
    assert zustand.attributes["ziel"] == "Gardasee"


async def test_erinnerung_frischt_urlaub_auf(
    hass, eingerichtet, blueprint_installiert, handy, freezer
):
    """Auch der tägliche Lauf hält den Sensor am Leben (Selbstheilung)."""
    jetzt = dt_util.now().replace(hour=8, minute=59, second=0, microsecond=0)
    freezer.move_to(jetzt)

    await automatisierung_bauen(
        hass,
        {
            "teilnehmer": [PAPA],
            "ziel": "Gardasee",
            "start": in_tagen(33, "18:00:00"),
            "mobilgeraete": [handy],
            "erinnerungszeit": "09:00:00",
        },
    )

    freezer.move_to(jetzt + timedelta(minutes=1))
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
    await hass.async_block_till_done()

    # 33 Tage ist keine Vorlaufzeit - der Sensor entsteht trotzdem.
    assert hass.states.get("sensor.urlaubszahler_urlaub_papa_gardasee") is not None

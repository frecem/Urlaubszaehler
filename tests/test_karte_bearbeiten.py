"""End-to-End-Test für das Bearbeiten aus der Karte gegen die echte
Automatisierungs-Editor-API von Home Assistant.

Die Karte selbst (JavaScript) wurde bereits gegen ein gemocktes ``hass``
geprüft. Hier geht es um die Backend-Seite, auf die sich die Karte
verlässt: dass ``POST /api/config/automation/config/{id}`` beim erneuten
Aufruf mit derselben (internen) Config-ID den bestehenden Eintrag
aktualisiert statt einen zweiten anzulegen, dass die entity_id über eine
Bearbeitung hinweg stabil bleibt, und dass sich diese Config-ID zuverlässig
über das Attribut ``id`` der Automatisierung wiederfinden lässt - genau der
Weg, den ``_bearbeitenLaden``/``_sofortAusfuehren`` in der Karte gehen.

Wichtig: die interne Config-ID (im Aufruf ``String(Date.now())`` in der
Karte) und ``urlaub_id`` sind zwei verschiedene Dinge. ``urlaub_id`` leitet
der Blueprint aus der eigenen entity_id ab
(``this.entity_id | replace('automation.', '')``), und die entity_id wird
von Home Assistant beim Erstellen aus dem *Alias* abgeleitet - nicht aus der
Config-ID. Deshalb sucht dieser Test die Automatisierung wie die Karte über
``attributes.id`` statt eine entity_id zu erraten.
"""

from __future__ import annotations

import pathlib
import shutil

import pytest
from homeassistant.components import automation
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

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


@pytest.fixture
def blueprint_installiert(hass: HomeAssistant):
    """Den Blueprint in das Konfigurationsverzeichnis der Testinstanz legen."""
    ziel = pathlib.Path(hass.config.config_dir) / "blueprints" / "automation"
    ziel.mkdir(parents=True, exist_ok=True)
    (ziel / "urlaubszaehler").mkdir(exist_ok=True)
    shutil.copy(QUELLE, ziel / BLUEPRINT_PFAD)
    return ziel


@pytest.fixture
def echte_configuration_yaml(hass: HomeAssistant):
    """Der 'automation.reload'-Dienst liest configuration.yaml von der
    Platte - im Testverzeichnis gibt es normalerweise keine. Da dieses
    Verzeichnis zwischen Tests geteilt wird, danach wieder aufräumen."""
    pfad = pathlib.Path(hass.config.config_dir) / "configuration.yaml"
    vorher = pfad.read_text() if pfad.exists() else None
    pfad.write_text("automation: !include automations.yaml\n")

    automations_datei = pfad.parent / "automations.yaml"
    automations_vorher = (
        automations_datei.read_text() if automations_datei.exists() else None
    )
    automations_datei.write_text("[]\n")

    yield

    if vorher is None:
        pfad.unlink(missing_ok=True)
    else:
        pfad.write_text(vorher)
    if automations_vorher is None:
        automations_datei.unlink(missing_ok=True)
    else:
        automations_datei.write_text(automations_vorher)


@pytest.fixture
async def config_api(hass: HomeAssistant, echte_configuration_yaml):
    """Dieselben Komponenten wie im echten Automatisierungs-Editor."""
    assert await async_setup_component(hass, automation.DOMAIN, {automation.DOMAIN: []})
    assert await async_setup_component(hass, "config", {})
    await hass.async_block_till_done()


async def _anlegen_oder_speichern(
    client, automatisierungs_id: str, ziel_name: str, input_daten: dict
) -> None:
    """Genau der Aufruf, den auch die Karte macht (_speichern in der Karte)."""
    antwort = await client.post(
        f"/api/config/automation/config/{automatisierungs_id}",
        json={
            "alias": f"Urlaub Test – {ziel_name}",
            "description": "Angelegt über die Urlaubszähler-Karte",
            "use_blueprint": {"path": BLUEPRINT_PFAD, "input": input_daten},
        },
    )
    assert antwort.status == 200, await antwort.text()


def _automation_ueber_config_id(hass: HomeAssistant, automatisierungs_id: str):
    """Wie _sofortAusfuehren()/_bearbeitenLaden() in der Karte: die
    Automatisierung über ihre interne Config-ID finden, nicht über eine
    angenommene entity_id (die hängt vom Alias ab)."""
    return next(
        (
            zustand
            for zustand in hass.states.async_all("automation")
            if zustand.attributes.get("id") == automatisierungs_id
        ),
        None,
    )


async def _sofort_ausloesen(hass: HomeAssistant, entity_id: str) -> None:
    """Wie _sofortAusfuehren() in der Karte: automation_reloaded kommt zu
    früh für die frisch angelegte/aktualisierte Automatisierung."""
    await hass.services.async_call(
        automation.DOMAIN,
        "trigger",
        {"entity_id": entity_id, "skip_condition": True},
        blocking=True,
    )
    await hass.async_block_till_done()


async def test_anlegen_und_bearbeiten_ueber_die_echte_api(
    hass, eingerichtet, blueprint_installiert, config_api, hass_client, in_tagen
):
    """Reproduziert exakt den Ablauf der Karte: Anlegen, dann Bearbeiten mit
    derselben Config-ID - über die echte HTTP-Config-API, nicht gemockt."""
    client = await hass_client()
    automatisierungs_id = "1700000000000"  # so wie String(Date.now()) in der Karte

    # 1) Anlegen - wie beim ersten Speichern im Karten-Dialog.
    await _anlegen_oder_speichern(
        client,
        automatisierungs_id,
        "Gardasee",
        {
            "teilnehmer": [PAPA],
            "ziel": "Gardasee",
            "start": in_tagen(30),
            "transportmittel": "auto",
            "mobilgeraete": [],
        },
    )
    await hass.async_block_till_done()

    zustand = _automation_ueber_config_id(hass, automatisierungs_id)
    assert zustand is not None, "Automatisierung wurde nicht angelegt"
    entity_id = zustand.entity_id
    urlaub_id = entity_id.removeprefix("automation.")

    await _sofort_ausloesen(hass, entity_id)

    sensor = next(
        (
            z
            for z in hass.states.async_all("sensor")
            if z.attributes.get("urlaub_id") == urlaub_id
        ),
        None,
    )
    assert sensor is not None, "Sensor wurde nicht angelegt"
    assert sensor.attributes["transportmittel"] == "auto"
    assert sensor.attributes["ziel"] == "Gardasee"
    urspruenglicher_sensor_entity_id = sensor.entity_id

    # 2) Bearbeiten: GET wie _bearbeitenLaden(), dann POST mit derselben
    # Config-ID, aber geänderten Werten - wie beim Speichern im
    # Bearbeiten-Modus.
    geladene_config = await client.get(
        f"/api/config/automation/config/{automatisierungs_id}"
    )
    assert geladene_config.status == 200
    geladene_config = await geladene_config.json()
    assert geladene_config["use_blueprint"]["input"]["ziel"] == "Gardasee"
    assert geladene_config["use_blueprint"]["input"]["transportmittel"] == "auto"

    await _anlegen_oder_speichern(
        client,
        automatisierungs_id,
        "Gardasee",
        {
            "teilnehmer": [PAPA],
            "ziel": "Gardasee",
            "start": in_tagen(30),
            "transportmittel": "bahn",
            "mobilgeraete": [],
        },
    )
    await hass.async_block_till_done()

    # Dieselbe Automatisierung (gleiche entity_id), keine zweite entstanden.
    automatisierungen = hass.states.async_entity_ids("automation")
    assert automatisierungen == [entity_id]

    await _sofort_ausloesen(hass, entity_id)

    # Derselbe Sensor (gleiche entity_id) zeigt jetzt die aktualisierten
    # Werte - kein zweiter, verwaister Sensor.
    alle_urlaubs_sensoren = [
        z for z in hass.states.async_all("sensor") if z.attributes.get("urlaub_id")
    ]
    assert len(alle_urlaubs_sensoren) == 1
    sensor = hass.states.get(urspruenglicher_sensor_entity_id)
    assert sensor is not None
    assert sensor.attributes["urlaub_id"] == urlaub_id
    assert sensor.attributes["transportmittel"] == "bahn"

    # Es existiert insgesamt weiterhin nur ein Urlaub, nicht zwei.
    manager = list(hass.data["urlaubszaehler"].values())[0]
    assert len(manager.vacations) == 1

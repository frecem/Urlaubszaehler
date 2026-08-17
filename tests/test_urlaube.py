"""Tests für Services, Sensoren, Countdown und Auto-Delete."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import voluptuous as vol
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.urlaubszaehler.const import DOMAIN

PAPA = "binary_sensor.urlaubszahler_papa"
FIENE = "binary_sensor.urlaubszahler_mama"
FAMILIE = "binary_sensor.urlaubszahler_familie_muster"


async def anlegen(hass, teilnehmer, ziel, tage=12, **extra):
    """Hilfsfunktion: Urlaub über den Service anlegen."""
    start = dt_util.now() + timedelta(days=tage)
    daten = {
        "teilnehmer": teilnehmer,
        "ziel": ziel,
        "start": start.replace(tzinfo=None),
        **extra,
    }
    antwort = await hass.services.async_call(
        DOMAIN, "add_vacation", daten, blocking=True, return_response=True
    )
    await hass.async_block_till_done()
    return antwort


# ---------------------------------------------------------------------------
# Einrichtung
# ---------------------------------------------------------------------------


async def test_teilnehmer_entitaeten(hass, eingerichtet):
    """Für jede Person und Familie entsteht eine Entität."""
    for entity_id in (PAPA, FIENE, FAMILIE):
        zustand = hass.states.get(entity_id)
        assert zustand is not None, entity_id
        assert zustand.state == "off"

    assert hass.states.get(PAPA).attributes["anzeigename"] == "Papa"
    assert hass.states.get(PAPA).attributes["art"] == "person"
    assert hass.states.get(FAMILIE).attributes["art"] == "familie"
    assert hass.states.get(FAMILIE).attributes["mitglieder"] == ["Papa", "Mama"]


async def test_alle_services_vorhanden(hass, eingerichtet):
    """Die drei Services sind registriert."""
    for service in ("add_vacation", "remove_vacation", "list_vacations"):
        assert hass.services.has_service(DOMAIN, service), service


async def test_ein_geraet(hass, eingerichtet):
    """Alle Entitäten hängen an einem gemeinsamen Gerät."""
    registry = er.async_get(hass)
    geraete = {
        registry.async_get(e).device_id
        for e in (PAPA, FIENE, FAMILIE)
    }
    assert len(geraete) == 1


# ---------------------------------------------------------------------------
# Urlaub anlegen
# ---------------------------------------------------------------------------


async def test_urlaub_ueber_entitaeten(hass, eingerichtet):
    """Der Blueprint übergibt Entity-IDs; daraus werden die Namen aufgelöst."""
    antwort = await anlegen(hass, [PAPA, FIENE], "Gardasee")

    assert antwort["wer"] == "Papa und Mama"
    assert antwort["breitengrad"] == 45.65
    assert antwort["koordinaten_quelle"] == "geocoding"
    assert "Der Urlaub von Papa und Mama ist in" in antwort["nachricht"]
    assert "Die Reise geht nach Gardasee." in antwort["nachricht"]

    zustand = hass.states.get("sensor.urlaubszahler_urlaub_papa_und_mama_gardasee")
    assert zustand is not None
    assert hass.states.get(PAPA).state == "on"
    assert hass.states.get(FIENE).state == "on"


async def test_urlaub_ueber_klartextnamen(hass, eingerichtet):
    """Auch reine Namen werden akzeptiert."""
    antwort = await anlegen(hass, ["Papa"], "Mallorca")
    assert antwort["wer"] == "Papa"
    assert hass.states.get("sensor.urlaubszahler_urlaub_papa_mallorca") is not None


async def test_familie_zieht_mitglieder_mit(hass, eingerichtet):
    """Fährt die Familie, gelten auch ihre Mitglieder als verreist."""
    await anlegen(hass, [FAMILIE], "Lappland")

    zustand = hass.states.get("sensor.urlaubszahler_urlaub_familie_muster_lappland")
    assert zustand.attributes["namen"] == ["Familie Muster"]
    assert zustand.attributes["mitglieder"] == ["Papa", "Mama"]
    assert zustand.attributes["arten"] == ["familie"]

    # Papa und Mama sind über die Familie beteiligt.
    assert hass.states.get(PAPA).state == "on"
    assert hass.states.get(FIENE).state == "on"
    assert hass.states.get(PAPA).attributes["anzahl_urlaube"] == 1


async def test_unbekannter_name_bleibt_erhalten(hass, eingerichtet):
    """Ein Gast, der nicht konfiguriert ist, wird trotzdem übernommen."""
    antwort = await anlegen(hass, ["Onkel Otto"], "Gardasee")
    assert antwort["wer"] == "Onkel Otto"


async def test_mehrere_urlaube_parallel(hass, eingerichtet):
    """Beliebig viele Urlaube nebeneinander."""
    await anlegen(hass, [PAPA], "Gardasee", tage=10)
    await anlegen(hass, [FIENE], "Mallorca", tage=30)
    await anlegen(hass, [FAMILIE], "Lappland", tage=90)

    sensoren = [
        s for s in hass.states.async_all("sensor")
        if "urlaub_id" in s.attributes
    ]
    assert len(sensoren) == 3


async def test_gleiche_id_aktualisiert(hass, eingerichtet):
    """Ein zweiter Aufruf mit gleicher urlaub_id erzeugt kein Duplikat."""
    await anlegen(hass, [PAPA], "Gardasee", tage=10, urlaub_id="sommer")
    await anlegen(hass, [PAPA], "Gardasee", tage=20, urlaub_id="sommer")

    sensoren = [
        s for s in hass.states.async_all("sensor") if "urlaub_id" in s.attributes
    ]
    assert len(sensoren) == 1
    assert sensoren[0].attributes["tage"] == 19  # 20 Tage minus ein paar Sekunden


async def test_leere_teilnehmerliste(hass, eingerichtet):
    """Ohne Teilnehmer gibt es eine verständliche Fehlermeldung."""
    with pytest.raises(ServiceValidationError):
        await anlegen(hass, [], "Gardasee")


async def test_unbekannte_entry_id(hass, eingerichtet):
    """Eine falsche entry_id wird abgewiesen."""
    with pytest.raises(ServiceValidationError):
        await anlegen(hass, [PAPA], "Gardasee", entry_id="gibtsnicht")


# ---------------------------------------------------------------------------
# Koordinaten
# ---------------------------------------------------------------------------


async def test_ort_wird_nur_einmal_gesucht(hass, eingerichtet, geocode_aufrufe):
    """Der Zwischenspeicher verhindert wiederholte Anfragen."""
    await anlegen(hass, [PAPA], "Gardasee", tage=10, urlaub_id="a")
    await anlegen(hass, [FIENE], "Gardasee", tage=20, urlaub_id="b")
    assert geocode_aufrufe == ["Gardasee"]


async def test_manuelle_koordinaten_gewinnen(hass, eingerichtet, geocode_aufrufe):
    """Manuell gesetzte Koordinaten werden nicht überschrieben."""
    antwort = await anlegen(
        hass,
        [PAPA],
        "Gardasee",
        koordinaten={"latitude": 45.0, "longitude": 11.0, "radius": 100},
    )
    assert (antwort["breitengrad"], antwort["laengengrad"]) == (45.0, 11.0)
    assert antwort["koordinaten_quelle"] == "manuell"
    assert geocode_aufrufe == []


async def test_unbekannter_ort(hass, eingerichtet):
    """Wird kein Ort gefunden, entsteht der Urlaub trotzdem."""
    antwort = await anlegen(hass, [PAPA], "Fantasialand XYZ")
    assert antwort["breitengrad"] is None
    assert antwort["koordinaten_quelle"] is None

    zustand = hass.states.get("sensor.urlaubszahler_urlaub_papa_fantasialand_xyz")
    assert zustand is not None
    assert zustand.attributes["tage"] == 11


# ---------------------------------------------------------------------------
# Sensorwerte
# ---------------------------------------------------------------------------


async def test_sensorattribute(hass, eingerichtet):
    """Status ist die Unix-Zeit, die Attribute enthalten alles Weitere."""
    await anlegen(hass, [PAPA], "Gardasee", tage=12)
    zustand = hass.states.get("sensor.urlaubszahler_urlaub_papa_gardasee")

    unixzeit = float(zustand.state)
    assert unixzeit == pytest.approx(zustand.attributes["start_zeitstempel"])
    # Der Zeitpunkt liegt rund 12 Tage in der Zukunft.
    assert unixzeit - dt_util.utcnow().timestamp() == pytest.approx(12 * 86400, abs=60)

    attribute = zustand.attributes
    assert attribute["tage"] == 11  # 11 Tage und ~23:59 h
    assert attribute["stunden"] == 23
    assert attribute["ziel"] == "Gardasee"
    assert attribute["wer"] == "Papa"
    assert attribute["gestartet"] is False
    assert attribute["zeitzone"]
    assert attribute["gefunden_als"] == "Gardasee, Europa"
    # Löschzeitpunkt liegt exakt 24 Stunden nach dem Start.
    assert (
        attribute["wird_geloescht_zeitstempel"] - attribute["start_zeitstempel"]
        == 86400
    )


async def test_transportmittel_standardwert(hass, eingerichtet):
    """Ohne Angabe gilt 'unbekannt' - das Feld ist optional."""
    antwort = await anlegen(hass, [PAPA], "Gardasee")
    assert antwort["transportmittel"] == "unbekannt"
    zustand = hass.states.get("sensor.urlaubszahler_urlaub_papa_gardasee")
    assert zustand.attributes["transportmittel"] == "unbekannt"


async def test_transportmittel_wird_gespeichert(hass, eingerichtet):
    """Ein angegebenes Transportmittel landet in Antwort, Sensor und Speicher."""
    antwort = await anlegen(hass, [PAPA], "Gardasee", transportmittel="auto")
    assert antwort["transportmittel"] == "auto"
    zustand = hass.states.get("sensor.urlaubszahler_urlaub_papa_gardasee")
    assert zustand.attributes["transportmittel"] == "auto"

    # Übersteht auch einen Neustart (Persistenz über den Store).
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    zustand = hass.states.get("sensor.urlaubszahler_urlaub_papa_gardasee")
    assert zustand.attributes["transportmittel"] == "auto"


async def test_entfernung_und_reisedauer_im_sensor(hass, eingerichtet):
    """Entfernung ist immer da (sobald Koordinaten bekannt sind), die
    Reisedauer nur, wenn auch ein Transportmittel angegeben wurde."""
    await anlegen(hass, [PAPA], "Gardasee", transportmittel="auto")
    zustand = hass.states.get("sensor.urlaubszahler_urlaub_papa_gardasee")

    # Testinstanz steht in San Diego (pytest-homeassistant-custom-component),
    # Gardasee liegt auf der anderen Seite des Atlantiks - grobe Plausibilitätsprüfung.
    assert 8000 < zustand.attributes["entfernung_km"] < 11000
    assert zustand.attributes["reisedauer_std"] > 0
    assert zustand.attributes["reisedauer_text"].startswith("ca. ")


async def test_reisedauer_ohne_transportmittel_ist_none(hass, eingerichtet):
    """Ohne Transportmittel (Standard 'unbekannt') gibt es keine Dauer-Schätzung,
    die Entfernung steht aber trotzdem zur Verfügung."""
    await anlegen(hass, [PAPA], "Gardasee")
    zustand = hass.states.get("sensor.urlaubszahler_urlaub_papa_gardasee")

    assert zustand.attributes["entfernung_km"] is not None
    assert zustand.attributes["reisedauer_std"] is None
    assert zustand.attributes["reisedauer_text"] is None


async def test_reisedauer_ohne_koordinaten_ist_none(hass, eingerichtet):
    """Ohne bekannte Koordinaten (Ort nicht gefunden) gibt es weder Entfernung
    noch Reisedauer."""
    await anlegen(hass, [PAPA], "Fantasialand XYZ", transportmittel="auto")
    zustand = hass.states.get("sensor.urlaubszahler_urlaub_papa_fantasialand_xyz")

    assert zustand.attributes["entfernung_km"] is None
    assert zustand.attributes["reisedauer_std"] is None
    assert zustand.attributes["reisedauer_text"] is None


async def test_ankunftszeit_erst_kurz_vor_abreise(hass, eingerichtet, freezer):
    """Weit im Voraus nur die Dauer, die Ankunftsuhrzeit erst kurz vorher."""
    await anlegen(hass, [PAPA], "Gardasee", tage=12, transportmittel="auto")
    zustand = hass.states.get("sensor.urlaubszahler_urlaub_papa_gardasee")
    assert zustand.attributes["reisedauer_text"] is not None
    assert zustand.attributes["ankunftszeit_text"] is None

    # Nur noch rund ein Tag bis zur Abreise - jetzt greift die Schwelle.
    freezer.tick(timedelta(days=11))
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
    await hass.async_block_till_done()

    zustand = hass.states.get("sensor.urlaubszahler_urlaub_papa_gardasee")
    text = zustand.attributes["ankunftszeit_text"]
    assert text is not None
    assert text.startswith("Ankunft ca. ")
    assert text.endswith("Uhr Ortszeit")


async def test_ankunftszeit_ohne_transportmittel_bleibt_none(hass, eingerichtet):
    """Ohne Transportmittel gibt es auch kurz vor der Abreise keine Uhrzeit."""
    await anlegen(hass, [PAPA], "Gardasee", tage=1)
    zustand = hass.states.get("sensor.urlaubszahler_urlaub_papa_gardasee")
    assert zustand.attributes["ankunftszeit_text"] is None


async def test_transportmittel_ungueltiger_wert_wird_abgelehnt(hass, eingerichtet):
    """Nur die bekannten Optionen sind erlaubt."""
    with pytest.raises(vol.Invalid):
        await anlegen(hass, [PAPA], "Gardasee", transportmittel="rakete")


async def test_bestehender_urlaub_ohne_transportmittel_bleibt_nutzbar(
    hass, eingerichtet
):
    """Vor 1.0.5 gespeicherte Urlaube kennen das Feld noch nicht.

    Bestandsschutz: Vacation.from_dict() muss auch ohne den Schlüssel
    'transportmittel' funktionieren (siehe models.py).
    """
    from custom_components.urlaubszaehler.models import Vacation

    alt = {
        "urlaub_id": "alt_ohne_transportmittel",
        "namen": ["Papa"],
        "ziel": "Gardasee",
        "start": (dt_util.now() + timedelta(days=5)).isoformat(),
    }
    urlaub = Vacation.from_dict(alt)
    assert urlaub.transportmittel == "unbekannt"


async def test_countdown_stoppt_bei_null(hass, eingerichtet):
    """Nach dem Reisebeginn wird nicht negativ weitergerechnet."""
    await anlegen(hass, [PAPA], "Gardasee", tage=-0.5)  # vor 12 Stunden
    zustand = hass.states.get("sensor.urlaubszahler_urlaub_papa_gardasee")

    assert zustand.attributes["tage"] == 0
    assert zustand.attributes["stunden"] == 0
    assert zustand.attributes["minuten"] == 0
    assert zustand.attributes["verbleibende_sekunden"] == 0
    assert zustand.attributes["gestartet"] is True
    assert "ist in 0 Tagen, 0 Stunden und 0 Minuten" in zustand.attributes["nachricht"]


async def test_countdown_laeuft_weiter(hass, eingerichtet, freezer):
    """Die Restzeit sinkt mit fortschreitender Uhr."""
    await anlegen(hass, [PAPA], "Gardasee", tage=12)
    vorher = hass.states.get("sensor.urlaubszahler_urlaub_papa_gardasee")
    # Bei angehaltener Uhr sind es exakt 12 Tage.
    assert vorher.attributes["tage"] == 12

    freezer.tick(timedelta(days=5))
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
    await hass.async_block_till_done()

    nachher = hass.states.get("sensor.urlaubszahler_urlaub_papa_gardasee")
    assert nachher.attributes["tage"] == 7
    # Der Status (Abfahrtszeitpunkt) bleibt unverändert.
    assert nachher.state == vorher.state


# ---------------------------------------------------------------------------
# Auto-Delete
# ---------------------------------------------------------------------------


async def test_sensor_bleibt_kurz_vor_24_stunden(hass, eingerichtet, freezer):
    """23:59 Stunden nach der Abfahrt existiert der Sensor noch."""
    await anlegen(hass, [PAPA], "Gardasee", tage=0.02)  # in ~29 Minuten

    freezer.tick(timedelta(hours=23, minutes=50))
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
    await hass.async_block_till_done()

    assert hass.states.get("sensor.urlaubszahler_urlaub_papa_gardasee") is not None


async def test_sensor_verschwindet_nach_24_stunden(hass, eingerichtet, freezer):
    """Genau einen Tag nach der Abfahrt wird der Sensor restlos entfernt."""
    await anlegen(hass, [PAPA], "Gardasee", tage=0.02)
    registry = er.async_get(hass)
    assert registry.async_get("sensor.urlaubszahler_urlaub_papa_gardasee")

    freezer.tick(timedelta(hours=24, minutes=30))
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
    await hass.async_block_till_done()

    assert hass.states.get("sensor.urlaubszahler_urlaub_papa_gardasee") is None
    # Auch aus der Entitäten-Registry.
    assert registry.async_get("sensor.urlaubszahler_urlaub_papa_gardasee") is None
    # Der Teilnehmer gilt wieder als "kein Urlaub geplant".
    assert hass.states.get(PAPA).state == "off"


async def test_abgelaufener_urlaub_kommt_nach_neustart_nicht_zurueck(
    hass, eingerichtet, freezer
):
    """Beim Laden werden abgelaufene Urlaube sofort aussortiert."""
    await anlegen(hass, [PAPA], "Gardasee", tage=0.02)

    freezer.tick(timedelta(hours=30))
    await hass.config_entries.async_reload(eingerichtet.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.urlaubszahler_urlaub_papa_gardasee") is None


# ---------------------------------------------------------------------------
# Neustart und Entfernen
# ---------------------------------------------------------------------------


async def test_urlaube_ueberleben_neustart(hass, eingerichtet):
    """Nach einem Reload sind alle Urlaube wieder da."""
    await anlegen(hass, [PAPA], "Gardasee", tage=10)
    await anlegen(hass, [FAMILIE], "Lappland", tage=40)

    await hass.config_entries.async_reload(eingerichtet.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.urlaubszahler_urlaub_papa_gardasee") is not None
    assert (
        hass.states.get("sensor.urlaubszahler_urlaub_familie_muster_lappland")
        is not None
    )


async def test_remove_vacation(hass, eingerichtet):
    """Der Service entfernt Urlaub und Sensor."""
    await anlegen(hass, [PAPA], "Gardasee", urlaub_id="sommer")

    antwort = await hass.services.async_call(
        DOMAIN,
        "remove_vacation",
        {"urlaub_id": "sommer"},
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()

    assert antwort["entfernt"] is True
    assert hass.states.get("sensor.urlaubszahler_urlaub_papa_gardasee") is None

    # Ein zweiter Aufruf meldet sauber "nichts entfernt".
    antwort = await hass.services.async_call(
        DOMAIN,
        "remove_vacation",
        {"urlaub_id": "sommer"},
        blocking=True,
        return_response=True,
    )
    assert antwort["entfernt"] is False


async def test_list_vacations(hass, eingerichtet):
    """Der Service liefert alle Urlaube nach Datum sortiert."""
    await anlegen(hass, [FAMILIE], "Lappland", tage=40)
    await anlegen(hass, [PAPA], "Gardasee", tage=10)

    antwort = await hass.services.async_call(
        DOMAIN, "list_vacations", {}, blocking=True, return_response=True
    )
    assert antwort["anzahl"] == 2
    assert [u["ziel"] for u in antwort["urlaube"]] == ["Gardasee", "Lappland"]
    assert antwort["urlaube"][0]["tage"] == 9


async def test_entladen(hass, eingerichtet):
    """Beim Entladen verschwinden Entitäten und Services."""
    await anlegen(hass, [PAPA], "Gardasee")

    assert await hass.config_entries.async_unload(eingerichtet.entry_id)
    await hass.async_block_till_done()

    # Registrierte Entitäten bleiben als "nicht verfügbar" stehen (HA-Standard),
    # die Services sind weg.
    assert hass.states.get(PAPA).state == "unavailable"
    assert not hass.services.has_service(DOMAIN, "add_vacation")


async def test_24_stunden_auch_bei_zeitumstellung(hass, eingerichtet):
    """Die 24 Stunden bis zum Löschen sind echte Stunden, keine Kalenderstunden."""
    from custom_components.urlaubszaehler.models import Vacation

    # Abreise am Tag vor der Umstellung auf Winterzeit.
    urlaub = Vacation(
        "test", ["Papa"], "Gardasee", datetime(2026, 10, 24, 20, 0)
    )
    assert urlaub.delete_ts - urlaub.start_ts == 86400

    # Und auf Sommerzeit.
    urlaub = Vacation(
        "test", ["Papa"], "Gardasee", datetime(2026, 3, 28, 20, 0)
    )
    assert urlaub.delete_ts - urlaub.start_ts == 86400


async def test_koordinaten_werden_nachgetragen(hass, eingerichtet, monkeypatch, freezer):
    """Ein Ausfall von OpenStreetMap darf nicht dauerhaft folgenlos bleiben."""
    from custom_components.urlaubszaehler.const import DOMAIN as D

    # Erster Versuch schlägt fehl (z. B. Ratenbegrenzung).
    erreichbar = {"wert": False}

    async def _wackelig(hass_, ziel):
        if not erreichbar["wert"]:
            return None
        return {"breitengrad": 45.65, "laengengrad": 10.65,
                "gefunden_als": f"{ziel}, Europa"}

    monkeypatch.setattr(
        "custom_components.urlaubszaehler.manager.async_geocode", _wackelig
    )
    await anlegen(hass, [PAPA], "Gardasee", tage=12)

    zustand = hass.states.get("sensor.urlaubszahler_urlaub_papa_gardasee")
    assert zustand.attributes["breitengrad"] is None

    # Später ist der Dienst wieder da.
    erreichbar["wert"] = True
    freezer.tick(timedelta(minutes=31))
    manager = hass.data[D][eingerichtet.entry_id]
    assert await manager.async_koordinaten_nachtragen() == 1
    await hass.async_block_till_done()

    zustand = hass.states.get("sensor.urlaubszahler_urlaub_papa_gardasee")
    assert zustand.attributes["breitengrad"] == 45.65
    assert zustand.attributes["koordinaten_quelle"] == "geocoding"


async def test_nachtrag_haelt_abstand(hass, eingerichtet, monkeypatch):
    """Zwischen zwei Versuchen liegt ein Mindestabstand."""
    from custom_components.urlaubszaehler.const import DOMAIN as D

    versuche: list[str] = []

    async def _immer_fehlschlag(hass_, ziel):
        versuche.append(ziel)
        return None

    monkeypatch.setattr(
        "custom_components.urlaubszaehler.manager.async_geocode", _immer_fehlschlag
    )
    await anlegen(hass, [PAPA], "Gardasee", tage=12)
    assert versuche == ["Gardasee"]

    manager = hass.data[D][eingerichtet.entry_id]
    await manager.async_koordinaten_nachtragen()
    await manager.async_koordinaten_nachtragen()
    # Nur ein einziger zusätzlicher Versuch innerhalb der Wartezeit.
    assert versuche == ["Gardasee", "Gardasee"]

"""Tests für die Ortszeit-Bestimmung am Reiseziel (zielzeit.py)."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from custom_components.urlaubszaehler import zielzeit

GARDASEE = (45.65, 10.65)
HURGHADA = (27.26, 33.81)

UTC = timezone.utc


def test_zeitzone_bekannter_orte():
    assert zielzeit.zeitzone_am_ziel(*GARDASEE) == "Europe/Rome"
    assert zielzeit.zeitzone_am_ziel(*HURGHADA) == "Africa/Cairo"


def test_in_ortszeit_gleicher_zeitpunkt_andere_darstellung():
    """Die Umrechnung ändert nur die Darstellung, nicht den Zeitpunkt selbst."""
    start = datetime(2026, 8, 14, 10, 0, tzinfo=UTC)
    ortszeit = zielzeit.in_ortszeit(start, ZoneInfo("Europe/Rome"))

    assert ortszeit.utcoffset() in (timedelta(hours=1), timedelta(hours=2))
    assert ortszeit.astimezone(UTC) == start


def test_in_ortszeit_ohne_zeitzone_bleibt_unveraendert():
    """Ohne bestimmbare Zone (z. B. auf offener See) wird nichts umgerechnet."""
    start = datetime(2026, 8, 14, 10, 0, tzinfo=UTC)
    assert zielzeit.in_ortszeit(start, None) == start


async def test_zeitzonensuche_laeuft_im_executor(hass):
    """Die Suche darf den Event-Loop nicht blockieren.

    timezonefinder liest beim ersten Nachschlagen rund 65 MB von der Platte.
    Passiert das im Event-Loop, steht der ganze Home-Assistant-Server -
    genau das hat Home Assistant als "Detected blocking call" gemeldet.
    """
    loop_thread = threading.get_ident()
    threads: list[int] = []

    def _merker(lat: float, lon: float) -> str:
        threads.append(threading.get_ident())
        return "Europe/Rome"

    with patch.object(zielzeit, "zeitzone_am_ziel", _merker):
        name = await zielzeit.async_zeitzone_am_ziel(hass, *GARDASEE)

    assert name == "Europe/Rome"
    assert threads, "Die Zeitzone wurde gar nicht bestimmt"
    assert loop_thread not in threads


async def test_async_zone_liefert_nutzbare_zeitzone(hass):
    zone = await zielzeit.async_zone(hass, "Europe/Rome")
    assert zone is not None

    start = datetime(2026, 8, 14, 10, 0, tzinfo=UTC)
    assert zielzeit.in_ortszeit(start, zone).astimezone(UTC) == start


async def test_async_zone_ohne_namen(hass):
    assert await zielzeit.async_zone(hass, None) is None

"""Tests für die Ortszeit-Bestimmung am Reiseziel (zielzeit.py)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
    ortszeit = zielzeit.in_ortszeit(start, *GARDASEE)

    assert ortszeit.utcoffset() in (timedelta(hours=1), timedelta(hours=2))
    assert ortszeit.astimezone(UTC) == start


def test_in_ortszeit_ohne_bestimmbare_zeitzone_bleibt_unveraendert(monkeypatch):
    """Findet timezonefinder keine Zone (Ausnahmefall), wird nichts umgerechnet."""
    monkeypatch.setattr(zielzeit, "zeitzone_am_ziel", lambda lat, lon: None)
    start = datetime(2026, 8, 14, 10, 0, tzinfo=UTC)
    assert zielzeit.in_ortszeit(start, 0.0, 0.0) == start

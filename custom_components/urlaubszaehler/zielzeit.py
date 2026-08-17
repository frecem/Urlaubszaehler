"""Ortszeit am Reiseziel, für die Ankunftszeit-Anzeige kurz vor der Reise.

Nutzt `timezonefinder`, um aus den Zielkoordinaten die IANA-Zeitzone zu
bestimmen - komplett offline, keine Netzwerkabfrage. Das ist die einzige
Abhängigkeit dieser Integration (siehe ROADMAP.md, "Zeitzone am Ziel"): ohne
Ortszeit wäre eine Ankunftsuhrzeit bei Fernreisen irreführend (Berlin -> New
York: 10:00 Start + 8 Std. Flug ist 12:00 Ortszeit, nicht 18:00).
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from timezonefinder import TimezoneFinder

_finder: TimezoneFinder | None = None


def _get_finder() -> TimezoneFinder:
    """Einmalig anlegen - der Aufbau der internen Suchstruktur kostet Zeit."""
    global _finder
    if _finder is None:
        _finder = TimezoneFinder()
    return _finder


@lru_cache(maxsize=256)
def zeitzone_am_ziel(lat: float, lon: float) -> str | None:
    """IANA-Zeitzone am angegebenen Punkt, z. B. 'Europe/Rome'."""
    return _get_finder().timezone_at(lat=lat, lng=lon)


def in_ortszeit(zeitpunkt: datetime, lat: float, lon: float) -> datetime:
    """Zeitpunkt in die Ortszeit am Ziel umrechnen.

    Ist die Zeitzone nicht bestimmbar (z. B. auf offener See), wird der
    Zeitpunkt unverändert zurückgegeben.
    """
    name = zeitzone_am_ziel(lat, lon)
    if name is None:
        return zeitpunkt
    return zeitpunkt.astimezone(ZoneInfo(name))

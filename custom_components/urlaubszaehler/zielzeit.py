"""Ortszeit am Reiseziel, für die Ankunftszeit-Anzeige kurz vor der Reise.

Nutzt `timezonefinder`, um aus den Zielkoordinaten die IANA-Zeitzone zu
bestimmen - komplett offline, keine Netzwerkabfrage. Das ist die einzige
Abhängigkeit dieser Integration (siehe ROADMAP.md, "Zeitzone am Ziel"): ohne
Ortszeit wäre eine Ankunftsuhrzeit bei Fernreisen irreführend (Berlin -> New
York: 10:00 Start + 8 Std. Flug ist 12:00 Ortszeit, nicht 18:00).

**Alles hier Blockierende läuft ausschließlich im Executor.** Der
`TimezoneFinder`-Konstruktor liest rund 65 MB Geodaten von der Platte, und
`ZoneInfo` liest die Zonendatei aus dem System. Beides im Event-Loop würde den
gesamten Home-Assistant-Server anhalten; Home Assistant meldet das als
"Detected blocking call ... inside the event loop". Deshalb gibt es zu jeder
blockierenden Funktion eine `async_`-Variante, und die Umrechnung selbst
(`in_ortszeit`) bekommt die fertige Zeitzone übergeben, statt sie
nachzuschlagen.
"""

from __future__ import annotations

from datetime import datetime, tzinfo
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_finder: Any | None = None


def _finder_laden() -> Any:
    """Den TimezoneFinder einmalig aufbauen - **nur im Executor aufrufen**.

    Sowohl der Import (zieht numpy und die Paketdaten nach) als auch der
    Konstruktor lesen von der Platte.
    """
    global _finder
    if _finder is None:
        from timezonefinder import TimezoneFinder

        _finder = TimezoneFinder()
    return _finder


@lru_cache(maxsize=256)
def zeitzone_am_ziel(lat: float, lon: float) -> str | None:
    """IANA-Zeitzone am angegebenen Punkt, z. B. 'Europe/Rome'.

    **Nur im Executor aufrufen** - beim ersten Aufruf wird die Zeitzonendatei
    geladen. Für den Aufruf aus Home Assistant heraus gibt es
    `async_zeitzone_am_ziel`.
    """
    return _finder_laden().timezone_at(lat=lat, lng=lon)


async def async_zeitzone_am_ziel(
    hass: HomeAssistant, lat: float, lon: float
) -> str | None:
    """Zeitzone am Ziel bestimmen, ohne den Event-Loop zu blockieren."""
    return await hass.async_add_executor_job(zeitzone_am_ziel, lat, lon)


async def async_zone(hass: HomeAssistant, name: str | None) -> tzinfo | None:
    """Zu einem IANA-Namen die Zeitzone laden (Home Assistant cacht sie)."""
    if name is None:
        return None
    return await dt_util.async_get_time_zone(name)


def in_ortszeit(zeitpunkt: datetime, zone: tzinfo | None) -> datetime:
    """Zeitpunkt in die Ortszeit am Ziel umrechnen - reine Rechnung.

    Die Zeitzone wird bewusst übergeben statt hier nachgeschlagen: so bleibt
    diese Funktion frei von Dateizugriffen und darf im Event-Loop laufen. Ist
    die Zeitzone unbekannt (z. B. auf offener See oder noch nicht bestimmt),
    wird der Zeitpunkt unverändert zurückgegeben.
    """
    if zone is None:
        return zeitpunkt
    return zeitpunkt.astimezone(zone)

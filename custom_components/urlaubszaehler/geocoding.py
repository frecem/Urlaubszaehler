"""Reiseziele in Koordinaten übersetzen (OpenStreetMap / Nominatim).

Die Abfrage passiert genau einmal pro Reiseziel; das Ergebnis landet im
Speicher der Integration. Nominatim erlaubt maximal eine Anfrage pro Sekunde
und verlangt einen aussagekräftigen User-Agent - beides wird hier eingehalten.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = (
    "HomeAssistant-Urlaubszaehler/1.0 (+https://github.com/frecem/urlaubszaehler)"
)
TIMEOUT = aiohttp.ClientTimeout(total=15)

# Nominatim: höchstens eine Anfrage pro Sekunde.
_MINDESTABSTAND = 1.1
_sperre = asyncio.Lock()
_letzte_anfrage = 0.0


async def async_geocode(hass: HomeAssistant, ziel: str) -> dict[str, Any] | None:
    """Koordinaten zu einem Ortsnamen suchen.

    Gibt ``None`` zurück, wenn nichts gefunden wurde oder der Dienst nicht
    erreichbar ist - der Urlaub wird dann trotzdem angelegt, erscheint aber
    nicht auf der Karte.
    """
    global _letzte_anfrage

    ziel = ziel.strip()
    if not ziel:
        return None

    async with _sperre:
        schleife = hass.loop
        wartezeit = _MINDESTABSTAND - (schleife.time() - _letzte_anfrage)
        if wartezeit > 0:
            await asyncio.sleep(wartezeit)
        _letzte_anfrage = schleife.time()

        sitzung = async_get_clientsession(hass)
        try:
            antwort = await sitzung.get(
                NOMINATIM_URL,
                params={
                    "q": ziel,
                    "format": "jsonv2",
                    "limit": "1",
                    "accept-language": hass.config.language or "de",
                },
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT,
            )
            antwort.raise_for_status()
            treffer = await antwort.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as fehler:
            _LOGGER.warning(
                "Koordinaten für '%s' konnten nicht ermittelt werden: %s", ziel, fehler
            )
            return None

    if not treffer:
        _LOGGER.info("Für das Reiseziel '%s' wurde kein Ort gefunden", ziel)
        return None

    ort = treffer[0]
    try:
        return {
            "breitengrad": float(ort["lat"]),
            "laengengrad": float(ort["lon"]),
            "gefunden_als": ort.get("display_name", ziel),
        }
    except (KeyError, TypeError, ValueError):
        _LOGGER.warning("Unerwartete Antwort von Nominatim für '%s'", ziel)
        return None

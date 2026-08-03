"""Die Lovelace-Karte ausliefern und als Ressource eintragen.

Damit muss der Nutzer die Karte weder nach ``www/`` kopieren noch von Hand
unter *Dashboards → Ressourcen* eintragen - sie kommt mit der Integration.

Bewusst über eine Lovelace-Ressource und **nicht** über
``frontend.add_extra_js_url``: Letzteres bindet das Modul bereits in den
HTML-Kopf ein. Es läuft damit, bevor Home Assistant seinen
Scoped-Custom-Element-Registry-Polyfill installiert, und registriert die Karte
in der nativen statt in der von Home Assistant genutzten Registry. Die Folge
wäre „Custom element doesn't exist". Ressourcen werden dagegen erst nach dem
Frontend-Bundle geladen.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import CARD_DATEI, CARD_URL, DATA_CARD_REGISTRIERT, DOMAIN

_LOGGER = logging.getLogger(__name__)


def _kartendatei() -> Path:
    """Pfad der ausgelieferten Kartendatei."""
    return Path(__file__).parent / CARD_DATEI


async def async_karte_anmelden(hass: HomeAssistant) -> None:
    """Karte ausliefern und als Lovelace-Ressource hinterlegen."""
    datei = _kartendatei()
    if not await hass.async_add_executor_job(datei.is_file):
        _LOGGER.warning(
            "Die Kartendatei %s fehlt - die Urlaubszähler-Karte steht nicht "
            "zur Verfügung. Die Integration funktioniert davon unabhängig",
            datei,
        )
        return

    # Statische Pfade lassen sich in Home Assistant nicht wieder abmelden,
    # deshalb genau einmal pro Programmlauf registrieren.
    if not hass.data.get(DATA_CARD_REGISTRIERT):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, str(datei), True)]
        )
        hass.data[DATA_CARD_REGISTRIERT] = True

    # Die Version hängt an der URL, damit der Browser nach einem Update der
    # Integration nicht die alte Karte aus dem Zwischenspeicher nimmt.
    integration = await async_get_integration(hass, DOMAIN)
    await _async_ressource_eintragen(hass, f"{CARD_URL}?v={integration.version}")


async def _async_ressource_eintragen(hass: HomeAssistant, url: str) -> None:
    """Die Karte in der Ressourcenliste anlegen oder aktualisieren."""
    try:
        from homeassistant.components.lovelace.const import LOVELACE_DATA
    except ImportError:  # pragma: no cover - Lovelace ist Teil von default_config
        _LOGGER.debug("Lovelace ist nicht eingerichtet - Karte nicht eingetragen")
        return

    daten = hass.data.get(LOVELACE_DATA)
    if daten is None:
        _LOGGER.debug("Lovelace noch nicht bereit - Karte nicht eingetragen")
        return

    if daten.resource_mode != "storage":
        _LOGGER.warning(
            "Lovelace-Ressourcen werden über YAML verwaltet. Bitte einmalig "
            "'%s' als Modul in der configuration.yaml eintragen",
            url,
        )
        return

    sammlung = daten.resources
    # Beim ersten Zugriff muss die Sammlung geladen sein.
    if hasattr(sammlung, "async_get_info"):
        await sammlung.async_get_info()

    vorhandene = [
        eintrag
        for eintrag in sammlung.async_items()
        if str(eintrag.get("url", "")).startswith(CARD_URL)
    ]

    if not vorhandene:
        await sammlung.async_create_item({"res_type": "module", "url": url})
        _LOGGER.info("Urlaubszähler-Karte als Lovelace-Ressource eingetragen: %s", url)
        return

    # Vorhandenen Eintrag auf die aktuelle Version bringen, Dubletten entfernen.
    behalten = vorhandene[0]
    if behalten.get("url") != url:
        await sammlung.async_update_item(
            behalten["id"], {"res_type": "module", "url": url}
        )
        _LOGGER.info("Urlaubszähler-Karte auf %s aktualisiert", url)
    for doppelt in vorhandene[1:]:
        await sammlung.async_delete_item(doppelt["id"])

"""Den mitgelieferten Blueprint ins Konfigurationsverzeichnis legen.

Home Assistant kopiert Blueprints nur für eigene Integrationen automatisch;
für Custom Components muss das die Integration selbst erledigen. Eigene
Änderungen des Nutzers am Blueprint bleiben dabei erhalten.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path

from homeassistant.core import HomeAssistant

from .const import BLUEPRINT_QUELLE, BLUEPRINT_ZIEL

_LOGGER = logging.getLogger(__name__)


def _pruefsumme(inhalt: bytes) -> str:
    return hashlib.sha256(inhalt).hexdigest()


def _installieren(quelle: Path, ziel: Path, letzte_pruefsumme: str | None) -> tuple[str, bool]:
    """Blueprint schreiben. Gibt Prüfsumme und zurück, ob geschrieben wurde."""
    inhalt = quelle.read_bytes()
    neu = _pruefsumme(inhalt)

    if not ziel.exists():
        ziel.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(quelle, ziel)
        return neu, True

    vorhanden = _pruefsumme(ziel.read_bytes())
    if vorhanden == neu:
        # Schon aktuell.
        return neu, False

    if letzte_pruefsumme is not None and vorhanden == letzte_pruefsumme:
        # Unverändert seit unserer letzten Auslieferung -> gefahrlos ersetzen.
        shutil.copyfile(quelle, ziel)
        return neu, True

    # Der Nutzer hat den Blueprint angepasst - nicht überschreiben.
    _LOGGER.info(
        "Der Blueprint %s wurde von Hand geändert und bleibt unangetastet. "
        "Eine neuere Fassung liegt in %s",
        ziel,
        quelle,
    )
    return vorhanden, False


async def async_blueprint_bereitstellen(
    hass: HomeAssistant, letzte_pruefsumme: str | None
) -> str | None:
    """Blueprint bereitstellen und die Prüfsumme der Auslieferung zurückgeben."""
    quelle = Path(__file__).parent / BLUEPRINT_QUELLE
    if not await hass.async_add_executor_job(quelle.is_file):
        _LOGGER.warning("Der mitgelieferte Blueprint fehlt: %s", quelle)
        return letzte_pruefsumme

    ziel = Path(hass.config.path(BLUEPRINT_ZIEL))
    try:
        pruefsumme, geschrieben = await hass.async_add_executor_job(
            _installieren, quelle, ziel, letzte_pruefsumme
        )
    except OSError as fehler:
        _LOGGER.warning("Blueprint konnte nicht bereitgestellt werden: %s", fehler)
        return letzte_pruefsumme

    if geschrieben:
        _LOGGER.info("Blueprint bereitgestellt: %s", ziel)
        await _zwischenspeicher_leeren(hass)

    return pruefsumme


async def _zwischenspeicher_leeren(hass: HomeAssistant) -> None:
    """Blueprint-Zwischenspeicher leeren, damit der neue sofort auftaucht."""
    try:
        from homeassistant.components.blueprint.models import DomainBlueprints
        from homeassistant.components.blueprint.const import DOMAIN as BLUEPRINT_DOMAIN

        blueprints: dict[str, DomainBlueprints] = hass.data.get(BLUEPRINT_DOMAIN, {})
        if (automationen := blueprints.get("automation")) is not None:
            await automationen.async_reset_cache()
    except (ImportError, AttributeError) as fehler:  # pragma: no cover - defensiv
        _LOGGER.debug("Blueprint-Zwischenspeicher nicht geleert: %s", fehler)

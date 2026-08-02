"""Tests für die mitgelieferte Karte und den mitgelieferten Blueprint.

Beides wird von der Integration selbst bereitgestellt, damit eine Installation
über HACS (Kategorie *Integration*) ohne Handgriffe auskommt.
"""

from __future__ import annotations

import pathlib

from homeassistant.components.lovelace.const import LOVELACE_DATA

from custom_components.urlaubszaehler.const import (
    BLUEPRINT_ZIEL,
    CARD_DATEI,
    CARD_URL,
)

PAKET = pathlib.Path("custom_components/urlaubszaehler")


def _ressourcen(hass) -> list[str]:
    """Die eingetragenen Lovelace-Ressourcen."""
    daten = hass.data.get(LOVELACE_DATA)
    if daten is None:
        return []
    return [str(e.get("url", "")) for e in daten.resources.async_items()]


# ---------------------------------------------------------------------------
# Ausgelieferte Dateien
# ---------------------------------------------------------------------------


def test_karte_liegt_im_paket():
    """Die Kartendatei wird mit der Integration ausgeliefert."""
    datei = PAKET / CARD_DATEI
    assert datei.is_file()
    inhalt = datei.read_text()
    assert "urlaubszaehler-card" in inhalt
    assert "customElements.define" in inhalt


def test_beispielkarten_liegen_im_paket():
    """Die Lovelace-Beispiele werden mitinstalliert."""
    datei = PAKET / "lovelace" / "urlaubszaehler_karte.yaml"
    assert datei.is_file()
    assert "custom:urlaubszaehler-card" in datei.read_text()


# ---------------------------------------------------------------------------
# Karte
# ---------------------------------------------------------------------------


async def test_karte_wird_als_ressource_eingetragen(hass, eingerichtet):
    """Die Karte steht ohne Zutun des Nutzers in der Ressourcenliste.

    Bewusst eine Ressource und kein 'extra module url': Letzteres lädt die
    Karte vor dem Scoped-Registry-Polyfill von Home Assistant, wodurch sie in
    der falschen Registry landet und als "Custom element doesn't exist" endet.
    """
    passende = [u for u in _ressourcen(hass) if u.startswith(CARD_URL)]
    assert len(passende) == 1
    # Die Version hängt zur Umgehung des Browser-Zwischenspeichers an der URL.
    assert passende[0].startswith(f"{CARD_URL}?v=")


async def test_karte_wird_ausgeliefert(hass, eingerichtet, hass_client):
    """Die Kartendatei ist unter ihrer URL abrufbar."""
    client = await hass_client()
    antwort = await client.get(CARD_URL)
    assert antwort.status == 200
    inhalt = await antwort.text()
    assert "customElements.define" in inhalt


async def test_karte_uebersteht_neuladen(hass, eingerichtet):
    """Ein Reload trägt die Karte nicht doppelt ein."""
    await hass.config_entries.async_reload(eingerichtet.entry_id)
    await hass.async_block_till_done()

    passende = [u for u in _ressourcen(hass) if u.startswith(CARD_URL)]
    assert len(passende) == 1


# ---------------------------------------------------------------------------
# Blueprint
# ---------------------------------------------------------------------------


async def test_blueprint_wird_installiert(hass, eingerichtet):
    """Der Blueprint landet im Konfigurationsverzeichnis."""
    ziel = pathlib.Path(hass.config.path(BLUEPRINT_ZIEL))
    assert ziel.is_file()
    assert ziel.read_text() == (PAKET / "blueprints" / "automation"
                                / "urlaubszaehler" / "urlaub_anlegen.yaml").read_text()


async def test_eigene_aenderungen_bleiben_erhalten(hass, eingerichtet):
    """Ein vom Nutzer angepasster Blueprint wird nicht überschrieben."""
    ziel = pathlib.Path(hass.config.path(BLUEPRINT_ZIEL))
    eigener_text = ziel.read_text() + "\n# von Hand angepasst\n"
    ziel.write_text(eigener_text)

    await hass.config_entries.async_reload(eingerichtet.entry_id)
    await hass.async_block_till_done()

    assert ziel.read_text() == eigener_text


async def test_unveraenderter_blueprint_wird_aktualisiert(hass, eingerichtet):
    """Eine neue Fassung ersetzt eine unveränderte alte."""
    ziel = pathlib.Path(hass.config.path(BLUEPRINT_ZIEL))
    aktuell = (PAKET / "blueprints" / "automation" / "urlaubszaehler"
               / "urlaub_anlegen.yaml").read_text()

    # Eine ältere Fassung vortäuschen, deren Prüfsumme die Integration kennt.
    from custom_components.urlaubszaehler.const import DOMAIN

    manager = hass.data[DOMAIN][eingerichtet.entry_id]
    alt = "# alte Fassung\n" + aktuell
    ziel.write_text(alt)
    import hashlib

    manager.blueprint_pruefsumme = hashlib.sha256(alt.encode()).hexdigest()
    await manager.async_save()

    await hass.config_entries.async_reload(eingerichtet.entry_id)
    await hass.async_block_till_done()

    assert ziel.read_text() == aktuell

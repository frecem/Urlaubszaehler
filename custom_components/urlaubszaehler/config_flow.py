"""Config- und Options-Flow für den Urlaubszähler."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
    ConfigEntry,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .const import (
    CONF_FAMILIEN,
    CONF_FAMILY_COUNT,
    CONF_MITGLIEDER,
    CONF_NAME,
    CONF_PERSON_COUNT,
    CONF_PERSONEN,
    DOMAIN,
)

TITEL = "Urlaubszähler"

COUNT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PERSON_COUNT, default=2): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=20)
        ),
        vol.Required(CONF_FAMILY_COUNT, default=1): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=10)
        ),
    }
)


def _personen_schema(anzahl: int, vorgabe: list[str]) -> vol.Schema:
    """Schema mit einem Textfeld je Person.

    Die Feldnamen sind bewusst lesbar ("Person 1"), weil Home Assistant bei
    dynamischen Feldern den Schlüssel als Beschriftung anzeigt.
    """
    felder: dict[Any, Any] = {}
    for index in range(anzahl):
        default = vorgabe[index] if index < len(vorgabe) else ""
        felder[vol.Required(f"Person {index + 1}", default=default)] = TextSelector()
    return vol.Schema(felder)


def _familien_schema(
    anzahl: int, personen: list[str], vorgabe: list[dict[str, Any]]
) -> vol.Schema:
    """Schema mit Name und (optionalen) Mitgliedern je Familie."""
    felder: dict[Any, Any] = {}
    for index in range(anzahl):
        alt = vorgabe[index] if index < len(vorgabe) else {}
        felder[vol.Required(f"Familie {index + 1}", default=alt.get(CONF_NAME, ""))] = (
            TextSelector()
        )
        felder[
            vol.Optional(
                f"Mitglieder von Familie {index + 1}",
                default=[m for m in alt.get(CONF_MITGLIEDER, []) if m in personen],
            )
        ] = SelectSelector(
            SelectSelectorConfig(
                options=personen, multiple=True, mode=SelectSelectorMode.LIST
            )
        )
    return vol.Schema(felder)


def _lese_personen(anzahl: int, eingaben: dict[str, Any]) -> list[str]:
    """Personennamen aus den dynamischen Feldern einsammeln."""
    namen = []
    for index in range(anzahl):
        name = str(eingaben.get(f"Person {index + 1}", "")).strip()
        if name:
            namen.append(name)
    return list(dict.fromkeys(namen))


def _lese_familien(anzahl: int, eingaben: dict[str, Any]) -> list[dict[str, Any]]:
    """Familien aus den dynamischen Feldern einsammeln."""
    familien = []
    for index in range(anzahl):
        name = str(eingaben.get(f"Familie {index + 1}", "")).strip()
        if not name:
            continue
        familien.append(
            {
                CONF_NAME: name,
                CONF_MITGLIEDER: list(
                    eingaben.get(f"Mitglieder von Familie {index + 1}", []) or []
                ),
            }
        )
    return familien


class UrlaubszaehlerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Einrichtung über die Benutzeroberfläche."""

    VERSION = 1

    def __init__(self) -> None:
        """Zwischenspeicher für die mehrstufige Einrichtung."""
        self._person_count = 0
        self._family_count = 0
        self._personen: list[str] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Schritt 1: Wie viele Personen und Familien gibt es?"""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=COUNT_SCHEMA)

        self._person_count = user_input[CONF_PERSON_COUNT]
        self._family_count = user_input[CONF_FAMILY_COUNT]
        return await self.async_step_personen()

    async def async_step_personen(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Schritt 2: Namen der Personen."""
        if user_input is None:
            return self.async_show_form(
                step_id="personen",
                data_schema=_personen_schema(self._person_count, []),
            )

        self._personen = _lese_personen(self._person_count, user_input)
        if not self._personen:
            return self.async_show_form(
                step_id="personen",
                data_schema=_personen_schema(self._person_count, []),
                errors={"base": "keine_namen"},
            )

        if self._family_count:
            return await self.async_step_familien()
        return self._erstelle_eintrag([])

    async def async_step_familien(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Schritt 3: Namen der Familien (und optional deren Mitglieder)."""
        if user_input is None:
            return self.async_show_form(
                step_id="familien",
                data_schema=_familien_schema(self._family_count, self._personen, []),
            )
        return self._erstelle_eintrag(_lese_familien(self._family_count, user_input))

    def _erstelle_eintrag(self, familien: list[dict[str, Any]]) -> ConfigFlowResult:
        return self.async_create_entry(
            title=TITEL,
            data={
                CONF_PERSON_COUNT: len(self._personen),
                CONF_FAMILY_COUNT: len(familien),
                CONF_PERSONEN: self._personen,
                CONF_FAMILIEN: familien,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> UrlaubszaehlerOptionsFlow:
        """Options-Flow bereitstellen."""
        return UrlaubszaehlerOptionsFlow()


class UrlaubszaehlerOptionsFlow(OptionsFlow):
    """Nachträgliches Bearbeiten der Namen und Löschen von Urlauben."""

    def __init__(self) -> None:
        """Zwischenspeicher für die mehrstufige Bearbeitung."""
        self._person_count = 0
        self._family_count = 0
        self._personen: list[str] = []

    @property
    def _aktuell(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Auswahl, was bearbeitet werden soll."""
        return self.async_show_menu(step_id="init", menu_options=["namen", "urlaube"])

    # ------------------------------------------------------------------
    # Namen bearbeiten
    # ------------------------------------------------------------------
    async def async_step_namen(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Anzahl der Personen und Familien anpassen."""
        aktuell = self._aktuell
        if user_input is None:
            schema = vol.Schema(
                {
                    vol.Required(
                        CONF_PERSON_COUNT,
                        default=len(aktuell.get(CONF_PERSONEN, [])) or 1,
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=20)),
                    vol.Required(
                        CONF_FAMILY_COUNT,
                        default=len(aktuell.get(CONF_FAMILIEN, [])),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=10)),
                }
            )
            return self.async_show_form(step_id="namen", data_schema=schema)

        self._person_count = user_input[CONF_PERSON_COUNT]
        self._family_count = user_input[CONF_FAMILY_COUNT]
        return await self.async_step_namen_personen()

    async def async_step_namen_personen(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Personennamen bearbeiten."""
        if user_input is None:
            return self.async_show_form(
                step_id="namen_personen",
                data_schema=_personen_schema(
                    self._person_count, self._aktuell.get(CONF_PERSONEN, [])
                ),
            )

        self._personen = _lese_personen(self._person_count, user_input)
        if not self._personen:
            return self.async_show_form(
                step_id="namen_personen",
                data_schema=_personen_schema(
                    self._person_count, self._aktuell.get(CONF_PERSONEN, [])
                ),
                errors={"base": "keine_namen"},
            )

        if self._family_count:
            return await self.async_step_namen_familien()
        return self._speichern([])

    async def async_step_namen_familien(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Familiennamen bearbeiten."""
        if user_input is None:
            return self.async_show_form(
                step_id="namen_familien",
                data_schema=_familien_schema(
                    self._family_count,
                    self._personen,
                    self._aktuell.get(CONF_FAMILIEN, []),
                ),
            )
        return self._speichern(_lese_familien(self._family_count, user_input))

    def _speichern(self, familien: list[dict[str, Any]]) -> ConfigFlowResult:
        return self.async_create_entry(
            data={
                CONF_PERSON_COUNT: len(self._personen),
                CONF_FAMILY_COUNT: len(familien),
                CONF_PERSONEN: self._personen,
                CONF_FAMILIEN: familien,
            }
        )

    # ------------------------------------------------------------------
    # Urlaube löschen
    # ------------------------------------------------------------------
    async def async_step_urlaube(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Geplante Urlaube vorzeitig entfernen."""
        manager = self.hass.data[DOMAIN][self.config_entry.entry_id]
        optionen = [
            {
                "value": urlaub.urlaub_id,
                "label": (
                    f"{urlaub.wer} → {urlaub.ziel} "
                    f"({urlaub.start.strftime('%d.%m.%Y %H:%M')})"
                ),
            }
            for urlaub in sorted(manager.vacations.values(), key=lambda u: u.start)
        ]

        if not optionen:
            return self.async_abort(reason="keine_urlaube")

        if user_input is None:
            schema = vol.Schema(
                {
                    vol.Optional("loeschen", default=[]): SelectSelector(
                        SelectSelectorConfig(
                            options=optionen,
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            )
            return self.async_show_form(step_id="urlaube", data_schema=schema)

        for urlaub_id in user_input.get("loeschen", []):
            await manager.async_remove_vacation(urlaub_id)

        # Optionen unverändert lassen, damit kein Reload nötig ist.
        return self.async_create_entry(data=dict(self.config_entry.options))

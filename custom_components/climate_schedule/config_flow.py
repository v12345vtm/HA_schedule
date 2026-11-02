# Bestand: custom_components/climate_schedule/config_flow.py
# Versie: 0.0.3
"""Config flow en options flow: met een climate picker kies je welke climates beheerd worden."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig

from .const import CONF_CLIMATES, DOMAIN


def _climate_schema(default: list[str]) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_CLIMATES, default=default): EntitySelector(
            EntitySelectorConfig(domain="climate", multiple=True)
        )
    })


class ClimateScheduleConfigFlow(ConfigFlow, domain=DOMAIN):
    """Eerste installatie: kies de climates."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            if not user_input[CONF_CLIMATES]:
                return self.async_show_form(
                    step_id="user",
                    data_schema=_climate_schema([]),
                    errors={"base": "no_climates"},
                )
            return self.async_create_entry(
                title="Climate Schedule", data={}, options=user_input
            )

        return self.async_show_form(step_id="user", data_schema=_climate_schema([]))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ClimateScheduleOptionsFlow()


class ClimateScheduleOptionsFlow(OptionsFlow):
    """Later aanpassen: climates toevoegen of verwijderen."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            if not user_input[CONF_CLIMATES]:
                return self.async_show_form(
                    step_id="init",
                    data_schema=_climate_schema([]),
                    errors={"base": "no_climates"},
                )
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options.get(CONF_CLIMATES, [])
        return self.async_show_form(step_id="init", data_schema=_climate_schema(current))

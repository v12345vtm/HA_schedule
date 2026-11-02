# Bestand: custom_components/climate_schedule/switch.py
# Versie: 0.0.3
"""Hoofdschakelaar testmodus: alles wordt berekend en gelogd, maar er wordt niets naar de climates gestuurd."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_UPDATE


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    manager = hass.data[DOMAIN]
    async_add_entities([ClimateScheduleTestSwitch(manager, entry)])


class ClimateScheduleTestSwitch(SwitchEntity):
    _attr_has_entity_name = False
    _attr_name = "Climate Schedule testmodus"
    _attr_icon = "mdi:flask-outline"
    _attr_should_poll = False

    def __init__(self, manager, entry: ConfigEntry) -> None:
        self._m = manager
        self._attr_unique_id = f"{DOMAIN}_testmodus_{entry.entry_id}"

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_UPDATE, self.async_write_ha_state)
        )

    @property
    def is_on(self) -> bool:
        return self._m.test_mode

    async def async_turn_on(self, **kwargs) -> None:
        await self._m.async_set_test_mode(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._m.async_set_test_mode(False)

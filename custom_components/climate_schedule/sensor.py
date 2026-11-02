# Bestand: custom_components/climate_schedule/sensor.py
# Versie: 0.0.3
"""Sommatie-sensor per geselecteerde climate: effectief setpoint nu, plus het dagverloop per weekdag."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import resolver as r
from .const import CONF_CLIMATES, DOMAIN, SIGNAL_UPDATE


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    manager = hass.data[DOMAIN]
    climates = entry.options.get(CONF_CLIMATES, [])
    async_add_entities([SommatieSensor(manager, climate) for climate in climates])


class SommatieSensor(SensorEntity):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_should_poll = False

    def __init__(self, manager, climate: str) -> None:
        self._m = manager
        self._climate = climate
        obj = climate.split(".", 1)[1]
        self._attr_unique_id = f"sommatie_{obj}"
        self._attr_name = f"Sommatie {obj}"

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_UPDATE, self.async_write_ha_state)
        )

    @staticmethod
    def _now():
        now = dt_util.now()
        return now.weekday(), now.hour * 60 + now.minute

    @property
    def native_value(self):
        idx, minute = self._now()
        temp, _, _ = r.effective(self._m.data, self._climate, idx, minute)
        return temp

    @property
    def extra_state_attributes(self):
        idx, minute = self._now()
        temp, users, source = r.effective(self._m.data, self._climate, idx, minute)
        week = {
            day: r.timeline(self._m.data, self._climate, i)
            for i, day in enumerate(r.WEEKDAYS)
        }
        return {
            "bron": source,
            "gebruikers": users,
            "presets_vandaag": r.today_presets(self._m.data, idx),
            "testmodus": self._m.test_mode,
            "vandaag": week[r.WEEKDAYS[idx]],
            "week": week,
        }

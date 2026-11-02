# Bestand: custom_components/climate_schedule/__init__.py
# Versie: 0.0.1
"""Climate Schedule: presets per gebruiker, per weekdag gekoppeld, gecombineerd per climate."""
from __future__ import annotations

import copy
import json
import logging
from pathlib import Path

import voluptuous as vol

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import resolver as r

_LOGGER = logging.getLogger(__name__)

DOMAIN = "climate_schedule"
VERSION = "0.0.1"
CONF_CLIMATES = "climates"
STORAGE_VERSION = 2
SIGNAL_UPDATE = f"{DOMAIN}_updated"
SEED_FILE = Path(__file__).parent / "seed.json"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {vol.Required(CONF_CLIMATES): vol.All(cv.ensure_list, [cv.entity_id])}
        )
    },
    extra=vol.ALLOW_EXTRA,
)

TIME = vol.All(cv.string, r.valid_time)
TEMP = vol.All(vol.Coerce(float), vol.Range(min=5, max=35))
DAY = vol.In(r.WEEKDAYS)


class ScheduleManager:
    """Houdt het datamodel vast en stuurt de climates aan."""

    def __init__(self, hass: HomeAssistant, store: Store, data: dict, climates: list[str]):
        self.hass = hass
        self.store = store
        self.data = data
        self.climates = climates
        self._last_applied: dict[str, float] = {}

    async def async_mutate(self, fn, **kwargs) -> None:
        """Voer een mutatie uit op een kopie, valideer, en pas dan pas op."""
        candidate = copy.deepcopy(self.data)
        try:
            fn(candidate, **kwargs)
        except (r.ScheduleError, KeyError, ValueError, TypeError) as err:
            raise HomeAssistantError(str(err)) from err
        errors = r.validate(candidate)
        if errors:
            raise HomeAssistantError("; ".join(errors))
        self.data = candidate
        await self.store.async_save(self.data)
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)
        await self.async_apply_all(force=True)

    async def async_tick(self, now) -> None:
        """Elke minuut: sensoren verversen en setpoint sturen bij wijziging."""
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)
        await self.async_apply_all()

    async def async_apply_all(self, force: bool = False) -> None:
        now = dt_util.now()
        minute = now.hour * 60 + now.minute
        for climate in self.climates:
            await self._apply(climate, now.weekday(), minute, force)

    async def _apply(self, climate: str, weekday: int, minute: int, force: bool) -> None:
        temp, _users, _source = r.effective(self.data, climate, weekday, minute)
        if temp is None:
            return

        state = self.hass.states.get(climate)
        if state is None:
            _LOGGER.warning("Climate %s niet gevonden", climate)
            return

        lo = state.attributes.get("min_temp", temp)
        hi = state.attributes.get("max_temp", temp)
        if not lo <= temp <= hi:
            _LOGGER.warning("%s: %s°C ligt buiten %s–%s, wordt begrensd", climate, temp, lo, hi)
            temp = min(max(temp, lo), hi)

        # Alleen sturen bij een wijziging van het setpoint, zodat een handmatige
        # aanpassing op de thermostaat blijft staan tot het volgende slotmoment.
        if not force and self._last_applied.get(climate) == temp:
            return
        self._last_applied[climate] = temp

        await self.hass.services.async_call(
            "climate",
            "set_temperature",
            {"entity_id": climate, "temperature": temp},
            blocking=True,
        )


def _load_seed() -> dict:
    if SEED_FILE.exists():
        data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
        data.pop("_meta", None)
        return data
    return {"schema_version": STORAGE_VERSION, "users": {}, "defaults": {}}


def _make_handler(manager: ScheduleManager, fn):
    async def handler(call: ServiceCall) -> None:
        await manager.async_mutate(fn, **call.data)
    return handler


def _register_services(hass: HomeAssistant, m: ScheduleManager) -> None:
    services = {
        "add_user": (r.add_user, vol.Schema({
            vol.Required("name"): cv.string,
        })),
        "remove_user": (r.remove_user, vol.Schema({
            vol.Required("name"): cv.string,
        })),
        "set_preset_slot": (r.set_preset_slot, vol.Schema({
            vol.Required("user"): cv.string,
            vol.Required("preset"): cv.string,
            vol.Required("climate"): cv.entity_id,
            vol.Required("start"): TIME,
            vol.Required("end"): TIME,
            vol.Required("temp"): TEMP,
        })),
        "remove_preset_slot": (r.remove_preset_slot, vol.Schema({
            vol.Required("user"): cv.string,
            vol.Required("preset"): cv.string,
            vol.Required("climate"): cv.entity_id,
            vol.Required("start"): TIME,
        })),
        "delete_preset": (r.delete_preset, vol.Schema({
            vol.Required("user"): cv.string,
            vol.Required("preset"): cv.string,
        })),
        "set_schedule": (r.set_schedule, vol.Schema({
            vol.Required("user"): cv.string,
            vol.Required("weekday"): DAY,
            vol.Optional("preset"): vol.Any(None, cv.string),
        })),
        "set_default": (r.set_default, vol.Schema({
            vol.Required("climate"): cv.entity_id,
            vol.Required("weekday"): DAY,
            vol.Optional("temp"): vol.Any(None, TEMP),
        })),
    }
    for name, (fn, schema) in services.items():
        hass.services.async_register(DOMAIN, name, _make_handler(m, fn), schema=schema)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    conf = config[DOMAIN]

    # Opslag: .storage/climate_schedule (JSON, door HA beheerd)
    store = Store(hass, STORAGE_VERSION, DOMAIN)
    data = await store.async_load()
    if data is None:
        data = await hass.async_add_executor_job(_load_seed)
        await store.async_save(data)
        _LOGGER.info("Climate Schedule: startdata uit seed.json geladen")
    data.setdefault("users", {})
    data.setdefault("defaults", {})

    for err in r.validate(data):
        _LOGGER.warning("Climate Schedule datamodel: %s", err)

    manager = ScheduleManager(hass, store, data, conf[CONF_CLIMATES])
    hass.data[DOMAIN] = manager

    _register_services(hass, manager)
    async_track_time_change(hass, manager.async_tick, second=0)
    await async_load_platform(
        hass, Platform.SENSOR, DOMAIN, {"climates": conf[CONF_CLIMATES]}, config
    )
    await manager.async_apply_all(force=True)
    return True

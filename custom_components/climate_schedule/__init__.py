# Bestand: custom_components/climate_schedule/__init__.py
# Versie: 0.0.3
"""Climate Schedule: presets per gebruiker, per weekdag gekoppeld, gecombineerd per climate.

De beheerde climates kies je in de UI (config flow / opties), niet in configuration.yaml.
Met de hoofdschakelaar testmodus wordt alles berekend en gelogd, maar niets naar de climates gestuurd.
"""
from __future__ import annotations

import copy
import json
import logging
from pathlib import Path

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import resolver as r
from .const import CONF_CLIMATES, DOMAIN, SIGNAL_UPDATE, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR, Platform.SWITCH]
SEED_FILE = Path(__file__).parent / "seed.json"

TIME = vol.All(cv.string, r.valid_time)
TEMP = vol.All(vol.Coerce(float), vol.Range(min=5, max=35))
DAY = vol.In(r.WEEKDAYS)


class ScheduleManager:
    """Houdt het datamodel vast en stuurt de geselecteerde climates aan."""

    def __init__(self, hass: HomeAssistant, store: Store, data: dict, climates: list[str]):
        self.hass = hass
        self.store = store
        self.data = data
        self.climates = climates
        self._last_applied: dict[str, float] = {}
        self._last_planned: dict[str, float] = {}

    @property
    def test_mode(self) -> bool:
        return bool(self.data.get("test_mode", True))

    async def async_set_test_mode(self, enabled: bool) -> None:
        """Zet de hoofdschakelaar. Uit zetten stuurt direct de huidige stand naar de climates."""
        if self.test_mode == enabled:
            return
        self.data["test_mode"] = enabled
        self._last_planned.clear()
        await self.store.async_save(self.data)
        _LOGGER.warning("Climate Schedule testmodus %s", "AAN" if enabled else "UIT")
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)
        await self.async_apply_all(force=True)

    async def async_mutate(self, fn, **kwargs) -> None:
        """Voer een mutatie uit op een kopie, valideer, en pas dan pas toe."""
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
        if self.hass.states.get(climate) is None:
            _LOGGER.warning("Climate %s bestaat niet (meer)", climate)
            return

        # Testmodus: niets sturen, alleen loggen wat er zou gebeuren (bij elke wijziging).
        if self.test_mode:
            if self._last_planned.get(climate) != temp:
                _LOGGER.info("TESTMODUS %s: zou op %s°C gaan (er wordt niets gestuurd)", climate, temp)
                self._last_planned[climate] = temp
            return

        # Geen begrenzing in de code: de climate zelf bepaalt of de waarde mag.
        # Alleen sturen bij een wijziging, zodat een handmatige aanpassing blijft staan.
        if not force and self._last_applied.get(climate) == temp:
            return
        try:
            await self.hass.services.async_call(
                "climate",
                "set_temperature",
                {"entity_id": climate, "temperature": temp},
                blocking=True,
            )
        except HomeAssistantError as err:
            _LOGGER.error(
                "%s: %s°C niet ingesteld, de climate weigerde de waarde: %s", climate, temp, err
            )
            return
        self._last_applied[climate] = temp


def _load_seed() -> dict:
    if SEED_FILE.exists():
        data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
        data.pop("_meta", None)
        return data
    return {"schema_version": STORAGE_VERSION, "users": {}, "defaults": {}}


def _make_handler(hass: HomeAssistant, fn):
    async def handler(call: ServiceCall) -> None:
        manager: ScheduleManager | None = hass.data.get(DOMAIN)
        if manager is None:
            raise HomeAssistantError(
                "Climate Schedule is niet geladen. Voeg de integratie toe via Instellingen."
            )
        await manager.async_mutate(fn, **call.data)
    return handler


def _register_services(hass: HomeAssistant) -> None:
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
        hass.services.async_register(DOMAIN, name, _make_handler(hass, fn), schema=schema)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Services eenmalig registreren. Er is geen YAML-configuratie meer."""
    _register_services(hass)
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    store = Store(hass, STORAGE_VERSION, DOMAIN)
    data = await store.async_load()
    if data is None:
        data = await hass.async_add_executor_job(_load_seed)
        await store.async_save(data)
        _LOGGER.info("Climate Schedule: startdata uit seed.json geladen")
    data.setdefault("users", {})
    data.setdefault("defaults", {})
    # Veilig als standaard: bij een nieuwe installatie staat de testmodus aan.
    data.setdefault("test_mode", True)

    for err in r.validate(data):
        _LOGGER.warning("Climate Schedule datamodel: %s", err)

    climates = entry.options.get(CONF_CLIMATES, [])
    manager = ScheduleManager(hass, store, data, climates)
    hass.data[DOMAIN] = manager

    entry.async_on_unload(async_track_time_change(hass, manager.async_tick, second=0))
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await manager.async_apply_all(force=True)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data.pop(DOMAIN, None)
    return unloaded

# Bestand: custom_components/climate_schedule/const.py
# Versie: 0.0.3
"""Constanten, apart gezet zodat config_flow, sensor en __init__ elkaar niet importeren."""

DOMAIN = "climate_schedule"
VERSION = "0.0.3"
CONF_CLIMATES = "climates"
STORAGE_VERSION = 2
SIGNAL_UPDATE = f"{DOMAIN}_updated"

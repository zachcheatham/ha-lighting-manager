import logging

from homeassistant.core import HomeAssistant
from homeassistant.core_config import Config
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import DOMAIN as DOMAIN_SENSOR

from .const import DOMAIN
from .coordinator import LayerManagerCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [DOMAIN_SENSOR]

async def async_setup(hass: HomeAssistant, config: Config):
    return True


async def async_setup_entry(hass: HomeAssistant, config: ConfigEntry) -> bool:
    coordinator = LayerManagerCoordinator(hass, config)
    await coordinator.async_load_from_store()

    hass.data.setdefault(DOMAIN, {})[config.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(config, PLATFORMS)
    config.async_on_unload(config.add_update_listener(config_update_listener))

    await coordinator.async_setup_services()
    await coordinator.async_setup_listeners()
    await coordinator.async_initial_refresh()

    return True

async def async_unload_entry(hass: HomeAssistant, config: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(config, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(config.entry_id)
        await coordinator.async_unload()

    return unload_ok


async def config_update_listener(hass: HomeAssistant, config: ConfigEntry):
    coordinator = hass.data[DOMAIN][config.entry_id]
    await coordinator.async_options_updated()

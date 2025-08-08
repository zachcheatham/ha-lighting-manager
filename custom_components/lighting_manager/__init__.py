"""Lighting Manager integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_FORCE,
    ATTR_LOCKED,
    ATTR_RGB_COLOR,
    ATTR_SOURCE,
    ATTR_TRANSITION,
    CONF_ENTITIES,
    CONF_MAX_ELEVATION,
    CONF_MIN_ELEVATION,
    CONF_ZONE,
    DOMAIN,
    PLATFORMS,
    SERVICE_ACTIVATE_LAYER,
    SERVICE_DEACTIVATE_LAYER,
    SERVICE_UPDATE_LAYER,
)
from .manager import LightingManager
from .coordinator import ZoneCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up from YAML is not supported."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Lighting Manager from a config entry."""
    zone_id = entry.data[CONF_ZONE]
    lights = entry.data.get(CONF_ENTITIES, [])
    adaptive = {
        CONF_MIN_ELEVATION: entry.options.get(
            CONF_MIN_ELEVATION, entry.data.get(CONF_MIN_ELEVATION, 0)
        ),
        CONF_MAX_ELEVATION: entry.options.get(
            CONF_MAX_ELEVATION, entry.data.get(CONF_MAX_ELEVATION, 15)
        ),
    }
    manager = LightingManager(hass, zone_id, lights, adaptive)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "manager": manager,
    }

    coordinator = ZoneCoordinator(hass, manager, zone_id)
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id]["coordinator"] = coordinator

    async def _apply_state() -> None:
        data = coordinator.data
        if not data:
            return
        final = data.get("final_state")
        if not final:
            return
        service_data = {k: v for k, v in final.items() if v is not None}
        service_data["entity_id"] = lights
        await hass.services.async_call("light", "turn_on", service_data)

    coordinator.async_add_listener(_apply_state)

    async def handle_activate_layer(call: ServiceCall) -> None:
        entity = hass.data.get("layer").get_entity(call.data["entity_id"])
        if entity:
            kwargs = {
                k: call.data[k]
                for k in [
                    ATTR_BRIGHTNESS,
                    ATTR_COLOR_TEMP,
                    ATTR_RGB_COLOR,
                    ATTR_TRANSITION,
                    ATTR_SOURCE,
                    ATTR_FORCE,
                    ATTR_LOCKED,
                ]
                if k in call.data
            }
            await entity.async_activate(**kwargs)

    async def handle_deactivate_layer(call: ServiceCall) -> None:
        entity = hass.data.get("layer").get_entity(call.data["entity_id"])
        if entity:
            await entity.async_deactivate()

    async def handle_update_layer(call: ServiceCall) -> None:
        entity = hass.data.get("layer").get_entity(call.data["entity_id"])
        if entity:
            kwargs = {
                k: call.data[k]
                for k in [
                    ATTR_BRIGHTNESS,
                    ATTR_COLOR_TEMP,
                    ATTR_RGB_COLOR,
                    ATTR_TRANSITION,
                    ATTR_SOURCE,
                    ATTR_FORCE,
                    ATTR_LOCKED,
                ]
                if k in call.data
            }
            await entity.async_update_attributes(**kwargs)

    hass.services.async_register(
        DOMAIN, SERVICE_ACTIVATE_LAYER, handle_activate_layer
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DEACTIVATE_LAYER, handle_deactivate_layer
    )
    hass.services.async_register(
        DOMAIN, SERVICE_UPDATE_LAYER, handle_update_layer
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = hass.data[DOMAIN].pop(entry.entry_id)
    coordinator: ZoneCoordinator = data["coordinator"]
    await coordinator.async_shutdown()
    await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    return True

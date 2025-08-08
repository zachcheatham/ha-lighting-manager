"""Layer entity platform for Lighting Manager."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import RestoreEntity

from .const import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_CONDITIONS,
    ATTR_FORCE,
    ATTR_LAST_UPDATED,
    ATTR_LOCKED,
    ATTR_PRIORITY,
    ATTR_RGB_COLOR,
    ATTR_SOURCE,
    ATTR_TRANSITION,
    CONF_ZONE,
    DEFAULT_LAYERS,
)


class LayerEntity(RestoreEntity):
    """Representation of a single lighting layer."""

    _attr_should_poll = False

    def __init__(self, zone_id: str, layer_id: str, priority: int) -> None:
        self._zone_id = zone_id
        self._layer_id = layer_id
        self._priority = priority
        self._active = False
        self._data: dict[str, Any] = {
            ATTR_BRIGHTNESS: None,
            ATTR_COLOR_TEMP: None,
            ATTR_RGB_COLOR: None,
            ATTR_TRANSITION: None,
            ATTR_FORCE: False,
            ATTR_LOCKED: False,
            ATTR_CONDITIONS: {},
            ATTR_LAST_UPDATED: None,
            ATTR_SOURCE: None,
        }
        self._attr_unique_id = f"{zone_id}_{layer_id}"
        self._attr_name = f"{zone_id} {layer_id}".replace("_", " ")
        self.entity_id = f"layer.{zone_id}_{layer_id}"

    async def async_added_to_hass(self) -> None:
        if (state := await self.async_get_last_state()) is not None:
            self._active = state.state == "on"
            for key in self._data:
                if key in state.attributes:
                    self._data[key] = state.attributes[key]
        self.async_write_ha_state()

    @property
    def state(self) -> bool:
        return self._active

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = {**self._data}
        attrs[ATTR_PRIORITY] = self._priority
        return attrs

    async def async_activate(self, **kwargs) -> None:
        if self._data.get(ATTR_LOCKED):
            return
        self._active = True
        self._data.update(kwargs)
        self._data[ATTR_LAST_UPDATED] = datetime.utcnow().isoformat()
        self.async_write_ha_state()

    async def async_deactivate(self) -> None:
        if self._data.get(ATTR_LOCKED):
            return
        self._active = False
        self._data[ATTR_LAST_UPDATED] = datetime.utcnow().isoformat()
        self.async_write_ha_state()

    async def async_update_attributes(self, **kwargs) -> None:
        if self._data.get(ATTR_LOCKED):
            return
        self._data.update(kwargs)
        self._data[ATTR_LAST_UPDATED] = datetime.utcnow().isoformat()
        self.async_write_ha_state()


def _create_layers(zone_id: str) -> list[LayerEntity]:
    return [
        LayerEntity(zone_id, layer_id, priority)
        for layer_id, priority in DEFAULT_LAYERS.items()
    ]


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities
) -> None:
    """Set up layer entities for a zone."""
    zone_id = entry.data[CONF_ZONE]
    async_add_entities(_create_layers(zone_id))

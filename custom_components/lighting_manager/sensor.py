"""Sensors for Lighting Manager."""
from __future__ import annotations

from typing import Any, Mapping

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import ATTR_ELEVATION
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import (
    TrackStates,
    async_track_state_change_filtered,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_MAX_ELEVATION,
    CONF_MIN_ELEVATION,
    DOMAIN,
)

from .manager import LightingManager
from .coordinator import ZoneCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    manager: LightingManager = data["manager"]
    coordinator: ZoneCoordinator = data["coordinator"]
    async_add_entities(
        [AdaptiveLightFactorSensor(manager), ActiveLayerSensor(coordinator)]
    )


class AdaptiveLightFactorSensor(SensorEntity):
    _attr_should_poll = False
    _attr_name = "Adaptive Lighting Factor"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, manager: LightingManager) -> None:
        self._manager = manager
        self._current_factor = 0.0

    async def async_added_to_hass(self) -> None:
        self._recalculate(self.hass.states.get("sun.sun"))
        self.async_on_remove(
            async_track_state_change_filtered(
                self.hass,
                TrackStates(False, {"sun.sun"}, None),
                self._handle_event,
            )
        )

    @callback
    def _handle_event(self, event) -> None:
        self._recalculate(event.data.get("new_state"))

    @callback
    def _recalculate(self, state) -> None:
        if state is None:
            return
        elevation = state.attributes.get(ATTR_ELEVATION, 0)
        min_el = self._manager.adaptive.get(CONF_MIN_ELEVATION, 0)
        max_el = self._manager.adaptive.get(CONF_MAX_ELEVATION, 15)
        span = max_el - min_el or 1
        clamped = min(max(elevation, min_el), max_el)
        self._current_factor = 1.0 - ((clamped - min_el) / span)
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        return round(self._current_factor, 3)

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        return self._manager.adaptive


class ActiveLayerSensor(CoordinatorEntity, SensorEntity):
    _attr_should_poll = False
    _attr_name = "Active Layers"

    def __init__(self, coordinator: ZoneCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator._zone_id}_layers"

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.get("active_layers", []))

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        return {
            "layers": self.coordinator.data.get("active_layers", []),
            "winning_layer": self.coordinator.data.get("winning_layer"),
        }

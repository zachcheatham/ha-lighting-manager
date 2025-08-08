"""Zone coordinator for Lighting Manager."""
from __future__ import annotations

from typing import Any
import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DEFAULT_LAYERS

_LOGGER = logging.getLogger(__name__)


class ZoneCoordinator(DataUpdateCoordinator):
    """Coordinate calculations for a zone."""

    def __init__(self, hass: HomeAssistant, manager, zone_id: str) -> None:
        super().__init__(hass, _LOGGER, name=f"{zone_id} coordinator")
        self._manager = manager
        self._zone_id = zone_id
        self._layer_ids = [
            f"layer.{zone_id}_{lid}" for lid in DEFAULT_LAYERS
        ]
        self._unsub = None
        self._scheduled = False

    async def async_config_entry_first_refresh(self) -> None:
        self._unsub = async_track_state_change_event(
            self.hass, self._layer_ids, self._handle_layer_event
        )
        await super().async_config_entry_first_refresh()

    @callback
    def _handle_layer_event(self, event) -> None:
        if not self._scheduled:
            self._scheduled = True
            async_call_later(self.hass, 0.1, self._scheduled_refresh)

    async def _scheduled_refresh(self, _now) -> None:
        self._scheduled = False
        await self.async_request_refresh()

    async def _async_update_data(self) -> dict[str, Any]:
        return self._manager.calculate_zone_state()

    async def async_shutdown(self) -> None:
        if self._unsub:
            self._unsub()



from typing import Any, Dict
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_DATA_UPDATE
from .coordinator import LayerManagerCoordinator

async def async_setup_entry(
        hass: HomeAssistant,
        config: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:

    coordinator = hass.data[DOMAIN][config.entry_id]
    async_add_entities([LayerStatusSensor(coordinator)])


class LayerStatusSensor(SensorEntity):

    _attr_should_poll: bool = False
    _attr_name: str = "Layer Manager Status"
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, coordinator: LayerManagerCoordinator):
        self.coordinator: LayerManagerCoordinator = coordinator
        self._attr_unique_id = f"{coordinator.config.entry_id}_status"
        self._attr_native_value: int = 0
        self._attr_extra_state_attributes: Dict[str, Any] = {}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_DATA_UPDATE, self._handle_update
            )
        )

        self._handle_update()

    @callback
    def _handle_update(self) -> None:
        info = self.coordinator.get_summary()
        self._attr_native_value = len(info.get("layers", []))
        self._attr_extra_state_attributes = info
        self.async_write_ha_state()

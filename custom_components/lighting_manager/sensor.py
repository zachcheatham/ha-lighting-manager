from homeassistant.core import Event, State
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.components.sun import STATE_ATTR_ELEVATION
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_track_state_change_filtered, TrackStates
from . import ATTR_PRIORITY, CONF_ACTIVE_LAYER_ENTITY, DATA_ENTITIES, DATA_STATES, SIGNAL_LAYER_UPDATE
import logging

DOMAIN = "lighting_manager"

_LOGGER = logging.getLogger(__name__)


def setup_platform(hass, config, add_entities, discovery_info=None):
    add_entities(
        [
            ActiveLayerSensor(
                entity_id, hass.data[DOMAIN][DATA_STATES][entity_id])
            for entity_id in hass.data[DOMAIN][DATA_ENTITIES].keys()
            if (hass.data[DOMAIN][DATA_ENTITIES][entity_id] is not None and hass.data[DOMAIN][DATA_ENTITIES][entity_id][CONF_ACTIVE_LAYER_ENTITY])
        ]
    )

    add_entities([AdaptiveColorTempSensor()])


class ActiveLayerSensor(SensorEntity):

    def __init__(self, light_entity_id: str, layer_data: dict):
        self._attr_name = light_entity_id + " Active Layer"
        self._attr_should_poll = False
        self._layers = layer_data
        self._light_entity_id = light_entity_id

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_LAYER_UPDATE}-{self._light_entity_id}",
                self.schedule_update_ha_state
            )
        )

    @property
    def native_value(self) -> str:
        active_layer = None
        for layer in self._layers:
            if (
                active_layer is None
                or self._layers[layer][ATTR_PRIORITY] > self._layers[active_layer][ATTR_PRIORITY]
            ):
                active_layer = layer

        if active_layer is None:
            return "None"
        else:
            return active_layer


class AdaptiveColorTempSensor(SensorEntity):

    _attr_should_poll: bool = False
    _attr_name: str = "Adaptive Color Temp"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _min_temp = 153
    _max_temp = 500
    _min_elevation = 0
    _max_elevation = 15

    _current_temp: int = _max_temp

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_track_state_change_filtered(
                self.hass,
                TrackStates(False, set(["sun.sun"]), None),
                self.recalculate_temp
            )
        )

    def recalculate_temp(self, event: Event) -> None:
        state: State = event.data.get("new_state")
        elevation = state.attributes[STATE_ATTR_ELEVATION]

        pct: float = 1.0 - (min(max(elevation, 0), 15) / 15.0)

        self._current_temp = int(((self._max_temp - self._min_temp) * pct) + self._min_temp)

        _LOGGER.info("Current temp is now %d", self._current_temp)

        self.schedule_update_ha_state

    @property
    def native_value(self) -> int:
        return self._current_temp


from typing import Any, Mapping
from homeassistant.core import Event, State
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_track_state_change_filtered, TrackStates
from . import ATTR_PRIORITY, CONF_ACTIVE_LAYER_ENTITY, CONF_MIN_ELEVATION, CONF_MAX_ELEVATION, DATA_ENTITIES, DATA_STATES, SIGNAL_LAYER_UPDATE, CONF_ADAPTIVE
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

    add_entities([AdaptiveLightFactorSensor()])


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


class AdaptiveLightFactorSensor(SensorEntity):

    _attr_should_poll: bool = False
    _attr_name: str = "Adaptive Lighting Factor"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _min_elevation = 0
    _max_elevation = 15

    _current_factor: int = 0

    async def async_added_to_hass(self) -> None:

        self.recalculate(self.hass.states.get("sun.sun"))

        self.async_on_remove(
            async_track_state_change_filtered(
                self.hass,
                TrackStates(False, set(["sun.sun"]), None),
                self.recalculate_from_event
            )
        )

    def recalculate(self, state: State) -> None:
        elevation = state.attributes["elevation"] # TODO IMPORT ATTR CONST

        self._current_factor = 1.0 - (float(min(max(elevation, self.hass.data[DOMAIN][CONF_ADAPTIVE][CONF_MIN_ELEVATION]),
                                                self.hass.data[DOMAIN][CONF_ADAPTIVE][CONF_MAX_ELEVATION])) / float(self.hass.data[DOMAIN][CONF_ADAPTIVE][CONF_MAX_ELEVATION]))

        self.schedule_update_ha_state()

    def recalculate_from_event(self, event: Event) -> None:
        self.recalculate(event.data.get("new_state"))

    @property
    def native_value(self) -> int:
        return self._current_factor

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        return self.hass.data[DOMAIN][CONF_ADAPTIVE]

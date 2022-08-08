from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from . import ATTR_PRIORITY, CONF_ACTIVE_LAYER_ENTITY, DATA_ENTITIES, DATA_STATES, SIGNAL_LAYER_UPDATE
import logging

DOMAIN="lighting_manager"

_LOGGER = logging.getLogger(__name__)

def setup_platform(hass, config, add_entities, discovery_info=None):
    add_entities(
        [
            ActiveLayerSensor(entity_id, hass.data[DOMAIN][DATA_STATES][entity_id])
            for entity_id in hass.data[DOMAIN][DATA_ENTITIES].keys()
            if (hass.data[DOMAIN][DATA_ENTITIES][entity_id] is not None and hass.data[DOMAIN][DATA_ENTITIES][entity_id][CONF_ACTIVE_LAYER_ENTITY])
        ]
    )

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
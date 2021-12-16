from typing import List
from homeassistant.const import ATTR_ENTITY_ID, ATTR_STATE, CONF_ENTITIES, STATE_OFF
from homeassistant.components.light import (
    ATTR_COLOR_MODE,
    ATTR_BRIGHTNESS,
    ATTR_BRIGHTNESS_PCT,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    ATTR_RGBW_COLOR,
    ATTR_RGBWW_COLOR,
    ATTR_COLOR_TEMP,
    ATTR_EFFECT,
    ATTR_KELVIN,
    ATTR_WHITE,
    ATTR_WHITE_VALUE,
    ATTR_XY_COLOR,
    ATTR_FLASH,
    LIGHT_TURN_ON_SCHEMA
)
from homeassistant.components.light import DOMAIN as DOMAIN_LIGHT
from homeassistant.core import Config, HomeAssistant, ServiceCall, State, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.state import async_reproduce_state
import logging
import voluptuous as vol
from homeassistant.components.scene import DOMAIN

_LOGGER = logging.getLogger(__name__)

DOMAIN = "lighting_manager"
DATA_ENTITIES = "lm_entities"
DATA_STATES = "lm_states"
DATA_EVENT_LISTENER = "event_listener"
DATA_HA_SCENE = "homeassistant_scene"

SERVICE_INSERT_SCENE = "insert_scene"
SERVICE_INSERT_STATE = "insert_state"
SERVICE_REMOVE_SCENE = "remove_scene"
SERVICE_REMOVE_STATE = "remove_state"

ATTR_PRIORITY = "priority"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_ENTITIES): vol.All(cv.ensure_list, [cv.string]),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

SUPPORTED_LIGHT_ATTRS = [
    ATTR_COLOR_MODE,
    ATTR_BRIGHTNESS,
    ATTR_BRIGHTNESS_PCT,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    ATTR_RGBW_COLOR,
    ATTR_RGBWW_COLOR,
    ATTR_COLOR_TEMP,
    ATTR_EFFECT,
    ATTR_KELVIN,
    ATTR_WHITE,
    ATTR_WHITE_VALUE,
    ATTR_XY_COLOR,
    ATTR_FLASH,
]

SERVICE_INSERT_SCENE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.string,
        vol.Required(ATTR_PRIORITY): cv.positive_int,
    }
)

SERVICE_REMOVE_SCENE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.string,
    }
)

def setup(hass: HomeAssistant, config: Config):

    conf = config[DOMAIN]

    hass.data[DOMAIN] = {}
    hass.data[DOMAIN][DATA_ENTITIES] = conf[CONF_ENTITIES]
    hass.data[DOMAIN][DATA_STATES] = {}

    for entity_id in conf[CONF_ENTITIES]:
        hass.data[DOMAIN][DATA_STATES][entity_id] = {}

    def on_state_change(event):
        state = event.data.get("new_state")
        if (
            state.entity_id.split(".")[0] == DOMAIN_LIGHT
            and state.entity_id in hass.data[DOMAIN][DATA_ENTITIES]
        ):
            _LOGGER.info(state)

    # hass.data[DOMAIN][DATA_EVENT_LISTENER] = hass.bus.async_listen(EVENT_STATE_CHANGED, on_state_change)

    def render_light(entity_id: str):

        if len(hass.data[DOMAIN][DATA_STATES][entity_id]) == 0:
            return State(entity_id, STATE_OFF)
        else:
            active_state = None
            for layer in hass.data[DOMAIN][DATA_STATES][entity_id]:
                if active_state == None or hass.data[DOMAIN][DATA_STATES][entity_id][layer][ATTR_PRIORITY] > active_state[ATTR_PRIORITY]:
                    active_state = hass.data[DOMAIN][DATA_STATES][entity_id][layer]

            return active_state[ATTR_STATE]


    async def apply_lights(entities: List, additional_states: List):
        states=additional_states
        for entity_id in entities:
            states.append(render_light(entity_id))

        await async_reproduce_state(hass, states)

    @callback
    async def insert_scene(call: ServiceCall):
        scene_entity_id = call.data.get(ATTR_ENTITY_ID)
        priority = call.data.get(ATTR_PRIORITY)
        entity_states = (
            hass.data[DATA_HA_SCENE].entities[scene_entity_id].scene_config.states
        )

        non_managed_entities=[]
        affected_entities=[]

        for entity_id in entity_states:
            if entity_id in hass.data[DOMAIN][DATA_STATES]:
                hass.data[DOMAIN][DATA_STATES][entity_id][scene_entity_id] = {
                    ATTR_PRIORITY: priority,
                    ATTR_STATE: entity_states[entity_id],
                }
                affected_entities.append(entity_id)
            else:
                non_managed_entities.append(entity_states[entity_id])
                
        await apply_lights(affected_entities, non_managed_entities)

    hass.services.register(
        DOMAIN, SERVICE_INSERT_SCENE, insert_scene, SERVICE_INSERT_SCENE_SCHEMA
    )

    @callback
    async def remove_scene(call: ServiceCall):
        scene_entity_id = call.data.get(ATTR_ENTITY_ID)

        affected_entities=[]
        for entity_id in hass.data[DOMAIN][DATA_STATES]:
            if scene_entity_id in hass.data[DOMAIN][DATA_STATES][entity_id]:
                hass.data[DOMAIN][DATA_STATES][entity_id].pop(scene_entity_id)
                affected_entities.append(entity_id)

        await apply_lights(affected_entities, [])

    hass.services.register(
        DOMAIN, SERVICE_REMOVE_SCENE, remove_scene, SERVICE_REMOVE_SCENE_SCHEMA
    )

    return True
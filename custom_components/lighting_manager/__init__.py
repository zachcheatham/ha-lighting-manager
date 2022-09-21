from typing import List
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_ID,
    ATTR_STATE,
    CONF_ENTITIES,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN
)

from homeassistant import core as ha
from homeassistant.core import Config, Context, Event, HomeAssistant, ServiceCall, State, callback
from homeassistant.components.group import DOMAIN as DOMAIN_GROUP
from homeassistant.components.sensor import DOMAIN as DOMAIN_SENSOR
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_filtered, TrackStates
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.state import async_reproduce_state
import logging
import voluptuous as vol

_LOGGER = logging.getLogger(__name__)

DOMAIN = "lighting_manager"
DATA_ENTITIES = "lm_entities"
DATA_STATES = "lm_states"
DATA_EVENT_LISTENER = "event_listener"
DATA_HA_SCENE = "homeassistant_scene"
DATA_CONF = "conf"

SERVICE_INSERT_SCENE = "insert_scene"
SERVICE_INSERT_STATE = "insert_state"
SERVICE_REMOVE_LAYER = "remove_layer"
SERVICE_REFRESH_ALL = "refresh_all"

ATTR_PRIORITY = "priority"
ATTR_ATTRIBUTES = "attributes"
ATTR_CLEAR_LAYER = "clear_layer"

CONF_ACTIVE_LAYER_ENTITY = "active_layer_entity"

SIGNAL_LAYER_UPDATE=f"{DOMAIN}-update"

ENTITY_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ACTIVE_LAYER_ENTITY, default=False): cv.boolean,
    }
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_ENTITIES): {cv.entity_id: vol.Any(None, ENTITY_SCHEMA)},
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

# SUPPORTED_LIGHT_ATTRS = [
#     ATTR_COLOR_MODE,
#     ATTR_BRIGHTNESS,
#     ATTR_BRIGHTNESS_PCT,
#     ATTR_HS_COLOR,
#     ATTR_RGB_COLOR,
#     ATTR_RGBW_COLOR,
#     ATTR_RGBWW_COLOR,
#     ATTR_COLOR_TEMP,
#     ATTR_EFFECT,
#     ATTR_KELVIN,
#     ATTR_WHITE,
#     ATTR_WHITE_VALUE,
#     ATTR_XY_COLOR,
#     ATTR_FLASH,
# ]

SERVICE_INSERT_SCENE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.string,
        vol.Required(ATTR_ID): cv.string,
        vol.Required(ATTR_PRIORITY): cv.positive_int,
        vol.Optional(ATTR_CLEAR_LAYER): cv.boolean
    }
)

SERVICE_INSERT_STATE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.string,
        vol.Required(ATTR_PRIORITY): cv.positive_int,
        vol.Required(ATTR_ID): cv.string,
        vol.Optional(ATTR_STATE): cv.string,
        vol.Optional(ATTR_ATTRIBUTES): dict,
        vol.Optional(ATTR_CLEAR_LAYER): cv.boolean
    }
)

SERVICE_REMOVE_LAYER_SCHEMA = vol.Schema(
    {vol.Optional(ATTR_ENTITY_ID): cv.string, vol.Required(ATTR_ID): cv.string}
)


def setup(hass: HomeAssistant, config: Config):

    conf = config[DOMAIN]

    hass.data[DOMAIN] = {}
    hass.data[DOMAIN][DATA_ENTITIES] = conf[CONF_ENTITIES]
    hass.data[DOMAIN][DATA_STATES] = {}

    for entity_id in conf[CONF_ENTITIES].keys():
        hass.data[DOMAIN][DATA_STATES][entity_id] = {}

    def render_entity(entity_id: str):

        if len(hass.data[DOMAIN][DATA_STATES][entity_id]) == 0:
            #domain = ha.split_entity_id(entity_id)[0]
            #if domain == "light" or domain == "group":
            return State(entity_id, STATE_OFF)
            #else:
            #    return 
        else:
            active_state = None
            for layer in hass.data[DOMAIN][DATA_STATES][entity_id]:
                if (
                    active_state == None
                    or hass.data[DOMAIN][DATA_STATES][entity_id][layer][ATTR_PRIORITY]
                    > active_state[ATTR_PRIORITY]
                ):
                    active_state = hass.data[DOMAIN][DATA_STATES][entity_id][layer]

            return active_state[ATTR_STATE]

    async def apply_entities(entities: List, additional_states: List, context: Context):
        states = additional_states
        for entity_id in entities:
            states.append(render_entity(entity_id))

        await async_reproduce_state(hass, states, context=context)

        for entity_id in entities:
            async_dispatcher_send(hass, f"{SIGNAL_LAYER_UPDATE}-{entity_id}")

    def clear_layer(layer_id: str):
        affected_entities = [
            light_entity_id
            for light_entity_id in hass.data[DOMAIN][DATA_ENTITIES]
            if layer_id in hass.data[DOMAIN][DATA_STATES][light_entity_id]
        ]

        for light_entity_id in affected_entities:
            hass.data[DOMAIN][DATA_STATES][light_entity_id].pop(layer_id)

        return affected_entities

    @callback
    async def insert_scene(call: ServiceCall):
        scene_entity_id = call.data.get(ATTR_ENTITY_ID)
        layer_id = call.data.get(ATTR_ID)
        priority = call.data.get(ATTR_PRIORITY)
        should_clear = call.data.get(ATTR_CLEAR_LAYER)
        entity_states = (
            hass.data[DATA_HA_SCENE].entities[scene_entity_id].scene_config.states
        )

        ungrouped_entity_states = {}

        # Split out groups
        for entity_id in entity_states:
            if ha.split_entity_id(entity_id)[0] == DOMAIN_GROUP:
                for group_entity in hass.components.group.get_entity_ids(entity_id):
                    ungrouped_entity_states[group_entity] = entity_states[entity_id]
            else:
                ungrouped_entity_states[entity_id] = entity_states[entity_id]

        del(entity_states)

        non_managed_entities = []
        affected_entities = None

        if should_clear:
            affected_entities = clear_layer(layer_id)
        else:
            affected_entities = []

        for entity_id in ungrouped_entity_states:

            if entity_id in hass.data[DOMAIN][DATA_STATES]:
                hass.data[DOMAIN][DATA_STATES][entity_id][layer_id] = {
                    ATTR_PRIORITY: priority,
                    ATTR_STATE: ungrouped_entity_states[entity_id],
                }
                affected_entities.append(entity_id)
            else:
                non_managed_entities.append(ungrouped_entity_states[entity_id])

        await apply_entities(affected_entities, non_managed_entities, call.context)

    hass.services.register(
        DOMAIN, SERVICE_INSERT_SCENE, insert_scene, SERVICE_INSERT_SCENE_SCHEMA
    )

    @callback
    async def insert_state(call: ServiceCall):
        entity_id = call.data.get(ATTR_ENTITY_ID)
        priority = call.data.get(ATTR_PRIORITY)
        layer_id = call.data.get(ATTR_ID)
        state = call.data.get(ATTR_STATE, STATE_ON)
        attributes = call.data.get(ATTR_ATTRIBUTES, {})
        should_clear = call.data.get(ATTR_CLEAR_LAYER)

        affected_clear_entities = None
        affected_entities = []
        extra_entities = []

        if should_clear:
            affected_clear_entities = clear_layer(layer_id)

        if ha.split_entity_id(entity_id)[0] == DOMAIN_GROUP:
            for entity in hass.components.group.get_entity_ids(entity_id):
                if entity in hass.data[DOMAIN][DATA_ENTITIES]:
                    affected_entities.append(entity)
                else:
                    extra_entities.append(entity)
        elif entity_id in hass.data[DOMAIN][DATA_ENTITIES]:
            affected_entities.append(entity_id)

        for entity in affected_entities:
            hass.data[DOMAIN][DATA_STATES][entity][layer_id] = {
                ATTR_PRIORITY: priority,
                ATTR_STATE: State(entity_id, state, attributes),
            }

        extra_states = [
            State(extra_entity_id, state, attributes)
            for extra_entity_id in extra_entities
        ]

        if should_clear:
            affected_entities = list(set(affected_entities + affected_clear_entities))

        if len(affected_entities) > 0 or len(extra_states) > 0:
            await apply_entities(affected_entities, extra_states, call.context)

    hass.services.register(
        DOMAIN, SERVICE_INSERT_STATE, insert_state, SERVICE_INSERT_STATE_SCHEMA
    )

    @callback
    async def remove_layer(call: ServiceCall):
        entity_id = call.data.get(ATTR_ENTITY_ID)
        layer_id = call.data.get(ATTR_ID)

        affected_entities = []

        if entity_id:
            if ha.split_entity_id(entity_id)[0] == DOMAIN_GROUP:
                for light_entity in hass.components.group.get_entity_ids(entity_id):
                    if (
                        light_entity in hass.data[DOMAIN][DATA_ENTITIES]
                        and layer_id in hass.data[DOMAIN][DATA_STATES][light_entity]
                    ):
                        affected_entities.append(light_entity)
            elif (
                entity_id in hass.data[DOMAIN][DATA_ENTITIES]
                and layer_id in hass.data[DOMAIN][DATA_STATES][entity_id]
            ):
                affected_entities.append(entity_id)
        else:
            for light_entity_id in hass.data[DOMAIN][DATA_ENTITIES]:
                if layer_id in hass.data[DOMAIN][DATA_STATES][light_entity_id]:
                    affected_entities.append(light_entity_id)

        for light_entity_id in affected_entities:
            hass.data[DOMAIN][DATA_STATES][light_entity_id].pop(layer_id)

        if len(affected_entities) > 0:
            await apply_entities(affected_entities, [], call.context)

    hass.services.register(
        DOMAIN, SERVICE_REMOVE_LAYER, remove_layer, SERVICE_REMOVE_LAYER_SCHEMA
    )

    @callback
    async def refresh_all(call: ServiceCall):
        await apply_entities(hass.data[DOMAIN][DATA_ENTITIES], [], call.context)

    hass.services.register(
        DOMAIN, SERVICE_REFRESH_ALL, refresh_all
    )

    @callback
    async def on_state_change_event(event: Event) -> None:

        old_state: State = event.data.get("old_state")
        new_state: State = event.data.get("new_state")

        if new_state and (not old_state or old_state.state == STATE_UNAVAILABLE or old_state.state == STATE_UNKNOWN) and new_state.state != STATE_UNAVAILABLE and new_state.state != STATE_UNKNOWN:
            _LOGGER.warn("Restoring state of %s...", event.data[ATTR_ENTITY_ID])
            await apply_entities([event.data[ATTR_ENTITY_ID]], [], event.context)

    async_track_state_change_filtered(hass, TrackStates(False, hass.data[DOMAIN][DATA_ENTITIES], None), on_state_change_event)

    hass.helpers.discovery.load_platform(DOMAIN_SENSOR, DOMAIN, {}, config)

    return True

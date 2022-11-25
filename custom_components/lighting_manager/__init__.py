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
from homeassistant.components.light import DOMAIN as DOMAIN_LIGHT, ATTR_COLOR_TEMP, ATTR_COLOR_MODE, COLOR_MODE_COLOR_TEMP, ATTR_BRIGHTNESS
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
DATA_ADAPTIVE_ENTITIES = "adaptive_entities"

SERVICE_INSERT_SCENE = "insert_scene"
SERVICE_INSERT_STATE = "insert_state"
SERVICE_REMOVE_LAYER = "remove_layer"
SERVICE_REFRESH_ALL = "refresh_all"
SERVICE_REFRESH = "refresh"
SERVICE_ADD_ADAPTIVE = "add_adaptive"
SERVICE_REMOVE_ADAPTIVE = "remove_adaptive"

ATTR_PRIORITY = "priority"
ATTR_ATTRIBUTES = "attributes"
ATTR_CLEAR_LAYER = "clear_layer"

CONF_ACTIVE_LAYER_ENTITY = "active_layer_entity"
CONF_ADAPTIVE = "adaptive"
CONF_MAX_TEMP = "max_temp"
CONF_MIN_TEMP = "min_temp"
CONF_MAX_BRIGHTNESS = "max_brightness"
CONF_MIN_BRIGHTNESS = "min_brightness"

CONF_MAX_ELEVATION = "max_elevation"
CONF_MIN_ELEVATION = "min_elevation"

SIGNAL_LAYER_UPDATE = f"{DOMAIN}-update"

ENTITY_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ACTIVE_LAYER_ENTITY, default=False): cv.boolean,
        vol.Optional(CONF_ADAPTIVE, default={CONF_MAX_TEMP: 500, CONF_MIN_TEMP: 153, CONF_MIN_BRIGHTNESS: 155, CONF_MAX_BRIGHTNESS: 255}): vol.Schema(
            {
                vol.Optional(CONF_MAX_TEMP, default=500): cv.positive_int,
                vol.Optional(CONF_MIN_TEMP, default=153): cv.positive_int,
                vol.Optional(CONF_MAX_BRIGHTNESS, default=255): cv.positive_int,
                vol.Optional(CONF_MIN_BRIGHTNESS, default=150): cv.positive_int
            }
        )
    }
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_ENTITIES): {cv.entity_id: vol.Any(None, ENTITY_SCHEMA)},
                vol.Optional(CONF_ADAPTIVE, default={CONF_MIN_ELEVATION: 0, CONF_MAX_ELEVATION: 15}): vol.Schema(
                    {
                        vol.Optional(CONF_MIN_ELEVATION, default=0): cv.positive_int,
                        vol.Optional(CONF_MAX_ELEVATION, default=15): cv.positive_int
                    }
                )
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

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

SERVICE_REFRESH_SCHEMA = vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.string})

SERVICE_ADD_ADAPTIVE_SCHEMA = vol.Schema(
    {vol.Required(ATTR_ENTITY_ID): cv.string})

SERVICE_REMOVE_ADAPTIVE_SCHEMA = vol.Schema(
    {vol.Required(ATTR_ENTITY_ID): cv.string})


def setup(hass: HomeAssistant, config: Config):

    conf = config[DOMAIN]

    hass.data[DOMAIN] = {}
    hass.data[DOMAIN][DATA_ENTITIES] = conf[CONF_ENTITIES]
    hass.data[DOMAIN][DATA_ADAPTIVE_ENTITIES] = {}
    hass.data[DOMAIN][DATA_STATES] = {}
    hass.data[DOMAIN][CONF_ADAPTIVE] = conf[CONF_ADAPTIVE]

    for entity_id in conf[CONF_ENTITIES].keys():
        hass.data[DOMAIN][DATA_STATES][entity_id] = {}

    def render_entity(entity_id: str):
        if len(hass.data[DOMAIN][DATA_STATES][entity_id]) == 0:
            if entity_id in hass.data[DOMAIN][DATA_ADAPTIVE_ENTITIES]:
                remove_entities_from_adaptive_track([entity_id])

            return State(entity_id, STATE_OFF)
        else:
            active_state = None
            for layer in hass.data[DOMAIN][DATA_STATES][entity_id]:
                if (
                    active_state == None
                    or hass.data[DOMAIN][DATA_STATES][entity_id][layer][ATTR_PRIORITY]
                    > active_state[ATTR_PRIORITY]
                ):
                    active_state = hass.data[DOMAIN][DATA_STATES][entity_id][layer]

            if (ha.split_entity_id(entity_id)[0] == DOMAIN_LIGHT and
                ((ATTR_COLOR_TEMP in active_state[ATTR_STATE].attributes and
                    active_state[ATTR_STATE].attributes[ATTR_COLOR_TEMP] == CONF_ADAPTIVE) or
                ATTR_BRIGHTNESS in active_state[ATTR_STATE].attributes and
                    active_state[ATTR_STATE].attributes[ATTR_BRIGHTNESS] == CONF_ADAPTIVE)):

                adaptive_factor: float = float(hass.states.get(
                    "sensor.adaptive_lighting_factor").state)

                # Need to recreate state thanks to the read-only attributes included in the state...
                new_attributes = dict(active_state[ATTR_STATE].attributes)
                adaptive_track: dict = {ATTR_ENTITY_ID: entity_id}

                if ATTR_COLOR_TEMP in active_state[ATTR_STATE].attributes and active_state[ATTR_STATE].attributes[ATTR_COLOR_TEMP] == CONF_ADAPTIVE:
                    min_temp = hass.data[DOMAIN][DATA_ENTITIES][entity_id][CONF_ADAPTIVE][CONF_MIN_TEMP]
                    max_temp = hass.data[DOMAIN][DATA_ENTITIES][entity_id][CONF_ADAPTIVE][CONF_MAX_TEMP]

                    new_attributes[ATTR_COLOR_TEMP] = int(
                        ((max_temp - min_temp) * adaptive_factor) + min_temp)
                    new_attributes[ATTR_COLOR_MODE] = COLOR_MODE_COLOR_TEMP
                    adaptive_track[ATTR_COLOR_TEMP] = True

                if ATTR_BRIGHTNESS in active_state[ATTR_STATE].attributes and active_state[ATTR_STATE].attributes[ATTR_BRIGHTNESS] == CONF_ADAPTIVE:
                    min_brightness = hass.data[DOMAIN][DATA_ENTITIES][entity_id][CONF_ADAPTIVE][CONF_MIN_BRIGHTNESS]
                    max_brightness = hass.data[DOMAIN][DATA_ENTITIES][entity_id][CONF_ADAPTIVE][CONF_MAX_BRIGHTNESS]

                    new_attributes[ATTR_BRIGHTNESS] = int(
                        max_brightness - ((max_brightness - min_brightness) * adaptive_factor))
                    adaptive_track[ATTR_BRIGHTNESS] = True

                if not entity_id in hass.data[DOMAIN][DATA_ADAPTIVE_ENTITIES]:
                    add_entities_to_adaptive_track([adaptive_track])

                return State(entity_id, active_state[ATTR_STATE].state, new_attributes)
            else:
                if entity_id in hass.data[DOMAIN][DATA_ADAPTIVE_ENTITIES]:
                    remove_entities_from_adaptive_track([entity_id])

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

        del (entity_states)

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
                if not entity_id in affected_entities:
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
            affected_entities = list(
                set(affected_entities + affected_clear_entities))

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
    async def refresh(call: ServiceCall):
        entity_id = call.data.get(ATTR_ENTITY_ID)
        if ha.split_entity_id(entity_id)[0] == DOMAIN_GROUP:
            await apply_entities([
                group_entity
                for group_entity in hass.components.group.get_entity_ids(entity_id)
                if group_entity in hass.data[DOMAIN][DATA_ENTITIES]
            ], [], call.context)
        else:
            await apply_entities([entity_id], [], call.context)

    hass.services.register(DOMAIN, SERVICE_REFRESH,
                           refresh, SERVICE_REFRESH_SCHEMA)

    @callback
    async def on_state_change_event(event: Event) -> None:

        old_state: State = event.data.get("old_state")
        new_state: State = event.data.get("new_state")

        if new_state and (not old_state or old_state.state == STATE_UNAVAILABLE or old_state.state == STATE_UNKNOWN) and new_state.state != STATE_UNAVAILABLE and new_state.state != STATE_UNKNOWN:
            _LOGGER.warn("Restoring state of %s...",
                         event.data[ATTR_ENTITY_ID])
            await apply_entities([event.data[ATTR_ENTITY_ID]], [], event.context)

    async_track_state_change_filtered(hass, TrackStates(
        False, hass.data[DOMAIN][DATA_ENTITIES], None), on_state_change_event)

    @callback
    async def on_adaptive_factor_change(event: Event) -> None:
        new_state: State = event.data.get("new_state")
        old_state: State = event.data.get("old_state")

        adaptive_factor: float = float(hass.states.get(
            "sensor.adaptive_lighting_factor").state)

        if new_state and old_state and new_state.state != old_state.state:
            await update_adaptive(
                hass.data[DOMAIN][DATA_ADAPTIVE_ENTITIES].values(), event.context, adaptive_factor)

    async_track_state_change_filtered(hass, TrackStates(
        False, ["sensor.adaptive_lighting_factor"], None), on_adaptive_factor_change)

    @callback
    async def on_adaptive_light_change_event(event: Event) -> None:
        old_state: State = event.data.get("old_state")
        new_state: State = event.data.get("new_state")

        if old_state.state != new_state.state and new_state.state == STATE_OFF:
            remove_entities_from_adaptive_track(
                [event.data.get(ATTR_ENTITY_ID)])

    adaptive_track_states = async_track_state_change_filtered(hass, TrackStates(
        False, set(hass.data[DOMAIN][DATA_ADAPTIVE_ENTITIES]), None), on_adaptive_light_change_event)

    def add_entities_to_adaptive_track(entities: List[dict]) -> None:
        for entity in entities:
            _LOGGER.debug(
                f"Adding {entity[ATTR_ENTITY_ID]} to tracking.", )
            hass.data[DOMAIN][DATA_ADAPTIVE_ENTITIES][entity[ATTR_ENTITY_ID]] = entity

        adaptive_track_states.async_update_listeners(TrackStates(
            False, set(hass.data[DOMAIN][DATA_ADAPTIVE_ENTITIES].keys()), None))

    def remove_entities_from_adaptive_track(entity_ids: List[str]) -> None:
        for entity_id in entity_ids:
            if entity_id in hass.data[DOMAIN][DATA_ADAPTIVE_ENTITIES]:
                del hass.data[DOMAIN][DATA_ADAPTIVE_ENTITIES][entity_id]

        adaptive_track_states.async_update_listeners(TrackStates(
            False, set(hass.data[DOMAIN][DATA_ADAPTIVE_ENTITIES].keys()), None))

    async def update_adaptive(entities: List[dict], context: Context, factor: float = None) -> None:
        if not factor:
            factor = float(hass.states.get(
                "sensor.adaptive_lighting_factor").state)

        states = []

        for entity in entities:
            attrs = {}
            if ATTR_COLOR_TEMP in entity and entity[ATTR_COLOR_TEMP]:
                min_temp = hass.data[DOMAIN][DATA_ENTITIES][entity[ATTR_ENTITY_ID]][CONF_ADAPTIVE][CONF_MIN_TEMP]
                max_temp = hass.data[DOMAIN][DATA_ENTITIES][entity[ATTR_ENTITY_ID]][CONF_ADAPTIVE][CONF_MAX_TEMP]
                attrs[ATTR_COLOR_TEMP] = int(
                    ((max_temp - min_temp) * factor) + min_temp)
                attrs[ATTR_COLOR_MODE] = COLOR_MODE_COLOR_TEMP

                _LOGGER.debug(
                    f"Updating color temperature of {entity[ATTR_ENTITY_ID]} to {attrs[ATTR_COLOR_TEMP]}.", )

            if ATTR_BRIGHTNESS in entity and entity[ATTR_BRIGHTNESS]:
                min_brightness = hass.data[DOMAIN][DATA_ENTITIES][entity[ATTR_ENTITY_ID]][CONF_ADAPTIVE][CONF_MIN_BRIGHTNESS]
                max_brightness = hass.data[DOMAIN][DATA_ENTITIES][entity[ATTR_ENTITY_ID]][CONF_ADAPTIVE][CONF_MAX_BRIGHTNESS]

                attrs[ATTR_BRIGHTNESS] = int(
                    max_brightness - ((max_brightness - min_brightness) * factor))

                _LOGGER.debug(
                    f"Updating brigthness of {entity[ATTR_ENTITY_ID]} to {attrs[ATTR_BRIGHTNESS]}.", )

            states.append(State(entity[ATTR_ENTITY_ID], STATE_ON, attrs))

        await async_reproduce_state(hass, states, context=context)

    @callback
    async def add_adaptive(call: ServiceCall):
        entity_id = call.data.get(ATTR_ENTITY_ID)
        if ha.split_entity_id(entity_id)[0] == DOMAIN_GROUP:

            entities = [
                {ATTR_ENTITY_ID: group_entity, ATTR_BRIGHTNESS: True,
                    ATTR_COLOR_TEMP: True}  # TODO Make configurable
                for group_entity in hass.components.group.get_entity_ids(entity_id)
                if ha.split_entity_id(group_entity)[0] == DOMAIN_LIGHT
            ]

            await update_adaptive(entities, call.context)
            add_entities_to_adaptive_track(entities)
        else:
            if ha.split_entity_id(entity_id)[0] == DOMAIN_LIGHT:
                adaptive = {ATTR_ENTITY_ID: entity_id, ATTR_BRIGHTNESS: True,
                            ATTR_COLOR_TEMP: True}  # TODO Make configurable
                await update_adaptive([adaptive], call.context)
                add_entities_to_adaptive_track([adaptive])

    hass.services.register(DOMAIN, SERVICE_ADD_ADAPTIVE,
                           add_adaptive, SERVICE_ADD_ADAPTIVE_SCHEMA)

    @callback
    async def remove_adaptive(call: ServiceCall):
        entity_id = call.data.get(ATTR_ENTITY_ID)
        if ha.split_entity_id(entity_id)[0] == DOMAIN_GROUP:
            remove_entities_from_adaptive_track(
                hass.components.group.get_entity_ids(entity_id))
        else:
            remove_entities_from_adaptive_track([entity_id])

    hass.services.register(DOMAIN, SERVICE_REMOVE_ADAPTIVE,
                           remove_adaptive, SERVICE_REMOVE_ADAPTIVE_SCHEMA)

    hass.helpers.discovery.load_platform(DOMAIN_SENSOR, DOMAIN, {}, config)

    return True

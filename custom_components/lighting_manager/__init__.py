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
from homeassistant.components.light import (DOMAIN as DOMAIN_LIGHT, ATTR_COLOR_TEMP, ATTR_COLOR_TEMP_KELVIN, ATTR_COLOR_MODE,
                                            COLOR_MODE_COLOR_TEMP, ATTR_BRIGHTNESS, ATTR_RGB_COLOR, ATTR_RGBW_COLOR,
                                            ATTR_EFFECT)
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
ATTR_COLOR = "color"

CONF_ACTIVE_LAYER_ENTITY = "active_layer_entity"
CONF_ADAPTIVE = "adaptive"
CONF_MAX_TEMP = "max_temp"
CONF_MIN_TEMP = "min_temp"
CONF_MAX_BRIGHTNESS = "max_brightness"
CONF_MIN_BRIGHTNESS = "min_brightness"
CONF_MAX_ELEVATION = "max_elevation"
CONF_MIN_ELEVATION = "min_elevation"
CONF_BRIGHTNESS_ENTITY_ID = "brightness_entity_id"
CONF_INPUT_BRIGHTNESS_MAX = "input_brightness_max"
CONF_INPUT_BRIGHTNESS_MIN = "input_brightness_min"
CONF_BRIGHTNESS_MODE_SUN = "brightness_mode_sun"

SIGNAL_LAYER_UPDATE = f"{DOMAIN}-update"

ENTITY_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ACTIVE_LAYER_ENTITY, default=False): cv.boolean,
        vol.Optional(CONF_ADAPTIVE, default={CONF_MAX_TEMP: None, CONF_MIN_TEMP: None,
                                             CONF_MIN_BRIGHTNESS: 155, CONF_MAX_BRIGHTNESS: 255,
                                             CONF_INPUT_BRIGHTNESS_MAX: None, CONF_INPUT_BRIGHTNESS_MIN: None,
                                             CONF_BRIGHTNESS_MODE_SUN: True}): vol.Schema(
            {
                vol.Optional(CONF_MAX_TEMP, default=None): vol.Any(None, cv.positive_int),
                vol.Optional(CONF_MIN_TEMP, default=None): vol.Any(None, cv.positive_int),
                vol.Optional(CONF_MAX_BRIGHTNESS, default=255): cv.positive_int,
                vol.Optional(CONF_MIN_BRIGHTNESS, default=150): cv.positive_int,
                vol.Optional(CONF_INPUT_BRIGHTNESS_MIN, default=None): vol.Any(None, cv.positive_int),
                vol.Optional(CONF_INPUT_BRIGHTNESS_MAX, default=None): vol.Any(None, cv.positive_int),
                vol.Optional(CONF_BRIGHTNESS_MODE_SUN, default=True): cv.boolean
            }
        )
    }
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_ENTITIES): {cv.entity_id: vol.Any(None, ENTITY_SCHEMA)},
                vol.Optional(CONF_ADAPTIVE, default={CONF_MIN_ELEVATION: 0, CONF_MAX_ELEVATION: 15, CONF_MIN_TEMP: 153,
                                                     CONF_MAX_TEMP: 333, CONF_BRIGHTNESS_ENTITY_ID: None,
                                                     CONF_INPUT_BRIGHTNESS_MAX: 255, CONF_INPUT_BRIGHTNESS_MIN: 0}): vol.Schema(
                    {
                        vol.Optional(CONF_MIN_ELEVATION, default=0): cv.positive_int,
                        vol.Optional(CONF_MAX_ELEVATION, default=15): cv.positive_int,
                        vol.Optional(CONF_MIN_TEMP, default=153): cv.positive_int,
                        vol.Optional(CONF_MAX_TEMP, default=333): cv.positive_int,
                        vol.Optional(CONF_BRIGHTNESS_ENTITY_ID, default=None): vol.Any(None, cv.string),
                        vol.Optional(CONF_INPUT_BRIGHTNESS_MAX, default=255): int,
                        vol.Optional(CONF_INPUT_BRIGHTNESS_MIN, default=0):int
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
        vol.Optional(ATTR_CLEAR_LAYER): cv.boolean,
        vol.Optional(ATTR_COLOR):  vol.Coerce(tuple)
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
    {
        vol.Required(ATTR_ENTITY_ID): cv.string,
        vol.Optional(ATTR_BRIGHTNESS, default=True): vol.Any(cv.boolean, cv.positive_int),
        vol.Optional(ATTR_COLOR_TEMP, default=True): cv.boolean
    }
)

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

    def state_has_adaptive(domain: str, state) -> bool:
        return domain == DOMAIN_LIGHT and (
            (state.attributes.get(ATTR_COLOR_TEMP, None) == CONF_ADAPTIVE) or
            (state.attributes.get(ATTR_BRIGHTNESS, None) == CONF_ADAPTIVE))

    def insert_adaptive_values(entity_id, state_attributes) -> None:
        adaptive_factor: float = float(hass.states.get(
            "sensor.adaptive_lighting_factor").state)
        
        brightness_adaptive_factor: float = adaptive_factor
        if (hass.data[DOMAIN][CONF_ADAPTIVE][CONF_BRIGHTNESS_ENTITY_ID] is not None and
            not hass.data[DOMAIN][DATA_ENTITIES][entity_id][CONF_ADAPTIVE][CONF_BRIGHTNESS_MODE_SUN]):

            brightness_current = float(hass.states.get(hass.data[DOMAIN][CONF_ADAPTIVE][CONF_BRIGHTNESS_ENTITY_ID]).state)
            brightness_input_min = float(hass.data[DOMAIN][DATA_ENTITIES][entity_id][CONF_ADAPTIVE].get(CONF_INPUT_BRIGHTNESS_MIN) or hass.data[DOMAIN][CONF_ADAPTIVE][CONF_INPUT_BRIGHTNESS_MIN])
            brightness_input_max = float(hass.data[DOMAIN][DATA_ENTITIES][entity_id][CONF_ADAPTIVE].get(CONF_INPUT_BRIGHTNESS_MAX) or hass.data[DOMAIN][CONF_ADAPTIVE][CONF_INPUT_BRIGHTNESS_MAX])
            brightness_adaptive_factor = 1.0 - (float(min(max(brightness_current, brightness_input_min), brightness_input_max)) / float(brightness_input_max))

        adaptive_track: dict = {
            ATTR_ENTITY_ID: entity_id,
            ATTR_COLOR_TEMP: state_attributes.get(ATTR_COLOR_TEMP, None) == CONF_ADAPTIVE,
            ATTR_BRIGHTNESS: state_attributes.get(
                ATTR_BRIGHTNESS, None) == CONF_ADAPTIVE
        }

        if state_attributes.get(ATTR_COLOR_TEMP, None) == CONF_ADAPTIVE:
            min_temp = (hass.data[DOMAIN][DATA_ENTITIES][entity_id][CONF_ADAPTIVE][CONF_MIN_TEMP] or
                        hass.data[DOMAIN][CONF_ADAPTIVE][CONF_MIN_TEMP])
            max_temp = (hass.data[DOMAIN][DATA_ENTITIES][entity_id][CONF_ADAPTIVE][CONF_MAX_TEMP] or
                        hass.data[DOMAIN][CONF_ADAPTIVE][CONF_MAX_TEMP])

            state_attributes[ATTR_COLOR_TEMP] = int(
                ((max_temp - min_temp) * adaptive_factor) + min_temp)
            state_attributes[ATTR_COLOR_MODE] = COLOR_MODE_COLOR_TEMP

        if state_attributes.get(ATTR_BRIGHTNESS, None) == CONF_ADAPTIVE:
            min_brightness = hass.data[DOMAIN][DATA_ENTITIES][entity_id][CONF_ADAPTIVE][CONF_MIN_BRIGHTNESS]
            max_brightness = hass.data[DOMAIN][DATA_ENTITIES][entity_id][CONF_ADAPTIVE][CONF_MAX_BRIGHTNESS]

            state_attributes[ATTR_BRIGHTNESS] = int(
                max_brightness - ((max_brightness - min_brightness) * brightness_adaptive_factor))
        
        if entity_id not in hass.data[DOMAIN][DATA_ADAPTIVE_ENTITIES]:
            add_entities_to_adaptive_track([adaptive_track])

    def handle_replacements(entity_id: str, state: State, color: list | None = None) -> State:
        domain = ha.split_entity_id(entity_id)[0]
        if domain == DOMAIN_LIGHT:
            new_attributes = dict(state.attributes)

            # Also default to no effect if not specified.
            if ATTR_EFFECT not in state.attributes:
                new_attributes[ATTR_EFFECT] = "None"

            if color and state.attributes.get(ATTR_RGB_COLOR, None) == ATTR_COLOR:
                new_attributes[ATTR_RGB_COLOR] = color
            elif color and state.attributes.get(ATTR_RGBW_COLOR, None) == ATTR_COLOR:
                new_attributes[ATTR_RGBW_COLOR] = color

            return State(entity_id, state.state, new_attributes)
        else:
            return state

    def render_entity(entity_id: str):
        if len(hass.data[DOMAIN][DATA_STATES][entity_id]) == 0:
            if entity_id in hass.data[DOMAIN][DATA_ADAPTIVE_ENTITIES]:
                remove_entities_from_adaptive_track([entity_id])

            return State(entity_id, STATE_OFF)
        else:
            active_state = None
            domain = ha.split_entity_id(entity_id)[0]

            for layer in hass.data[DOMAIN][DATA_STATES][entity_id]:
                if (
                    active_state == None
                    or hass.data[DOMAIN][DATA_STATES][entity_id][layer][ATTR_PRIORITY]
                    > active_state[ATTR_PRIORITY]
                ):
                    active_state = hass.data[DOMAIN][DATA_STATES][entity_id][layer]

            has_adaptive = state_has_adaptive(domain, active_state[ATTR_STATE])

            if has_adaptive:
                # Need to recreate state thanks to the read-only attributes included in the state...
                new_attributes = dict(active_state[ATTR_STATE].attributes)

                if has_adaptive:
                    insert_adaptive_values(entity_id, new_attributes)

                return State(entity_id, active_state[ATTR_STATE].state, new_attributes)

            if not has_adaptive and entity_id in hass.data[DOMAIN][DATA_ADAPTIVE_ENTITIES]:
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
        color = call.data.get(ATTR_COLOR)

        entity_states = (
            hass.data[DATA_HA_SCENE].entities[scene_entity_id].scene_config.states
        )

        ungrouped_entity_states = {}

        # Split out groups
        for entity_id in entity_states:
            if ha.split_entity_id(entity_id)[0] == DOMAIN_GROUP:
                for group_entity in hass.components.group.get_entity_ids(entity_id):
                    ungrouped_entity_states[group_entity] = handle_replacements(
                        group_entity, entity_states[entity_id], color=color)
            else:
                ungrouped_entity_states[entity_id] = handle_replacements(
                    entity_id, entity_states[entity_id], color=color)

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
                if entity_id not in affected_entities:
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

            # Force Effect to None if not specified
            overwrite_attributes = dict(attributes)
            if ha.split_entity_id(entity_id)[0] == DOMAIN_LIGHT and ATTR_EFFECT not in overwrite_attributes:
                overwrite_attributes[ATTR_EFFECT] = "None"

            hass.data[DOMAIN][DATA_STATES][entity][layer_id] = {
                ATTR_PRIORITY: priority,
                ATTR_STATE: State(entity_id, state, overwrite_attributes),
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
    
    if hass.data[DOMAIN][CONF_ADAPTIVE][CONF_BRIGHTNESS_ENTITY_ID] is not None:
        @callback
        async def on_input_brightness_change(event: Event) -> None:
            new_state: State = event.data.get("new_state")
            old_state: State = event.data.get("old_state")

            if new_state and old_state and new_state.state != old_state.state:
                await update_adaptive(hass.data[DOMAIN][DATA_ADAPTIVE_ENTITIES].values(), event.context)

        async_track_state_change_filtered(hass, TrackStates(
            False, [hass.data[DOMAIN][CONF_ADAPTIVE][CONF_BRIGHTNESS_ENTITY_ID]], None), on_input_brightness_change)

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

            if ATTR_BRIGHTNESS in entity and type(entity[ATTR_BRIGHTNESS]) is int:
                entity[ATTR_BRIGHTNESS] = False

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
        
        brightness_input_current = float(hass.states.get(hass.data[DOMAIN][CONF_ADAPTIVE][CONF_BRIGHTNESS_ENTITY_ID]).state)

        states = []

        for entity in entities:
            attrs = {}
            if ATTR_COLOR_TEMP in entity and entity[ATTR_COLOR_TEMP]:
                min_temp = (hass.data[DOMAIN][DATA_ENTITIES][entity[ATTR_ENTITY_ID]][CONF_ADAPTIVE][CONF_MIN_TEMP]
                            or hass.data[DOMAIN][CONF_ADAPTIVE][CONF_MIN_TEMP])
                max_temp = (hass.data[DOMAIN][DATA_ENTITIES][entity[ATTR_ENTITY_ID]][CONF_ADAPTIVE][CONF_MAX_TEMP]
                            or hass.data[DOMAIN][CONF_ADAPTIVE][CONF_MAX_TEMP])
                attrs[ATTR_COLOR_TEMP] = int(
                    ((max_temp - min_temp) * factor) + min_temp)
                attrs[ATTR_COLOR_MODE] = COLOR_MODE_COLOR_TEMP

            if ATTR_BRIGHTNESS in entity and entity[ATTR_BRIGHTNESS] == True:

                brightness_factor: float = factor
                if (not hass.data[DOMAIN][DATA_ENTITIES][entity[ATTR_ENTITY_ID]][CONF_ADAPTIVE][CONF_BRIGHTNESS_MODE_SUN]):

                    brightness_input_min = float(hass.data[DOMAIN][DATA_ENTITIES][entity[ATTR_ENTITY_ID]][CONF_ADAPTIVE].get(CONF_INPUT_BRIGHTNESS_MIN)
                                                 or hass.data[DOMAIN][CONF_ADAPTIVE][CONF_INPUT_BRIGHTNESS_MIN])
                    brightness_input_max = float(hass.data[DOMAIN][DATA_ENTITIES][entity[ATTR_ENTITY_ID]][CONF_ADAPTIVE].get(CONF_INPUT_BRIGHTNESS_MAX)
                                                 or hass.data[DOMAIN][CONF_ADAPTIVE][CONF_INPUT_BRIGHTNESS_MAX])
                                        
                    brightness_factor = 1.0 - (float(min(max(brightness_input_current, brightness_input_min), brightness_input_max)) / float(brightness_input_max))

                min_brightness = hass.data[DOMAIN][DATA_ENTITIES][entity[ATTR_ENTITY_ID]
                                                                  ][CONF_ADAPTIVE][CONF_MIN_BRIGHTNESS]
                max_brightness = hass.data[DOMAIN][DATA_ENTITIES][entity[ATTR_ENTITY_ID]
                                                                  ][CONF_ADAPTIVE][CONF_MAX_BRIGHTNESS]

                attrs[ATTR_BRIGHTNESS] = int(
                    max_brightness - ((max_brightness - min_brightness) * brightness_factor))

                _LOGGER.debug(
                    f"Updating brightness of {entity[ATTR_ENTITY_ID]} to {attrs[ATTR_BRIGHTNESS]}.", )
            elif ATTR_BRIGHTNESS in entity and entity[ATTR_BRIGHTNESS] != False:
                attrs[ATTR_BRIGHTNESS] = entity[ATTR_BRIGHTNESS]

            states.append(State(entity[ATTR_ENTITY_ID], STATE_ON, attrs))

        await async_reproduce_state(hass, states, context=context)

    @callback
    async def add_adaptive(call: ServiceCall):
        entity_id = call.data.get(ATTR_ENTITY_ID)
        brightness = call.data.get(ATTR_BRIGHTNESS)
        color_temp = call.data.get(ATTR_COLOR_TEMP)
        if brightness or color_temp:
            if ha.split_entity_id(entity_id)[0] == DOMAIN_GROUP:

                entities = [
                    {ATTR_ENTITY_ID: group_entity, ATTR_BRIGHTNESS: brightness,
                        ATTR_COLOR_TEMP: color_temp}
                    for group_entity in hass.components.group.get_entity_ids(entity_id)
                    if ha.split_entity_id(group_entity)[0] == DOMAIN_LIGHT
                ]

                await update_adaptive(entities, call.context)
                add_entities_to_adaptive_track(entities)
            else:
                if ha.split_entity_id(entity_id)[0] == DOMAIN_LIGHT:
                    adaptive = {ATTR_ENTITY_ID: entity_id, ATTR_BRIGHTNESS: brightness,
                                ATTR_COLOR_TEMP: color_temp}
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

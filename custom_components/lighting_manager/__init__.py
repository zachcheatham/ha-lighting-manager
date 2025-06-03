import logging
import voluptuous as vol

from typing import List
from dataclasses import dataclass

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
from homeassistant.components.group import DOMAIN as DOMAIN_GROUP, get_entity_ids
from homeassistant.components.sensor import DOMAIN as DOMAIN_SENSOR
from homeassistant.components.light import (DOMAIN as DOMAIN_LIGHT, ATTR_COLOR_TEMP, ATTR_COLOR_MODE,
                                            COLOR_MODE_COLOR_TEMP, ATTR_BRIGHTNESS, ATTR_RGB_COLOR, ATTR_RGBW_COLOR,
                                            ATTR_EFFECT)
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_filtered, TrackStates
from homeassistant.helpers.state import async_reproduce_state
import homeassistant.helpers.config_validation as cv

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

CONF_ADAPTIVE = "adaptive"
CONF_MAX_COLOR_TEMP = "color_temp_max"
CONF_MIN_COLOR_TEMP = "color_temp_min"
CONF_MAX_BRIGHTNESS = "brightness_max"
CONF_MIN_BRIGHTNESS = "brightness_min"
CONF_MAX_ELEVATION = "elevation_max"
CONF_MIN_ELEVATION = "elevation_min"
CONF_ADAPTIVE_INPUT_ENTITIES = "adaptive_input_entities"
CONF_INPUT_BRIGHTNESS_MAX = "input_brightness_max"
CONF_INPUT_BRIGHTNESS_MIN = "input_brightness_min"
CONF_INPUT_BRIGHTNESS_ENTITY = "input_brightness_entity"

SIGNAL_LAYER_UPDATE = f"{DOMAIN}-update"

ENTITY_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ADAPTIVE, default={CONF_MAX_COLOR_TEMP: None, CONF_MIN_COLOR_TEMP: None,
                                             CONF_MIN_BRIGHTNESS: 155, CONF_MAX_BRIGHTNESS: 255,
                                             CONF_INPUT_BRIGHTNESS_MAX: 255, CONF_INPUT_BRIGHTNESS_MIN: 0,
                                             CONF_INPUT_BRIGHTNESS_ENTITY: None}): vol.Schema(
            {
                vol.Optional(CONF_MAX_COLOR_TEMP, default=None): vol.Any(None, cv.positive_int),
                vol.Optional(CONF_MIN_COLOR_TEMP, default=None): vol.Any(None, cv.positive_int),
                vol.Optional(CONF_MAX_BRIGHTNESS, default=255): cv.positive_int,
                vol.Optional(CONF_MIN_BRIGHTNESS, default=150): cv.positive_int,
                vol.Optional(CONF_INPUT_BRIGHTNESS_MIN, default=None): vol.Any(None, cv.positive_int),
                vol.Optional(CONF_INPUT_BRIGHTNESS_MAX, default=None): vol.Any(None, cv.positive_int),
                vol.Optional(CONF_INPUT_BRIGHTNESS_ENTITY, default=None): vol.Any(None, cv.string),
            }
        )
    }
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_ENTITIES, default={}): {cv.entity_id: vol.Coerce(lambda x: ENTITY_SCHEMA(x or {}))},
                vol.Optional(CONF_ADAPTIVE, default={CONF_MIN_ELEVATION: 0, CONF_MAX_ELEVATION: 15, CONF_MIN_COLOR_TEMP: 153,
                                                     CONF_MAX_COLOR_TEMP: 333, CONF_ADAPTIVE_INPUT_ENTITIES: [],
                                                     CONF_INPUT_BRIGHTNESS_MAX: 255, CONF_INPUT_BRIGHTNESS_MIN: 0}): vol.Schema(
                    {
                        vol.Optional(CONF_MIN_ELEVATION, default=0): cv.positive_int,
                        vol.Optional(CONF_MAX_ELEVATION, default=15): cv.positive_int,
                        vol.Optional(CONF_MIN_COLOR_TEMP, default=153): cv.positive_int,
                        vol.Optional(CONF_MAX_COLOR_TEMP, default=333): cv.positive_int,
                        vol.Optional(CONF_INPUT_BRIGHTNESS_ENTITY, default=None): vol.Any(None, cv.string),
                        vol.Optional(CONF_ADAPTIVE_INPUT_ENTITIES, default=[]): vol.Any(None, [cv.string]),
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
        # TODO Add additional adaptive options
    }
)

SERVICE_REMOVE_ADAPTIVE_SCHEMA = vol.Schema(
    {vol.Required(ATTR_ENTITY_ID): cv.string})

@dataclass
class AdaptiveProperties:
    entity_id: str | None
    enable_brightness: bool
    enable_color_temp: bool
    brightness_input_entity_id: str | None
    brightness_input_min: int | None
    brightness_input_max: int | None
    brightness_min: int | None
    brightness_max: int | None
    color_temp_min: int | None
    color_temp_max: int | None

async def async_setup(hass: HomeAssistant, config: Config):

    conf = config[DOMAIN]

    hass.data[DOMAIN] = {}
    hass.data[DOMAIN][DATA_ENTITIES] = conf[CONF_ENTITIES]
    hass.data[DOMAIN][DATA_ADAPTIVE_ENTITIES] = {}
    hass.data[DOMAIN][DATA_STATES] = {}
    hass.data[DOMAIN][CONF_ADAPTIVE] = conf[CONF_ADAPTIVE]

    for entity_id in conf[CONF_ENTITIES].keys():
        hass.data[DOMAIN][DATA_STATES][entity_id] = {}

    def handle_replacements(entity_id: str, state: State, color: list | None = None) -> State:
        domain = ha.split_entity_id(entity_id)[0]
        if domain == DOMAIN_LIGHT:
            new_attributes = dict(state.attributes)

            # Also default to no effect if not specified.
            if ATTR_EFFECT not in state.attributes:
                new_attributes[ATTR_EFFECT] = "None"

            if color and state.attributes.get(ATTR_RGB_COLOR, None) == ATTR_COLOR:
                if len(color) == 4:
                    color.pop(3)
                new_attributes[ATTR_RGB_COLOR] = color
            elif color and state.attributes.get(ATTR_RGBW_COLOR, None) == ATTR_COLOR:
                if len(color) == 3:
                    color.append(0)
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

                new_attributes = dict(active_state[ATTR_STATE].attributes) # Need to recreate state thanks to the read-only attributes included in the state...

                color_temp_enabled = False
                color_temp_min = None
                color_temp_max = None
                brightness_enabled = False
                brightness_input_entity = None
                brightness_input_max = None
                brightness_input_min = None
                brightness_min = None
                brightness_max = None

                if str(new_attributes.get(ATTR_BRIGHTNESS, "")).startswith(CONF_ADAPTIVE):
                    brightness_enabled = True

                    for item in str(new_attributes.get(ATTR_BRIGHTNESS, "")).split(";"):
                        if '=' in item:
                            k,v = item.split("=", 2)

                            if k == CONF_INPUT_BRIGHTNESS_MAX:
                                brightness_input_max = int(v)
                            elif k == CONF_INPUT_BRIGHTNESS_MIN:
                                brightness_input_min = int(v)
                            elif k == CONF_INPUT_BRIGHTNESS_ENTITY:
                                brightness_input_entity = v
                            elif k == CONF_MAX_BRIGHTNESS:
                                brightness_max = int(v)
                            elif k == CONF_MIN_BRIGHTNESS:
                                brightness_min = int(v)
                            else:
                                _LOGGER.warning("Unknown adaptive brightness configuration in %s state: '%s' = '%s'", entity_id, k, v)

                if str(new_attributes.get(ATTR_COLOR_TEMP, "")).startswith(CONF_ADAPTIVE):
                    color_temp_enabled = True
                    for item in str(new_attributes.get(ATTR_COLOR_TEMP, "")).split(";"):
                        if '=' in item:
                            k,v = item.split("=", 1)

                            if k == CONF_MIN_COLOR_TEMP:
                                color_temp_min = v
                            elif k == CONF_MAX_COLOR_TEMP:
                                color_temp_max = v
                            else:
                                _LOGGER.warning("Unknown adaptive color_temp configuration in %s state: '%s' = '%s'", entity_id, k, v)

                create_adaptive_track(entity_id, new_attributes, AdaptiveProperties(
                    entity_id,
                    brightness_enabled,
                    color_temp_enabled,
                    brightness_input_entity,
                    brightness_input_min,
                    brightness_input_max,
                    brightness_min,
                    brightness_max,
                    color_temp_min,
                    color_temp_max
                ))

                return State(entity_id, active_state[ATTR_STATE].state, new_attributes)

            elif not has_adaptive and entity_id in hass.data[DOMAIN][DATA_ADAPTIVE_ENTITIES]:
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
                for group_entity in get_entity_ids(hass, entity_id):
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

    hass.services.async_register(
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
            for entity in get_entity_ids(hass, entity_id):
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

    hass.services.async_register(
        DOMAIN, SERVICE_INSERT_STATE, insert_state, SERVICE_INSERT_STATE_SCHEMA
    )

    @callback
    async def remove_layer(call: ServiceCall):
        entity_id = call.data.get(ATTR_ENTITY_ID)
        layer_id = call.data.get(ATTR_ID)

        affected_entities = []

        if entity_id:
            if ha.split_entity_id(entity_id)[0] == DOMAIN_GROUP:
                for light_entity in get_entity_ids(hass, entity_id):
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

    hass.services.async_register(
        DOMAIN, SERVICE_REMOVE_LAYER, remove_layer, SERVICE_REMOVE_LAYER_SCHEMA
    )

    @callback
    async def refresh_all(call: ServiceCall):
        await apply_entities(hass.data[DOMAIN][DATA_ENTITIES], [], call.context)

    hass.services.async_register(
        DOMAIN, SERVICE_REFRESH_ALL, refresh_all
    )

    @callback
    async def refresh(call: ServiceCall):
        entity_id = call.data.get(ATTR_ENTITY_ID)
        if ha.split_entity_id(entity_id)[0] == DOMAIN_GROUP:
            await apply_entities([
                group_entity
                for group_entity in get_entity_ids(hass, entity_id)
                if group_entity in hass.data[DOMAIN][DATA_ENTITIES]
            ], [], call.context)
        else:
            await apply_entities([entity_id], [], call.context)

    hass.services.async_register(DOMAIN, SERVICE_REFRESH,
                           refresh, SERVICE_REFRESH_SCHEMA)

    @callback
    async def on_state_change_event(event: Event) -> None:

        old_state: State = event.data.get("old_state", STATE_UNAVAILABLE)
        new_state: State = event.data.get("new_state", STATE_UNAVAILABLE)

        if new_state and (not old_state or old_state.state == STATE_UNAVAILABLE or old_state.state == STATE_UNKNOWN) and new_state.state != STATE_UNAVAILABLE and new_state.state != STATE_UNKNOWN:
            _LOGGER.warning("Restoring state of %s...",
                         event.data[ATTR_ENTITY_ID])
            await apply_entities([event.data[ATTR_ENTITY_ID]], [], event.context)

    async_track_state_change_filtered(hass, TrackStates(
        False, hass.data[DOMAIN][DATA_ENTITIES], None), on_state_change_event)

    @callback
    async def on_adaptive_factor_change(event: Event) -> None:
        new_state: State = event.data.get("new_state")
        old_state: State = event.data.get("old_state")

        if new_state and old_state and new_state.state != old_state.state:
            await update_adaptive(
                hass.data[DOMAIN][DATA_ADAPTIVE_ENTITIES].values(), event.context, "sun")

    async_track_state_change_filtered(hass, TrackStates(
        False, ["sensor.adaptive_lighting_factor"], None), on_adaptive_factor_change)

    # Register listener for all adaptive brightness inputs
    if hass.data[DOMAIN][CONF_ADAPTIVE][CONF_ADAPTIVE_INPUT_ENTITIES] is not None:
        @callback
        async def on_input_brightness_change(event: Event) -> None:
            entity_id: str = event.data.get("entity_id")
            new_state: State = event.data.get("new_state")
            old_state: State = event.data.get("old_state")

            if new_state and old_state and new_state.state != old_state.state:
                await update_adaptive(hass.data[DOMAIN][DATA_ADAPTIVE_ENTITIES].values(), event.context, entity_id)

        async_track_state_change_filtered(hass, TrackStates(
            False, hass.data[DOMAIN][CONF_ADAPTIVE][CONF_ADAPTIVE_INPUT_ENTITIES], None), on_input_brightness_change)

    # Listen for lights turning off to remove them from the automatic updates
    @callback
    async def on_adaptive_light_change_event(event: Event) -> None:
        old_state: State = event.data.get("old_state")
        new_state: State = event.data.get("new_state")

        if old_state.state != new_state.state and new_state.state == STATE_OFF:
            remove_entities_from_adaptive_track(
                [event.data.get(ATTR_ENTITY_ID)])

    adaptive_track_states = async_track_state_change_filtered(hass, TrackStates(
        False, set(hass.data[DOMAIN][DATA_ADAPTIVE_ENTITIES].keys()), None), on_adaptive_light_change_event)

    def add_entity_to_adaptive_track(properties: AdaptiveProperties) -> None:
        hass.data[DOMAIN][DATA_ADAPTIVE_ENTITIES][properties.entity_id] = properties
        adaptive_track_states.async_update_listeners(TrackStates(
            False, set(hass.data[DOMAIN][DATA_ADAPTIVE_ENTITIES].keys()), None))

    def remove_entities_from_adaptive_track(entity_ids: List[str]) -> None:
        for entity_id in entity_ids:
            if entity_id in hass.data[DOMAIN][DATA_ADAPTIVE_ENTITIES]:
                del hass.data[DOMAIN][DATA_ADAPTIVE_ENTITIES][entity_id]

        adaptive_track_states.async_update_listeners(TrackStates(
            False, set(hass.data[DOMAIN][DATA_ADAPTIVE_ENTITIES].keys()), None))

    def state_has_adaptive(domain: str, state) -> bool:

        brightness = state.attributes.get(ATTR_BRIGHTNESS, None)
        color_temp = state.attributes.get(ATTR_COLOR_TEMP, None)

        return domain == DOMAIN_LIGHT and (
            (isinstance(brightness, str) and brightness.startswith(CONF_ADAPTIVE)) or
            (isinstance(color_temp, str) and color_temp.startswith(CONF_ADAPTIVE)))


    def create_adaptive_track(entity_id, state_attributes, adaptive_properties: AdaptiveProperties) -> None:
        adaptive_config = hass.data[DOMAIN][CONF_ADAPTIVE]
        entity_adaptive_config = hass.data[DOMAIN][DATA_ENTITIES][entity_id][CONF_ADAPTIVE]

        input_brightness_entity = adaptive_properties.brightness_input_entity_id or entity_adaptive_config[CONF_INPUT_BRIGHTNESS_ENTITY] or adaptive_config[CONF_INPUT_BRIGHTNESS_ENTITY]
        input_brightness_min = adaptive_properties.brightness_input_min or entity_adaptive_config[CONF_INPUT_BRIGHTNESS_MIN] or adaptive_config[CONF_INPUT_BRIGHTNESS_MIN]
        input_brightness_max = adaptive_properties.brightness_input_max or entity_adaptive_config[CONF_INPUT_BRIGHTNESS_MAX] or adaptive_config[CONF_INPUT_BRIGHTNESS_MAX]
        brightness_min = adaptive_properties.brightness_min or entity_adaptive_config[CONF_MIN_BRIGHTNESS]
        brightness_max = adaptive_properties.brightness_max or entity_adaptive_config[CONF_MAX_BRIGHTNESS]
        color_temp_min = adaptive_properties.color_temp_min or entity_adaptive_config[CONF_MIN_COLOR_TEMP] or adaptive_config[CONF_MIN_COLOR_TEMP]
        color_temp_max = adaptive_properties.color_temp_max or entity_adaptive_config[CONF_MAX_COLOR_TEMP] or adaptive_config[CONF_MAX_COLOR_TEMP]

        if brightness_min is None or brightness_max is None:
            _LOGGER.warninging("%s does not specify min or max brightnesses. Cannot set adaptive brightness!", entity_id)

        if color_temp_min is None or color_temp_max is None:
            _LOGGER.warninging("%s does not specify min or max temperatures. Cannot set adaptive temp!", entity_id)

        adaptive_track_properties = AdaptiveProperties(
            entity_id,
            adaptive_properties.enable_brightness,
            adaptive_properties.enable_color_temp,
            input_brightness_entity,
            input_brightness_min,
            input_brightness_max,
            brightness_min,
            brightness_max,
            color_temp_min,
            color_temp_max)

        if state_attributes is not None:
            set_adaptive_values(adaptive_track_properties, state_attributes)

        if entity_id not in hass.data[DOMAIN][DATA_ADAPTIVE_ENTITIES]:
            add_entity_to_adaptive_track(adaptive_track_properties)


    def set_adaptive_values(ap: AdaptiveProperties, state_attributes) -> None:

        _LOGGER.debug("Applying adaptive values using configuration: %s", ap)

        if (ap.enable_brightness and
            ap.brightness_min and ap.brightness_max):

            brightness_input = float(hass.states.get(ap.brightness_input_entity_id).state)
            brightness_adaptive_factor = 1.0 - (float(min(max(brightness_input, ap.brightness_input_min), ap.brightness_input_max)) / float(ap.brightness_input_max))
            state_attributes[ATTR_BRIGHTNESS] = int(round(ap.brightness_max - ((ap.brightness_max - ap.brightness_min) * brightness_adaptive_factor)))

            _LOGGER.debug("input_brightness:%s brighness_factor:%s", brightness_input, brightness_adaptive_factor)

        if (ap.enable_color_temp and
            ap.color_temp_max and
            ap.color_temp_min):

            sun_adaptive_factor = float(hass.states.get("sensor.adaptive_lighting_factor").state)
            state_attributes[ATTR_COLOR_TEMP] = int(round(((ap.color_temp_max - ap.color_temp_min) * sun_adaptive_factor) + ap.color_temp_min))
            state_attributes[ATTR_COLOR_MODE] = COLOR_MODE_COLOR_TEMP

            _LOGGER.debug("sun_factor:%s", sun_adaptive_factor)

        _LOGGER.debug("Resulting attributes for %s: %s", ap.entity_id, state_attributes)


    async def update_adaptive(entities: List[any], context: Context, input_entity_id: str | None = None) -> None:
        states = []
        for entity_adaptive_properties in entities:
            if isinstance(entity_adaptive_properties, str):
                entity_adaptive_properties = hass.data[DOMAIN][DATA_ADAPTIVE_ENTITIES][entity_adaptive_properties]

            if ((entity_adaptive_properties.enable_brightness and (entity_adaptive_properties.brightness_input_entity_id == input_entity_id or input_entity_id is None)) or
                entity_adaptive_properties.enable_color_temp and (input_entity_id == "sun" or input_entity_id is None)):
                attrs = {}

                set_adaptive_values(entity_adaptive_properties, attrs)
                states.append(State(entity_adaptive_properties.entity_id, STATE_ON, attrs))

        await async_reproduce_state(hass, states, context=context)

    @callback
    async def add_adaptive(call: ServiceCall):
        entity_id = call.data.get(ATTR_ENTITY_ID)
        brightness = call.data.get(ATTR_BRIGHTNESS)
        color_temp = call.data.get(ATTR_COLOR_TEMP)
        states = []

        _LOGGER.debug("Call for adaptive brightness: %s", call.data)

        if ha.split_entity_id(entity_id)[0] == DOMAIN_GROUP:

            entities = [group_entity
                        for group_entity in get_entity_ids(hass, entity_id)
                        if ha.split_entity_id(group_entity)[0] == DOMAIN_LIGHT]

            for group_entity in entities:
                entity_attrs = {}
                create_adaptive_track(group_entity, entity_attrs, AdaptiveProperties(
                    group_entity, brightness is True, color_temp is True,
                    None, None, None, None, None, None, None
                ))
                if brightness is not None and brightness is not True:
                    entity_attrs[ATTR_BRIGHTNESS] = brightness
                if color_temp is not None and color_temp is not True:
                    entity_attrs[ATTR_COLOR_TEMP] = color_temp
                    entity_attrs[ATTR_COLOR_MODE] = COLOR_MODE_COLOR_TEMP

                states.append(State(group_entity, STATE_ON, entity_attrs))
        else:
            if ha.split_entity_id(entity_id)[0] == DOMAIN_LIGHT:
                entity_attrs = {}
                create_adaptive_track(entity_id, entity_attrs, AdaptiveProperties(
                    entity_id, brightness is True, color_temp is True,
                    None, None, None, None, None, None, None
                ))
                if brightness is not None and brightness is not True:
                    entity_attrs[ATTR_BRIGHTNESS] = brightness
                if color_temp is not None and color_temp is not True:
                    entity_attrs[ATTR_COLOR_TEMP] = color_temp
                    entity_attrs[ATTR_COLOR_MODE] = COLOR_MODE_COLOR_TEMP
                states.append(State(entity_id, STATE_ON, entity_attrs))

        await async_reproduce_state(hass, states, context=call.context)

    hass.services.async_register(DOMAIN, SERVICE_ADD_ADAPTIVE,
                           add_adaptive, SERVICE_ADD_ADAPTIVE_SCHEMA)

    @callback
    async def remove_adaptive(call: ServiceCall):
        entity_id = call.data.get(ATTR_ENTITY_ID)
        if ha.split_entity_id(entity_id)[0] == DOMAIN_GROUP:
            remove_entities_from_adaptive_track(
                get_entity_ids(hass, entity_id))
        else:
            remove_entities_from_adaptive_track([entity_id])

    hass.services.async_register(DOMAIN, SERVICE_REMOVE_ADAPTIVE,
                           remove_adaptive, SERVICE_REMOVE_ADAPTIVE_SCHEMA)

    hass.async_create_task(async_load_platform(hass, DOMAIN_SENSOR, DOMAIN, {}, config))

    return True

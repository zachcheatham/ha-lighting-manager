import logging
import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from typing import Any, Dict, List, cast
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
from homeassistant.core import Context, Event, HomeAssistant, ServiceCall, State, callback
from homeassistant.core_config import Config
from homeassistant.components.group import DOMAIN as DOMAIN_GROUP, get_entity_ids
from homeassistant.components.number import DOMAIN as DOMAIN_NUMBER
from homeassistant.components.cover import (DOMAIN as DOMAIN_COVER, CoverState,
                                            ATTR_CURRENT_TILT_POSITION, ATTR_TILT_POSITION)
from homeassistant.components.scene import DOMAIN as DOMAIN_SCENE, DATA_COMPONENT as DATA_HA_SCENE
from homeassistant.components.fan import DOMAIN as DOMAIN_FAN
from homeassistant.components.light import (DOMAIN as DOMAIN_LIGHT, ATTR_COLOR_TEMP_KELVIN, ATTR_COLOR_MODE,
                                            ATTR_BRIGHTNESS, ATTR_RGB_COLOR, ATTR_RGBW_COLOR, ATTR_EFFECT,
                                            ColorMode)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ELEVATION, SERVICE_SET_COVER_TILT_POSITION
from homeassistant.helpers.event import async_track_state_change_filtered, TrackStates
from homeassistant.helpers.state import async_reproduce_state
from homeassistant.helpers.storage import Store

from .const import (DOMAIN,
                    STORAGE_VERSION, STORAGE_KEY, SUPPORTED_DOMAINS,
                    ATTR_PRIORITY, ATTR_CLEAR_LAYER, ATTR_COLOR, ATTR_ATTRIBUTES, ATTR_COLOR_TEMP,
                    CONF_ADAPTIVE, CONF_MAX_COLOR_TEMP, CONF_MIN_COLOR_TEMP, CONF_MIN_BRIGHTNESS,
                    CONF_MAX_BRIGHTNESS, CONF_INPUT_BRIGHTNESS_MAX, CONF_INPUT_BRIGHTNESS_MIN,
                    CONF_INPUT_BRIGHTNESS_ENTITY, CONF_ADAPTIVE_INPUT_ENTITIES, CONF_DEFAULT_STATE,
                    CONF_MIN_ELEVATION, CONF_MAX_ELEVATION,
                    SERVICE_INSERT_SCENE, SERVICE_INSERT_STATE, SERVICE_REMOVE_LAYER, SERVICE_ADD_ADAPTIVE,
                    SERVICE_REMOVE_ALL_LAYERS,
                    SERVICE_REMOVE_ADAPTIVE, SERVICE_REFRESH, SERVICE_REFRESH_ALL)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = []

SERVICE_INSERT_SCENE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_domain(DOMAIN_SCENE),
        vol.Required(ATTR_ID): cv.string,
        vol.Required(ATTR_PRIORITY): cv.positive_int,
        vol.Optional(ATTR_CLEAR_LAYER): cv.boolean,
        vol.Optional(ATTR_COLOR):  vol.Coerce(tuple)
    }
)

SERVICE_INSERT_STATE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_domain(SUPPORTED_DOMAINS + [DOMAIN_GROUP]),
        vol.Required(ATTR_PRIORITY): cv.positive_int,
        vol.Required(ATTR_ID): cv.string,
        vol.Optional(ATTR_STATE): cv.string,
        vol.Optional(ATTR_ATTRIBUTES): dict,
        vol.Optional(ATTR_CLEAR_LAYER): cv.boolean
    }
)

SERVICE_REMOVE_LAYER_SCHEMA = vol.Schema(
    {vol.Optional(ATTR_ENTITY_ID): cv.entity_domain(SUPPORTED_DOMAINS + [DOMAIN_GROUP]), vol.Required(ATTR_ID): cv.string}
)

SERVICE_REFRESH_SCHEMA = vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.entity_domain(SUPPORTED_DOMAINS + [DOMAIN_GROUP])})

SERVICE_ADD_ADAPTIVE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_domain([DOMAIN_LIGHT, DOMAIN_GROUP]),
        vol.Optional(ATTR_BRIGHTNESS, default=None): vol.Any(cv.boolean, cv.positive_int),
        vol.Optional(ATTR_COLOR_TEMP, default=True): vol.Any(cv.boolean, cv.positive_int)
    }
)

SERVICE_REMOVE_ADAPTIVE_SCHEMA = vol.Schema(
    {vol.Required(ATTR_ENTITY_ID): cv.entity_domain([DOMAIN_LIGHT, DOMAIN_GROUP])})


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
    return True


async def async_setup_entry(hass: HomeAssistant, config: ConfigEntry) -> bool:
    coordinator = LayerManagerCoordinator(hass, config)
    await coordinator.async_load_from_store()

    hass.data.setdefault(DOMAIN, {})[config.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(config, PLATFORMS)
    config.async_on_unload(config.add_update_listener(config_update_listener))


    await coordinator.async_setup_services()
    await coordinator.async_setup_listeners()
    await coordinator.async_initial_refresh()

    return True

async def async_unload_entry(hass: HomeAssistant, config: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(config, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(config.entry_id)
        await coordinator.async_unload()

    return unload_ok


async def config_update_listener(hass: HomeAssistant, config: ConfigEntry):
    coordinator = hass.data[DOMAIN][config.entry_id]
    await coordinator.async_options_updated()


class LayerManagerCoordinator:
    def __init__(self, hass: HomeAssistant, config: ConfigEntry):
        self.hass = hass
        self.config = config
        self.managed_entities: List[str] = []
        self.entity_states: Dict[str, Dict[str, Dict]] = {}
        self.adaptive_entities: Dict[str, AdaptiveProperties] = {}
        self._unsub_listeners = []
        self._store = Store[Dict[str, Any]](hass, STORAGE_VERSION, STORAGE_KEY)
        self._adaptive_track_states_remover = None
        self._adaptive_color_temp_factor: float = 0.0

        self._load_options()

    def _load_options(self):
        self.managed_entities = self.config.options.get(CONF_ENTITIES, {})
        for entity_id in list(self.managed_entities.keys()):
            self.entity_states.setdefault(entity_id, {})

        for entity_id in list(self.entity_states.keys()):
            if entity_id not in self.managed_entities:
                del self.entity_states[entity_id]
                if entity_id in self.adaptive_entities:
                    del self.adaptive_entities[entity_id]

    async def async_options_updated(self):
        self._load_options()
        await self.async_setup_listeners()
        await self.async_initial_refresh()

    async def async_initial_refresh(self):
        await self._apply_entities(self.managed_entities, [], None)

    async def async_load_from_store(self):
        stored_data = await self._store.async_load()
        if stored_data:
            for entity_id, layers, in stored_data.items():
                self.entity_states[entity_id] = {}
                for layer_id, data in layers.items():
                    state_info = data.get(ATTR_STATE, {})
                    reconstructed_state = State(state_info.get("entity_id", entity_id),
                                                state_info.get("state"),
                                                state_info.get("attributes"))
                    self.entity_states[entity_id][layer_id] = {
                        ATTR_PRIORITY: data.get(ATTR_PRIORITY),
                        ATTR_STATE: reconstructed_state
                    }

    def _schedule_save(self):
        serializable_states = {}
        for entity_id, layers in self.entity_states.items():
            if entity_id not in self.managed_entities: continue
            serializable_states[entity_id] = {}
            for layer_id, data in layers.items():
                state_obj = cast(State, data.get(ATTR_STATE))
                serializable_states[entity_id][layer_id] = {
                    ATTR_PRIORITY: data.get(ATTR_PRIORITY),
                    ATTR_STATE: {
                        "entity_id": state_obj.entity_id,
                        "state": state_obj.state,
                        "attributes": dict(state_obj.attributes)
                    }
                }

        self._store.async_delay_save(lambda: serializable_states, 1)

    async def insert_scene(self, call: ServiceCall):
        scene_entity_id = call.data.get(ATTR_ENTITY_ID)
        layer_id = call.data.get(ATTR_ID)
        priority = call.data.get(ATTR_PRIORITY)
        should_clear = call.data.get(ATTR_CLEAR_LAYER)
        color = call.data.get(ATTR_COLOR)

        scene_entity = self.hass.data.get(DATA_HA_SCENE, {}).get_entity(scene_entity_id)
        if not scene_entity: _LOGGER.error("Scene %s not found", scene_entity_id); return

        entity_states = scene_entity.scene_config.states
        ungrouped_entity_states = {}

        # Split out groups
        for entity_id, state in entity_states.items():
            if ha.split_entity_id(entity_id)[0] == DOMAIN_GROUP:
                for group_entity in get_entity_ids(self.hass, entity_id):
                    ungrouped_entity_states[group_entity] = self._handle_replacements(
                        group_entity, state, color=color)
            else:
                ungrouped_entity_states[entity_id] = self._handle_replacements(
                    entity_id, state, color=color)

        non_managed_entities = []
        affected_entities = []

        if should_clear: affected_entities.extend(self._clear_layer(layer_id))
        for entity_id, state in ungrouped_entity_states.items():
            if entity_id in self.managed_entities:
                self.entity_states.setdefault(entity_id, {})[layer_id] = {
                    ATTR_PRIORITY: priority,
                    ATTR_STATE: state
                }
                if entity_id not in affected_entities:
                    affected_entities.append(entity_id)
            else:
                non_managed_entities.append(state)

        await self._apply_entities(affected_entities, non_managed_entities, call.context)
        self._schedule_save()

    async def insert_state(self, call: ServiceCall):
        entity_id = call.data.get(ATTR_ENTITY_ID)
        priority = call.data.get(ATTR_PRIORITY)
        layer_id = call.data.get(ATTR_ID)
        state = call.data.get(ATTR_STATE, STATE_ON)
        attributes = call.data.get(ATTR_ATTRIBUTES, {})
        should_clear = call.data.get(ATTR_CLEAR_LAYER)

        affected_entities = []
        extra_entities_to_update = []
        target_entities = []

        if should_clear:
            affected_entities.extend(self._clear_layer(layer_id))

        if ha.split_entity_id(entity_id)[0] == DOMAIN_GROUP:
            target_entities.extend(get_entity_ids(self.hass, entity_id))
        else:
            target_entities.append(entity_id)

        for target_entity_id in target_entities:
            if target_entity_id in self.managed_entities:
                if target_entity_id not in affected_entities:
                    affected_entities.append(target_entity_id)

                overwrite_attributes = dict(attributes)

                # Force Effect to None if not specified
                if ha.split_entity_id(target_entity_id)[0] == DOMAIN_LIGHT and ATTR_EFFECT not in overwrite_attributes:
                    overwrite_attributes[ATTR_EFFECT] = "None"

                self.entity_states.setdefault(target_entity_id, {})[layer_id] = {
                    ATTR_PRIORITY: priority,
                    ATTR_STATE: State(target_entity_id, state, overwrite_attributes)
                }
            else:
                extra_entities_to_update.append(State(target_entity_id, state, attributes))

        await self._apply_entities(affected_entities, extra_entities_to_update, call.context)
        self._schedule_save()

    async def remove_layer(self, call: ServiceCall):
        entity_id = call.data.get(ATTR_ENTITY_ID)
        layer_id = call.data.get(ATTR_ID)
        affected_entities = []
        entities_to_check = []

        if entity_id:
            if ha.split_entity_id(entity_id)[0] == DOMAIN_GROUP:
                entities_to_check.extend(get_entity_ids(self.hass, entity_id))
            else:
                entities_to_check.append(entity_id)
        else:
            entities_to_check.extend(self.managed_entities)

        for check_entity_id in entities_to_check:
            if check_entity_id in self.managed_entities and layer_id in self.entity_states.get(check_entity_id, {}):
                self.entity_states[check_entity_id].pop(layer_id)
                affected_entities.append(check_entity_id)

        if affected_entities:
            await self._apply_entities(affected_entities, [], call.context)
            self._schedule_save()

    async def remove_all_layers(self, call: ServiceCall):
        affected_entities = []

        for entity_id in self.managed_entities:
            if self.entity_states.get(entity_id, {}):
                self.entity_states[entity_id] = {}
                affected_entities.append(entity_id)

        if affected_entities:
            await self._apply_entities(affected_entities, [], call.context)
            self._schedule_save()

    async def refresh_all(self, call: ServiceCall):
        await self._apply_entities(self.managed_entities, [], call.context)

    async def refresh(self, call: ServiceCall):
        entity_id = call.data.get(ATTR_ENTITY_ID)
        entities_to_refresh = []
        if ha.split_entity_id(entity_id)[0] == DOMAIN_GROUP:
            entities_to_refresh.extend([e for e in get_entity_ids(self.hass, entity_id) if e in self.managed_entities])
        elif entity_id in self.managed_entities:
            entities_to_refresh.append(entity_id)

        await self._apply_entities(entities_to_refresh, [], call.context)

    async def add_adaptive(self, call: ServiceCall):
        entity_id = call.data.get(ATTR_ENTITY_ID)
        brightness = call.data.get(ATTR_BRIGHTNESS)
        color_temp = call.data.get(ATTR_COLOR_TEMP)
        states_to_apply = []

        target_entities = get_entity_ids(self.hass, entity_id) if ha.split_entity_id(entity_id)[0] == DOMAIN_GROUP else [entity_id]

        for light_entity in [e for e in target_entities if ha.split_entity_id(e)[0] == DOMAIN_LIGHT]:
            attrs = {}
            props = AdaptiveProperties(
                    light_entity, brightness is True, color_temp is True,
                    None, None, None, None, None, None, None)
            self._create_adaptive_track(light_entity, attrs, props)
            if brightness not in (True, None):
                attrs[ATTR_BRIGHTNESS] = brightness
            if color_temp not in (True, None):
                attrs[ATTR_COLOR_TEMP_KELVIN] = color_temp
                attrs[ATTR_COLOR_MODE] = ColorMode.COLOR_TEMP

            states_to_apply.append(State(light_entity, STATE_ON, attrs))

        if states_to_apply:
            await async_reproduce_state(self.hass, states_to_apply, context=call.context)

    async def remove_adaptive(self, call: ServiceCall):
        entity_id = call.data.get(ATTR_ENTITY_ID)
        entities_to_remove = get_entity_ids(self.hass, entity_id) if ha.split_entity_id(entity_id)[0] == DOMAIN_GROUP else [entity_id]
        self._remove_entities_from_adaptive_track(entities_to_remove)
        await self._apply_entities(entities_to_remove, [], call.context)

    def _clear_layer(self, layer_id: str) -> List[str]:
        affected = []
        [self.entity_states[entity_id].pop(layer_id) and affected.append(entity_id)
         for entity_id in self.managed_entities if layer_id in self.entity_states.get(entity_id, {})]

        return affected

    def _handle_replacements(self, entity_id: str, state: State, color: list | None = None) -> State:
        if ha.split_entity_id(entity_id)[0] == DOMAIN_LIGHT:
            new_attributes = dict(state.attributes)

            # Also default to no effect if not specified.
            if ATTR_EFFECT not in state.attributes:
                new_attributes[ATTR_EFFECT] = "None"

            if color:
                if state.attributes.get(ATTR_RGB_COLOR) == ATTR_COLOR:
                    new_attributes[ATTR_RGB_COLOR] = tuple(color[:3])
                elif state.attributes.get(ATTR_RGBW_COLOR) == ATTR_COLOR:
                    rgbw = list(color[:3]) + [0] if len(color) == 3 else list(color[:4])
                    new_attributes[ATTR_RGBW_COLOR] = tuple(rgbw)

            return State(entity_id, state.state, new_attributes)
        else:
            return state

    def _render_entity(self, entity_id: str) -> State | tuple:
        layers = self.entity_states.get(entity_id)
        if not layers:
            if entity_id in self.adaptive_entities:
                self._remove_entities_from_adaptive_track([entity_id])
            if (default_state := self._get_default_state(entity_id)) is not None:
                return State(entity_id, default_state)
            else:
                return None

        active_layer = max(layers.values(), key=lambda layer: layer[ATTR_PRIORITY])
        active_state = active_layer[ATTR_STATE]
        has_adaptive = self._state_has_adaptive(active_state)

        if has_adaptive:
            new_attributes = dict(active_state.attributes)
            brightness_str = str(new_attributes.get(ATTR_BRIGHTNESS, ""))
            color_temp_str = str(new_attributes.get(ATTR_COLOR_TEMP_KELVIN, ""))
            props = AdaptiveProperties(entity_id,
                                       brightness_str.startswith(CONF_ADAPTIVE),
                                       color_temp_str.startswith(CONF_ADAPTIVE),
                                       None, None, None, None, None, None, None)

            # Insert adhoc adaptive brightness settings
            if props.enable_brightness:
                for item in brightness_str.split(';'):
                    if '=' in item:
                        k, v = item.split('=', 1)
                        setattr(props, k, v)

            # Insert adhoc adaptive color temp settings
            if props.enable_color_temp:
                for item in color_temp_str.split(';'):
                    if '=' in item:
                        k, v = item.split('=', 1)
                        setattr(props, k, v)

            self._create_adaptive_track(entity_id, new_attributes, props)
            active_state = State(entity_id, active_state.state, new_attributes)
        elif entity_id in self.adaptive_entities:
            self._remove_entities_from_adaptive_track([entity_id])

        # Handle service call enhancements
        if (ha.split_entity_id(entity_id)[0] == DOMAIN_COVER and
            ATTR_CURRENT_TILT_POSITION in active_state.attributes):

            return (
                DOMAIN_COVER,
                SERVICE_SET_COVER_TILT_POSITION,
                {
                    ATTR_ENTITY_ID: entity_id,
                    ATTR_TILT_POSITION: active_state.attributes[ATTR_CURRENT_TILT_POSITION]
                }
            )

        return active_state

    def _state_has_adaptive(self, state: State) -> bool:
        brightness = state.attributes.get(ATTR_BRIGHTNESS, None)
        color_temp = state.attributes.get(ATTR_COLOR_TEMP_KELVIN, None)

        return ha.split_entity_id(state.entity_id)[0] == DOMAIN_LIGHT and (
            (isinstance(brightness, str) and brightness.startswith(CONF_ADAPTIVE)) or
            (isinstance(color_temp, str) and color_temp.startswith(CONF_ADAPTIVE)))

    def _create_adaptive_track(self, entity_id: str, state_attributes: Dict, props: AdaptiveProperties) -> None:

        adaptive_config = self.config.options.get(CONF_ADAPTIVE, {})

        ap = AdaptiveProperties(
            entity_id=entity_id, enable_brightness=props.enable_brightness,
            enable_color_temp=props.enable_color_temp,
            brightness_input_entity_id=props.brightness_input_entity_id or adaptive_config.get(CONF_INPUT_BRIGHTNESS_ENTITY),
            brightness_input_min=props.brightness_input_min or adaptive_config.get(CONF_INPUT_BRIGHTNESS_MIN),
            brightness_input_max=props.brightness_input_max or adaptive_config.get(CONF_INPUT_BRIGHTNESS_MAX),
            brightness_min=props.brightness_min or adaptive_config.get(CONF_MIN_BRIGHTNESS),
            brightness_max=props.brightness_max or adaptive_config.get(CONF_MAX_BRIGHTNESS),
            color_temp_min=props.color_temp_min or adaptive_config.get(CONF_MIN_COLOR_TEMP),
            color_temp_max=props.color_temp_max or adaptive_config.get(CONF_MAX_COLOR_TEMP)
        )

        self._set_adaptive_values(ap, state_attributes)
        if entity_id not in self.adaptive_entities:
            self._add_entity_to_adaptive_track(ap)

    def _set_adaptive_values(self, ap: AdaptiveProperties, state_attributes: Dict) -> None:

        if ap.enable_brightness and ap.brightness_input_entity_id and (input_state := self.hass.states.get(ap.brightness_input_entity_id)):
            try:
                input_val = float(input_state.state)
                norm_val = 1.0 - (float(min(max(input_val, ap.brightness_input_min), ap.brightness_input_max)) / float(ap.brightness_input_max))
                state_attributes[ATTR_BRIGHTNESS] = int(ap.brightness_max - ((ap.brightness_max - ap.brightness_min) * norm_val))
            except (ValueError, TypeError):
                pass

        if ap.enable_color_temp:
            try:
                state_attributes[ATTR_COLOR_TEMP_KELVIN] = int(round(((ap.color_temp_max - ap.color_temp_min) * self._adaptive_color_temp_factor) + ap.color_temp_min))
                state_attributes[ATTR_COLOR_MODE] = ColorMode.COLOR_TEMP
            except (ValueError, TypeError):
                pass

    async def _update_adaptive(self, context: Context, input_entity_id: str | None = None) -> None:
        states_to_apply = []
        for ap in list(self.adaptive_entities.values()):
            should_update_brightness = ap.enable_brightness and (ap.brightness_input_entity_id == input_entity_id or input_entity_id is None)
            should_update_color = ap.enable_color_temp and (input_entity_id == "sun" or input_entity_id is None)

            if should_update_brightness or should_update_color:
                attrs = {}
                self._set_adaptive_values(ap, attrs)
                if attrs:
                    states_to_apply.append(State(ap.entity_id, STATE_ON, attrs))

        if states_to_apply:
            await async_reproduce_state(self.hass, states_to_apply, context=context)

    def _add_entity_to_adaptive_track(self, props: AdaptiveProperties) -> None:
        self.adaptive_entities[props.entity_id] = props
        self._adaptive_track_states_remover.async_update_listeners(TrackStates(False, set(self.adaptive_entities.keys()), None))

    def _remove_entities_from_adaptive_track(self, entity_ids: List[str]) -> None:
        removed = False
        for entity_id in entity_ids:
            if entity_id in self.adaptive_entities:
                del self.adaptive_entities[entity_id]
                removed = True

        if removed:
            self._adaptive_track_states_remover.async_update_listeners(TrackStates(False, set(self.adaptive_entities.keys()), None))

    async def _apply_entities(self, entities: List[str], additional_states: List[State], context: Context | None):
        states_to_apply = additional_states[:]

        for entity_id in entities:
            if entity_id not in self.managed_entities:
                continue

            rendered_state = self._render_entity(entity_id)
            if rendered_state is None:
                continue

            if isinstance(rendered_state, State):
                states_to_apply.append(rendered_state)
            elif isinstance(rendered_state, tuple):
                domain, service, service_data = rendered_state
                await self.hass.services.async_call(
                    domain,
                    service,
                    service_data,
                    blocking=False
                )

        if states_to_apply:
            await async_reproduce_state(self.hass, states_to_apply, context=context)

    def _get_default_state(self, entity_id: str):
        return (self.config.options.get(CONF_ENTITIES, {}).get(entity_id, {}).get(CONF_DEFAULT_STATE, None) or
            get_domain_default_state(ha.split_entity_id(entity_id)[0]))

    async def async_setup_services(self):
        self.hass.services.async_register(DOMAIN, SERVICE_INSERT_SCENE, self.insert_scene, SERVICE_INSERT_SCENE_SCHEMA)
        self.hass.services.async_register(DOMAIN, SERVICE_INSERT_STATE, self.insert_state, SERVICE_INSERT_STATE_SCHEMA)
        self.hass.services.async_register(DOMAIN, SERVICE_REMOVE_LAYER, self.remove_layer, SERVICE_REMOVE_LAYER_SCHEMA)
        self.hass.services.async_register(DOMAIN, SERVICE_REMOVE_ALL_LAYERS, self.remove_all_layers)
        self.hass.services.async_register(DOMAIN, SERVICE_REFRESH_ALL, self.refresh_all)
        self.hass.services.async_register(DOMAIN, SERVICE_REFRESH, self.refresh, SERVICE_REFRESH_SCHEMA)
        self.hass.services.async_register(DOMAIN, SERVICE_ADD_ADAPTIVE, self.add_adaptive, SERVICE_ADD_ADAPTIVE_SCHEMA)
        self.hass.services.async_register(DOMAIN, SERVICE_REMOVE_ADAPTIVE, self.remove_adaptive, SERVICE_REMOVE_ADAPTIVE_SCHEMA)

    async def async_unload(self):
        for service in self.hass.services.async_services().get(DOMAIN, {}):
            self.hass.services.async_remove(DOMAIN, service)
        for unsub in self._unsub_listeners:
            unsub()
        self._unsub_listeners.clear()
        self._adaptive_track_states_remover.async_remove()

    async def async_setup_listeners(self):
        for unsub in self._unsub_listeners:
            unsub()
        self._unsub_listeners.clear()

        self._unsub_listeners.append(async_track_state_change_filtered(
            self.hass, TrackStates(False, {"sun.sun"}, None), self.on_sun_changed).async_remove)

        self._adaptive_track_states_remover = async_track_state_change_filtered(
            self.hass, TrackStates(False, set(self.adaptive_entities.keys()), None), self.on_adaptive_light_change_event)

        adaptive_opts = self.config.options.get(CONF_ADAPTIVE, {})
        input_entities = adaptive_opts.get(CONF_ADAPTIVE_INPUT_ENTITIES, [])
        if input_entities:
            self._unsub_listeners.append(async_track_state_change_filtered(
                self.hass, TrackStates(False, input_entities, None), self.on_input_brightness_change).async_remove)

        if self.managed_entities:
            self._unsub_listeners.append(async_track_state_change_filtered(
                self.hass, TrackStates(False, self.managed_entities, None), self.on_state_change_event).async_remove)

    @callback
    async def on_state_change_event(self, event: Event) -> None:

        old_state: State = event.data.get("old_state", STATE_UNAVAILABLE)
        new_state: State = event.data.get("new_state", STATE_UNAVAILABLE)
        entity_id = event.data.get(ATTR_ENTITY_ID)

        if (new_state and
            (not old_state or old_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN)) and
            new_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)):

            _LOGGER.warning("Restoring state of %s after it became available...", entity_id)
            await self._apply_entities([entity_id], [], event.context)

    @callback
    async def on_sun_changed(self, event: Event) -> None:

        new_state: State = event.data.get("new_state")

        if not new_state or not new_state.attributes.get(ATTR_ELEVATION):
            return

        elevation = new_state.attributes[ATTR_ELEVATION]

        min_elev = self.config.options.get(CONF_MIN_ELEVATION, 0)
        max_elev = self.config.options.get(CONF_MAX_ELEVATION, 15)
        adaptive_color_temp_factor = 1.0

        if max_elev > min_elev:
            adaptive_color_temp_factor = (
                min(max(elevation, min_elev), max_elev) - min_elev
            ) / (max_elev - min_elev)

        if adaptive_color_temp_factor != self._adaptive_color_temp_factor:
            self._adaptive_color_temp_factor = adaptive_color_temp_factor
            await self._update_adaptive(event.context, "sun")

    @callback
    async def on_input_brightness_change(self, event: Event):
        new_state: State = event.data.get("new_state")
        old_state: State = event.data.get("old_state")

        if new_state and old_state and new_state.state != old_state.state:
            await self._update_adaptive(event.context, event.data.get("entity_id"))

    @callback
    async def on_adaptive_light_change_event(self, event: Event) -> None:
        old_state: State = event.data.get("old_state")
        new_state: State = event.data.get("new_state")

        if (not old_state or old_state.state != new_state.state) and new_state.state == STATE_OFF:
            self._remove_entities_from_adaptive_track([event.data.get(ATTR_ENTITY_ID)])

def get_domain_default_state(domain: str):
    if domain in (DOMAIN_LIGHT, DOMAIN_FAN):
        return STATE_OFF
    elif domain == DOMAIN_NUMBER:
        return "0"
    elif domain == DOMAIN_COVER:
        return CoverState.CLOSED
    else:
        return None

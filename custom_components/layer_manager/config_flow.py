import logging
from typing import Any, Dict
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.sensor.const import DOMAIN as DOMAIN_SENSOR
from homeassistant.components.number.const import DOMAIN as DOMAIN_NUMBER
from homeassistant.components.input_number import DOMAIN as DOMAIN_INPUT_NUMBER
from homeassistant.components.light.const import DOMAIN as DOMAIN_LIGHT
from homeassistant.core import callback, split_entity_id
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    DEFAULT_CONF_NAME,
    CONF_ENTITIES,
    CONF_ADAPTIVE,
    SUPPORTED_DOMAINS,
    CONF_MIN_ELEVATION,
    CONF_MAX_ELEVATION,
    CONF_DEFAULT_STATE,
    CONF_MIN_COLOR_TEMP,
    CONF_MAX_COLOR_TEMP,
    CONF_ADAPTIVE_INPUT_ENTITIES,
    CONF_INPUT_BRIGHTNESS_ENTITY,
    CONF_INPUT_BRIGHTNESS_MIN,
    CONF_INPUT_BRIGHTNESS_MAX,
    CONF_MIN_BRIGHTNESS,
    CONF_MAX_BRIGHTNESS
)

_LOGGER = logging.getLogger(__name__)

class LayerManagerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):

    VERSION = 1

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(title=DEFAULT_CONF_NAME, data={}, options={CONF_ENTITIES: {}})

        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return LayerManagerOptionsFlowHandler()


class LayerManagerOptionsFlowHandler(config_entries.OptionsFlow):

    VERSION = 1

    def __init__(self):
        self.entity_id_to_config = None
        self.options = None

    async def async_step_init(self, user_input=None):
        if not self.options:
            self.options = dict(self.config_entry.options)

        return self.async_show_menu(
            step_id="init",
            menu_options=["manage_entities",
                          "select_advanced_entity",
                          "global_adaptive_settings"],
        )

    async def async_step_manage_entities(self, user_input=None):

        if user_input is not None:

            existing_entities_conf = self.config_entry.options.get(CONF_ENTITIES, {})
            new_entity_list = user_input.get(CONF_ENTITIES, [])
            new_entities_conf = {
                entity: existing_entities_conf.get(entity, {})
                for entity in new_entity_list
            }

            self.options[CONF_ENTITIES] = new_entities_conf
            return self.async_create_entry(title="", data=self.options)

        managed_entities = list(self.config_entry.options.get(CONF_ENTITIES, {}).keys())

        return self.async_show_form(
            step_id="manage_entities",
            data_schema=vol.Schema({
                vol.Optional(CONF_ENTITIES, default=managed_entities): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=SUPPORTED_DOMAINS, multiple=True)
                )
            })
        )

    async def async_step_select_advanced_entity(self, user_input=None):
        managed_entities = list(self.options.get(CONF_ENTITIES, {}).keys())
        if not managed_entities:
            return self.async_abort(reason="no_managed_entities")

        if user_input is not None:
            self.entity_id_to_config = user_input["entity_id"]
            return await self.async_step_advanced_entity_settings()

        return self.async_show_form(
            step_id="select_advanced_entity",
            data_schema=vol.Schema({
                vol.Required("entity_id"): selector.EntitySelector(
                    selector.EntitySelectorConfig(include_entities=managed_entities)
                )
            })
        )

    async def async_step_advanced_entity_settings(self, user_input=None):
        entity_id = self.entity_id_to_config

        if user_input is not None:
            entity_conf = self.options[CONF_ENTITIES].get(entity_id, {})
            adaptive_input = {k: v for k, v in user_input.items() if v is not None and v != "" and v in [
                    CONF_MIN_COLOR_TEMP, CONF_MAX_COLOR_TEMP, CONF_ADAPTIVE_INPUT_ENTITIES,
                    CONF_INPUT_BRIGHTNESS_ENTITY, CONF_INPUT_BRIGHTNESS_MIN, CONF_INPUT_BRIGHTNESS_MAX,
                    CONF_MIN_BRIGHTNESS, CONF_MAX_BRIGHTNESS
            ]}
            entity_conf[CONF_ADAPTIVE] = adaptive_input
            entity_conf[CONF_DEFAULT_STATE] = user_input[CONF_DEFAULT_STATE]
            self.options[CONF_ENTITIES][entity_id] = entity_conf

            return self.async_create_entry(title="", data=self.options)

        entity_conf = self.options[CONF_ENTITIES].get(entity_id, {})
        adaptive_conf = entity_conf.get(CONF_ADAPTIVE)

        if split_entity_id(entity_id)[0] == DOMAIN_LIGHT:
            conf_schema = self._get_adaptive_schema(adaptive_conf, False)
        else:
            conf_schema = {
                vol.Optional(CONF_DEFAULT_STATE, default=entity_conf.get(CONF_DEFAULT_STATE, None)): str
            }

        return self.async_show_form(
            step_id="advanced_entity_settings",
            description_placeholders={"entity_id": entity_id},
            data_schema=vol.Schema(conf_schema)
        )

    async def async_step_global_adaptive_settings(self, user_input=None):
        if user_input is not None:
            self.options[CONF_ADAPTIVE] = user_input
            return self.async_create_entry(title="", data=self.options)

        adaptive_opts = self.options.get(CONF_ADAPTIVE, {})

        schema = {
            vol.Optional(CONF_MIN_ELEVATION, default=adaptive_opts.get(CONF_MIN_ELEVATION, 0)): int,
            vol.Optional(CONF_MAX_ELEVATION, default=adaptive_opts.get(CONF_MAX_ELEVATION, 15)): int,
            vol.Optional(CONF_ADAPTIVE_INPUT_ENTITIES, default=adaptive_opts.get(CONF_ADAPTIVE_INPUT_ENTITIES, [])):
                selector.EntitySelector(selector.EntitySelectorConfig(multiple=True, domain=[DOMAIN_SENSOR, DOMAIN_NUMBER, DOMAIN_INPUT_NUMBER]))
        }
        schema.update(self._get_adaptive_schema(adaptive_opts, True))

        return self.async_show_form(step_id="global_adaptive_settings", data_schema=vol.Schema(schema))

    def _get_adaptive_schema(self, options: Dict[str, Any] = None, root_config=False) -> Dict:
        options = options or {}

        input_selector_opts = None
        if root_config:
            input_selector_opts = selector.EntitySelectorConfig(domain=[DOMAIN_SENSOR, DOMAIN_NUMBER, DOMAIN_INPUT_NUMBER])
        else:
            input_selector_opts = selector.EntitySelectorConfig(include_entities=options.get(CONF_ADAPTIVE_INPUT_ENTITIES, []))

        return {
            vol.Optional(CONF_MIN_BRIGHTNESS, default=options.get(CONF_MIN_BRIGHTNESS)):
                selector.NumberSelector(selector.NumberSelectorConfig(min=1, max=255, mode="box")),
            vol.Optional(CONF_MAX_BRIGHTNESS, default=options.get(CONF_MAX_BRIGHTNESS)):
                selector.NumberSelector(selector.NumberSelectorConfig(min=1, max=255, mode="box")),
            vol.Optional(CONF_MIN_COLOR_TEMP, default=options.get(CONF_MIN_COLOR_TEMP)):
                selector.NumberSelector(selector.NumberSelectorConfig(min=0,mode="box")),
            vol.Optional(CONF_MAX_COLOR_TEMP, default=options.get(CONF_MAX_COLOR_TEMP)):
                selector.NumberSelector(selector.NumberSelectorConfig(min=0,mode="box")),
            vol.Optional(CONF_INPUT_BRIGHTNESS_ENTITY, default=options.get(CONF_INPUT_BRIGHTNESS_ENTITY)):
                selector.EntitySelector(input_selector_opts),
            vol.Optional(CONF_INPUT_BRIGHTNESS_MIN, default=options.get(CONF_INPUT_BRIGHTNESS_MIN)):
                selector.NumberSelector(selector.NumberSelectorConfig(min=0,mode="box")),
            vol.Optional(CONF_INPUT_BRIGHTNESS_MAX, default=options.get(CONF_INPUT_BRIGHTNESS_MAX)):
                selector.NumberSelector(selector.NumberSelectorConfig(min=0,mode="box"))
        }

    def _get_entity_schema(self, domain: str) -> Dict:
        return {
            vol.Optional(CONF_DEFAULT_STATE, description={"suggested_value": None}): str
        }

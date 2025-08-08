"""Config flow for Lighting Manager."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.selector import selector

from .const import (
    CONF_ENTITIES,
    CONF_MAX_ELEVATION,
    CONF_MIN_ELEVATION,
    CONF_ZONE,
    DOMAIN,
)


class LightingManagerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the integration."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step where a zone is defined."""
        if user_input is not None:
            zone_id = user_input[CONF_ZONE]
            return self.async_create_entry(title=zone_id, data=user_input)

        data_schema = vol.Schema(
            {
                vol.Required(CONF_ZONE): str,
                vol.Required(CONF_ENTITIES): selector(
                    {"entity": {"domain": "light", "multiple": True}}
                ),
                vol.Optional(CONF_MIN_ELEVATION, default=0): int,
                vol.Optional(CONF_MAX_ELEVATION, default=15): int,
            }
        )
        return self.async_show_form(step_id="user", data_schema=data_schema)

    async def async_step_import(self, user_input: dict[str, Any]):
        """Handle import from YAML."""
        return await self.async_step_user(user_input)

    @staticmethod
    def async_get_options_flow(config_entry):
        return LightingManagerOptionsFlow(config_entry)


class LightingManagerOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Lighting Manager."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_ENTITIES,
                    default=self.config_entry.data.get(CONF_ENTITIES, []),
                ): selector(
                    {"entity": {"domain": "light", "multiple": True}}
                ),
                vol.Optional(
                    CONF_MIN_ELEVATION,
                    default=self.config_entry.options.get(
                        CONF_MIN_ELEVATION,
                        self.config_entry.data.get(CONF_MIN_ELEVATION, 0),
                    ),
                ): int,
                vol.Optional(
                    CONF_MAX_ELEVATION,
                    default=self.config_entry.options.get(
                        CONF_MAX_ELEVATION,
                        self.config_entry.data.get(CONF_MAX_ELEVATION, 15),
                    ),
                ): int,
            }
        )
        return self.async_show_form(step_id="init", data_schema=data_schema)

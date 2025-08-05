"""Config flow for IRsinn integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .backends import SUPPORTED_BACKENDS
from .remote import (
    CONF_BACKEND,
    CONF_CONTROLLER_DATA,
    CONF_DELAY,
    CONF_DEVICE_CODE,
    CONF_NAME,
    CONF_UNIQUE_ID,
    DEFAULT_DELAY,
)


class IRsinnConfigFlow(config_entries.ConfigFlow, domain="irsinn"):
    """Handle a config flow for IRsinn."""

    async def async_step_user(self, user_input=None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

        data_schema = vol.Schema(
            {
                vol.Required(CONF_NAME): str,
                vol.Required(CONF_UNIQUE_ID): str,
                vol.Required(CONF_DEVICE_CODE): int,
                vol.Optional(CONF_DELAY, default=DEFAULT_DELAY): float,
                vol.Required(CONF_BACKEND): vol.In(sorted(SUPPORTED_BACKENDS)),
                vol.Required(CONF_CONTROLLER_DATA): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=data_schema)

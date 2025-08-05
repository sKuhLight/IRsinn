"""Config flow for IRsinn integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from . import CONF_ENTITY_TYPE
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

    def __init__(self) -> None:
        self._backend: str | None = None
        self._entity_type: str | None = None

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Select entity type and backend."""
        if user_input is not None:
            self._entity_type = user_input[CONF_ENTITY_TYPE]
            self._backend = user_input[CONF_BACKEND]
            return await self.async_step_device()

        entity_types = ["remote", "climate", "fan", "light", "media_player"]
        data_schema = vol.Schema(
            {
                vol.Required(CONF_ENTITY_TYPE): vol.In(entity_types),
                vol.Required(CONF_BACKEND): vol.In(sorted(SUPPORTED_BACKENDS)),
            }
        )
        return self.async_show_form(step_id="user", data_schema=data_schema)

    async def async_step_device(self, user_input=None) -> FlowResult:
        """Collect device specific settings."""
        assert self._backend is not None and self._entity_type is not None

        if user_input is not None:
            data = {
                CONF_NAME: user_input[CONF_NAME],
                CONF_UNIQUE_ID: user_input[CONF_UNIQUE_ID],
                CONF_DEVICE_CODE: user_input[CONF_DEVICE_CODE],
                CONF_DELAY: user_input.get(CONF_DELAY, DEFAULT_DELAY),
                CONF_BACKEND: self._backend,
                CONF_CONTROLLER_DATA: user_input[CONF_CONTROLLER_DATA],
                CONF_ENTITY_TYPE: self._entity_type,
            }
            return self.async_create_entry(title=data[CONF_NAME], data=data)

        backend_cls = SUPPORTED_BACKENDS[self._backend]
        controllers = await backend_cls.async_controller_options(self.hass)
        if controllers:
            controller_field = vol.Required(
                CONF_CONTROLLER_DATA, default=next(iter(controllers))
            )
            controller_validator = vol.In(controllers)
        else:
            controller_field = vol.Required(CONF_CONTROLLER_DATA)
            controller_validator = str

        data_schema = vol.Schema(
            {
                vol.Required(CONF_NAME): str,
                vol.Required(CONF_UNIQUE_ID): str,
                vol.Required(CONF_DEVICE_CODE): int,
                vol.Optional(CONF_DELAY, default=DEFAULT_DELAY): float,
                controller_field: controller_validator,
            }
        )
        return self.async_show_form(step_id="device", data_schema=data_schema)

import asyncio
import logging

import voluptuous as vol

from homeassistant.components.remote import (
    RemoteEntity,
    PLATFORM_SCHEMA,
    RemoteEntityFeature,
)
from homeassistant.const import CONF_NAME
import homeassistant.helpers.config_validation as cv
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import ConfigType

from . import DOMAIN
from .backends import get_backend, SUPPORTED_BACKENDS
from .storage_manager import StorageManager

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "IRsinn Remote"
DEFAULT_DELAY = 0.5

CONF_UNIQUE_ID = "unique_id"
CONF_DEVICE_CODE = "device_code"
CONF_CONTROLLER_DATA = "controller_data"
CONF_DELAY = "delay"
CONF_BACKEND = "backend"

SUPPORT_FLAGS = (
    RemoteEntityFeature.LEARN_COMMAND | RemoteEntityFeature.DELETE_COMMAND
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_UNIQUE_ID): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Required(CONF_DEVICE_CODE): cv.positive_int,
        vol.Required(CONF_CONTROLLER_DATA): cv.string,
        vol.Optional(CONF_DELAY, default=DEFAULT_DELAY): cv.positive_float,
        vol.Required(CONF_BACKEND): vol.In(sorted(SUPPORTED_BACKENDS)),
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: dict | None = None,
) -> None:
    """Set up the IR Remote platform."""
    device_code = config.get(CONF_DEVICE_CODE)

    storage: StorageManager = hass.data.get(DOMAIN, {}).get("storage") or StorageManager(hass)
    try:
        device_data = await storage.async_load_device("remote", device_code)
    except Exception:
        _LOGGER.error("The device JSON file is invalid")
        return
    backend = get_backend(
        hass,
        config[CONF_BACKEND],
        config[CONF_CONTROLLER_DATA],
        config[CONF_DELAY],
    )

    async_add_entities([IRsinnRemote(hass, config, device_data, backend, storage)])


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
):
    """Set up IRsinn remote from a config entry."""
    storage: StorageManager = hass.data.get(DOMAIN, {}).get("storage") or StorageManager(hass)
    device_code = entry.data[CONF_DEVICE_CODE]
    device_data = await storage.async_load_device("remote", device_code)
    backend = get_backend(
        hass,
        entry.data[CONF_BACKEND],
        entry.data[CONF_CONTROLLER_DATA],
        entry.data.get(CONF_DELAY, DEFAULT_DELAY),
    )
    async_add_entities([IRsinnRemote(hass, entry.data, device_data, backend, storage)])


class IRsinnRemote(RemoteEntity, RestoreEntity):
    def __init__(self, hass, config, device_data, backend, storage: StorageManager):
        self.hass = hass
        self._unique_id = config.get(CONF_UNIQUE_ID)
        self._name = config.get(CONF_NAME)
        self._device_code = config.get(CONF_DEVICE_CODE)
        self._controller_data = config.get(CONF_CONTROLLER_DATA)
        self._delay = config.get(CONF_DELAY)
        self._backend_name = config.get(CONF_BACKEND)

        self._manufacturer = device_data.get("manufacturer")
        self._supported_models = device_data.get("supportedModels")
        self._commands_encoding = device_data.get("commandsEncoding")
        self._device_class = device_data.get("device_class")
        self._commands = device_data.get("commands", {})

        self._is_on = False
        self._backend = backend
        self._storage = storage

    @property
    def name(self):
        return self._name

    @property
    def should_poll(self):
        return False

    @property
    def supported_features(self):
        return SUPPORT_FLAGS

    @property
    def is_on(self):
        return self._is_on

    @property
    def device_info(self):
        return {
            "identifiers": {("irsinn", self._unique_id or self._device_code)},
            "name": self._name,
            "manufacturer": self._manufacturer,
            "model": ", ".join(self._supported_models) if self._supported_models else None,
        }

    @property
    def extra_state_attributes(self):
        return {
            "device_code": self._device_code,
            "manufacturer": self._manufacturer,
            "supported_models": self._supported_models,
            "backend": self._backend_name,
            "commands_encoding": self._commands_encoding,
        }

    async def async_added_to_hass(self) -> None:
        self.hass.data.setdefault(DOMAIN, {}).setdefault("entities", {})[
            self.entity_id
        ] = self

    async def async_will_remove_from_hass(self) -> None:
        self.hass.data.get(DOMAIN, {}).get("entities", {}).pop(self.entity_id, None)

    async def async_turn_on(self, **kwargs):
        command = self._commands.get("turn_on")
        if command is not None:
            await self._backend.async_send(command)
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        command = self._commands.get("turn_off")
        if command is not None:
            await self._backend.async_send(command)
        self._is_on = False
        self.async_write_ha_state()

    async def async_send_command(self, command, **kwargs):
        if isinstance(command, str):
            commands = [command]
        else:
            commands = command
        for cmd in commands:
            if cmd in self._commands:
                await self._backend.async_send(self._commands[cmd])
                await asyncio.sleep(self._delay)

    async def async_learn_command(self, **kwargs):
        command = kwargs.get("command")
        command_data = kwargs.get("command_data", [])
        if command:
            self._commands[command] = command_data
            await self._storage.async_save_command(
                "remote", self._device_code, command, command_data
            )

    async def async_delete_command(self, **kwargs):
        command = kwargs.get("command")
        if command in self._commands:
            self._commands.pop(command)
            await self._storage.async_delete_command(
                "remote", self._device_code, command
            )


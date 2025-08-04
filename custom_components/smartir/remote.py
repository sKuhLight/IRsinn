import asyncio
import aiofiles
import json
import logging
import os.path

import voluptuous as vol

from homeassistant.components.remote import (
    RemoteEntity,
    PLATFORM_SCHEMA,
    RemoteEntityFeature,
)
from homeassistant.const import CONF_NAME
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.restore_state import RestoreEntity

from . import COMPONENT_ABS_DIR, Helper
from .controller import get_controller

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "SmartIR Remote"
DEFAULT_DELAY = 0.5

CONF_UNIQUE_ID = "unique_id"
CONF_DEVICE_CODE = "device_code"
CONF_CONTROLLER_DATA = "controller_data"
CONF_DELAY = "delay"

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
    }
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the IR Remote platform."""
    device_code = config.get(CONF_DEVICE_CODE)
    device_files_subdir = os.path.join("codes", "remote")
    device_files_absdir = os.path.join(COMPONENT_ABS_DIR, device_files_subdir)

    if not os.path.isdir(device_files_absdir):
        os.makedirs(device_files_absdir)

    device_json_filename = str(device_code) + ".json"
    device_json_path = os.path.join(device_files_absdir, device_json_filename)

    if not os.path.exists(device_json_path):
        _LOGGER.warning(
            "Couldn't find the device Json file. The component will try to download it from the GitHub repo."
        )
        try:
            codes_source = (
                "https://raw.githubusercontent.com/"
                "smartHomeHub/SmartIR/master/"
                "codes/remote/{}.json"
            )
            await Helper.downloader(codes_source.format(device_code), device_json_path)
        except Exception:
            _LOGGER.error(
                "There was an error while downloading the device Json file. Please check your internet connection or if the device code exists on GitHub. If the problem still exists please place the file manually in the proper directory."
            )
            return

    try:
        async with aiofiles.open(device_json_path, mode="r") as j:
            content = await j.read()
            device_data = json.loads(content)
    except Exception:
        _LOGGER.error("The device JSON file is invalid")
        return

    async_add_entities([
        SmartIRRemote(
            hass,
            config,
            device_data,
        )
    ])


class SmartIRRemote(RemoteEntity, RestoreEntity):
    def __init__(self, hass, config, device_data):
        self.hass = hass
        self._unique_id = config.get(CONF_UNIQUE_ID)
        self._name = config.get(CONF_NAME)
        self._device_code = config.get(CONF_DEVICE_CODE)
        self._controller_data = config.get(CONF_CONTROLLER_DATA)
        self._delay = config.get(CONF_DELAY)

        self._manufacturer = device_data.get("manufacturer")
        self._supported_models = device_data.get("supportedModels")
        self._supported_controller = device_data.get("supportedController")
        self._commands_encoding = device_data.get("commandsEncoding")
        self._device_class = device_data.get("device_class")
        self._commands = device_data.get("commands", {})

        self._is_on = False
        self._controller = get_controller(
            hass,
            self._supported_controller,
            self._commands_encoding,
            self._controller_data,
            self._delay,
        )

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
            "identifiers": {("smartir", self._unique_id or self._device_code)},
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
            "supported_controller": self._supported_controller,
            "commands_encoding": self._commands_encoding,
        }

    async def async_turn_on(self, **kwargs):
        command = self._commands.get("turn_on")
        if command is not None:
            await self._controller.send(command)
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        command = self._commands.get("turn_off")
        if command is not None:
            await self._controller.send(command)
        self._is_on = False
        self.async_write_ha_state()

    async def async_send_command(self, command, **kwargs):
        if isinstance(command, str):
            commands = [command]
        else:
            commands = command
        for cmd in commands:
            if cmd in self._commands:
                await self._controller.send(self._commands[cmd])
                await asyncio.sleep(self._delay)

    async def async_learn_command(self, **kwargs):
        command = kwargs.get("command")
        command_data = kwargs.get("command_data", [])
        if command:
            self._commands[command] = command_data

    async def async_delete_command(self, **kwargs):
        command = kwargs.get("command")
        if command in self._commands:
            self._commands.pop(command)

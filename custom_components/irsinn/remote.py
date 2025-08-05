import asyncio
import logging
from typing import Any

import voluptuous as vol

try:  # pragma: no cover - allows tests without Home Assistant
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
except Exception:  # pragma: no cover - Home Assistant not available
    RemoteEntity = type("RemoteEntity", (object,), {})  # type: ignore
    RestoreEntity = type("RestoreEntity", (object,), {})  # type: ignore

    class RemoteEntityFeature:  # type: ignore
        LEARN_COMMAND = 0
        DELETE_COMMAND = 0

    PLATFORM_SCHEMA = vol.Schema({})
    CONF_NAME = "name"

    class _CV:  # minimal stand-ins for Home Assistant validators
        string = str
        positive_int = int
        positive_float = float

    cv = _CV()
    HomeAssistant = AddEntitiesCallback = ConfigType = Any

from . import DOMAIN, async_get_device_config
from .controller import get_controller

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "IRsinn Remote"
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


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: dict | None = None,
) -> None:
    """Set up the IR Remote platform."""
    device_code = config.get(CONF_DEVICE_CODE)

    try:
        device_data = await async_get_device_config("remote", device_code)
    except Exception:
        _LOGGER.error("The device JSON file is invalid")
        return

    async_add_entities([IRsinnRemote(hass, config, device_data)])


class IRsinnRemote(RemoteEntity, RestoreEntity):
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

    async def async_added_to_hass(self) -> None:
        """Register entity for domain services."""
        await super().async_added_to_hass()
        self.hass.data.setdefault(DOMAIN, {})[self.entity_id] = self

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
        command = kwargs.get("command") or kwargs.get("key")
        _LOGGER.debug("Learn command requested: %s", command)
        if not command:
            _LOGGER.error("No command name provided for learn_command")
            return

        try:
            learned = await self._controller.learn()
        except NotImplementedError:
            _LOGGER.error("Controller does not support learning")
            return
        except Exception as err:  # pragma: no cover - depends on HA
            _LOGGER.error("Error while learning command %s: %s", command, err)
            return

        if learned:
            self._commands[command] = [learned]
            _LOGGER.debug("Learned command %s: %s", command, learned)
        else:
            _LOGGER.warning("No IR code learned for %s", command)

    async def async_delete_command(self, **kwargs):
        command = kwargs.get("command")
        if command in self._commands:
            self._commands.pop(command)

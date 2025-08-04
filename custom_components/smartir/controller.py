"""Generic controller abstractions for SmartIR."""

from __future__ import annotations

from abc import ABC, abstractmethod
from base64 import b64encode
import binascii
import json
import logging
from typing import Any, Iterable, List

import requests

from homeassistant.core import HomeAssistant
from homeassistant.const import ATTR_ENTITY_ID

from . import Helper

_LOGGER = logging.getLogger(__name__)

BROADLINK_CONTROLLER = "Broadlink"
XIAOMI_CONTROLLER = "Xiaomi"
MQTT_CONTROLLER = "MQTT"
LOOKIN_CONTROLLER = "LOOKin"
ESPHOME_CONTROLLER = "ESPHome"
ZHA_CONTROLLER = "ZHA"

ENC_BASE64 = "Base64"
ENC_HEX = "Hex"
ENC_PRONTO = "Pronto"
ENC_RAW = "Raw"

BROADLINK_COMMANDS_ENCODING = (ENC_BASE64, ENC_HEX, ENC_PRONTO)
XIAOMI_COMMANDS_ENCODING = (ENC_PRONTO, ENC_RAW)
MQTT_COMMANDS_ENCODING = (ENC_RAW,)
LOOKIN_COMMANDS_ENCODING = (ENC_PRONTO, ENC_RAW)
ESPHOME_COMMANDS_ENCODING = (ENC_RAW,)
ZHA_COMMANDS_ENCODING = (ENC_BASE64, ENC_RAW)


def get_controller(
    hass: HomeAssistant,
    controller: str,
    encoding: str,
    controller_data: str,
    delay: float,
) -> "AbstractController":
    """Return a controller matching the given specification.

    Raises:
        ValueError: If the controller type is not supported.
    """
    controllers = {
        BROADLINK_CONTROLLER: BroadlinkController,
        XIAOMI_CONTROLLER: XiaomiController,
        MQTT_CONTROLLER: MQTTController,
        LOOKIN_CONTROLLER: LookinController,
        ESPHOME_CONTROLLER: ESPHomeController,
        ZHA_CONTROLLER: ZHAController,
    }

    try:
        cls = controllers[controller]
    except KeyError as exc:
        raise ValueError("The controller is not supported.") from exc

    return cls(hass, controller, encoding, controller_data, delay)


class AbstractController(ABC):
    """Base representation of a controller device."""

    supported_encodings: Iterable[str] = ()

    def __init__(
        self,
        hass: HomeAssistant,
        controller: str,
        encoding: str,
        controller_data: str,
        delay: float,
    ) -> None:
        self.hass = hass
        self._controller = controller
        self._encoding = encoding
        self._controller_data = controller_data
        self._delay = delay
        self.check_encoding(encoding)

    def check_encoding(self, encoding: str) -> None:
        """Ensure the controller supports the provided encoding."""
        if encoding not in self.supported_encodings:
            raise ValueError(
                f"The encoding is not supported by the {self._controller} controller."
            )

    @abstractmethod
    async def send(self, command: Any) -> None:
        """Send a command."""
        raise NotImplementedError


class BroadlinkController(AbstractController):
    """Controls a Broadlink device."""

    supported_encodings = BROADLINK_COMMANDS_ENCODING

    async def send(self, command: str | List[str]) -> None:
        """Send a command."""
        commands: List[str] = []

        if not isinstance(command, list):
            command = [command]

        for item in command:
            if self._encoding == ENC_HEX:
                try:
                    raw = binascii.unhexlify(item)
                except binascii.Error as exc:
                    raise ValueError(
                        "Error while converting Hex to Base64 encoding"
                    ) from exc
                item = b64encode(raw).decode("utf-8")
            elif self._encoding == ENC_PRONTO:
                try:
                    pronto = item.replace(" ", "")
                    pronto_bytes = bytearray.fromhex(pronto)
                    pronto_bytes = Helper.pronto2lirc(pronto_bytes)
                    pronto_bytes = Helper.lirc2broadlink(pronto_bytes)
                except (binascii.Error, ValueError) as exc:
                    raise ValueError(
                        "Error while converting Pronto to Base64 encoding"
                    ) from exc
                item = b64encode(pronto_bytes).decode("utf-8")

            commands.append("b64:" + item)

        service_data = {
            ATTR_ENTITY_ID: self._controller_data,
            "command": commands,
            "delay_secs": self._delay,
        }

        await self.hass.services.async_call(
            "remote", "send_command", service_data
        )


class XiaomiController(AbstractController):
    """Controls a Xiaomi device."""

    supported_encodings = XIAOMI_COMMANDS_ENCODING

    async def send(self, command: str) -> None:
        """Send a command."""
        service_data = {
            ATTR_ENTITY_ID: self._controller_data,
            "command": f"{self._encoding.lower()}:{command}",
        }

        await self.hass.services.async_call(
            "remote", "send_command", service_data
        )


class ZHAController(AbstractController):
    """Controls a ZHA device."""

    supported_encodings = ZHA_COMMANDS_ENCODING

    async def send(self, command: str) -> None:
        """Send a command."""
        service_data = {
            "cluster_type": "in",
            "endpoint_id": 1,
            "command": 2,
            "ieee": self._controller_data,
            "command_type": "server",
            "params": {"code": command},
            "cluster_id": 57348,
        }

        await self.hass.services.async_call(
            "zha", "issue_zigbee_cluster_command", service_data
        )


class MQTTController(AbstractController):
    """Controls a MQTT device."""

    supported_encodings = MQTT_COMMANDS_ENCODING

    async def send(self, command: str) -> None:
        """Send a command."""
        service_data = {"topic": self._controller_data, "payload": command}

        await self.hass.services.async_call(
            "mqtt", "publish", service_data
        )


class LookinController(AbstractController):
    """Controls a Lookin device."""

    supported_encodings = LOOKIN_COMMANDS_ENCODING

    async def send(self, command: str) -> None:
        """Send a command."""
        encoding = self._encoding.lower().replace("pronto", "prontohex")
        url = (
            f"http://{self._controller_data}/commands/ir/"
            f"{encoding}/{command}"
        )
        await self.hass.async_add_executor_job(requests.get, url)


class ESPHomeController(AbstractController):
    """Controls an ESPHome device."""

    supported_encodings = ESPHOME_COMMANDS_ENCODING

    async def send(self, command: str) -> None:
        """Send a command."""
        service_data = {"command": json.loads(command)}

        await self.hass.services.async_call(
            "esphome", self._controller_data, service_data
        )

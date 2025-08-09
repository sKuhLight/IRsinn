"""Generic controller abstractions for IRsinn."""

from __future__ import annotations

from abc import ABC, abstractmethod
from base64 import b64encode
import asyncio
import binascii
import json
import logging
import time
from typing import Any, Iterable, List

import requests

try:  # pragma: no cover - allows tests without Home Assistant
    from homeassistant.core import HomeAssistant
    from homeassistant.const import ATTR_ENTITY_ID
except Exception:  # pragma: no cover - Home Assistant not installed
    HomeAssistant = Any  # type: ignore[misc, assignment]
    ATTR_ENTITY_ID = "entity_id"

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

    async def learn(self) -> str | None:  # pragma: no cover - default implementation
        """Learn a command from the device.

        Controllers that support learning should override this method.
        """
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

    async def learn(self, timeout: int = 30) -> str | None:
        """Learn an IR command via ZHA."""

        async def _read_code() -> str | None:
            read_data = {
                "cluster_type": "in",
                "endpoint_id": 1,
                "ieee": self._controller_data,
                "cluster_id": 57348,
                "attribute": 0,
                "allow_cache": False,
            }
            try:
                resp = await self.hass.services.async_call(
                    "zha",
                    "get_zigbee_cluster_attribute",
                    read_data,
                    blocking=True,
                    return_response=True,
                )
            except Exception as err:  # pragma: no cover - depends on HA
                _LOGGER.debug("Failed to read attribute: %s", err)
                return None
            _LOGGER.debug("Attribute read response: %s", resp)
            if isinstance(resp, dict):
                if "value" in resp:
                    return resp.get("value")
                val = resp.get("0")
                if isinstance(val, dict):
                    return val.get("value")
                return val
            return None

        initial_code = await _read_code()
        _LOGGER.debug("Initial learned code: %s", initial_code)

        learn_data = {
            "cluster_type": "in",
            "endpoint_id": 1,
            "command": 1,
            "ieee": self._controller_data,
            "command_type": "server",
            # quirk expects lowercase string values
            "params": {"on_off": "true"},
            "cluster_id": 57348,
        }
        await self.hass.services.async_call(
            "zha", "issue_zigbee_cluster_command", learn_data
        )
        _LOGGER.debug("Sent learn mode command")

        end = time.monotonic() + timeout
        while time.monotonic() < end:
            await asyncio.sleep(1)
            code = await _read_code()
            _LOGGER.debug("Polled learned code: %s", code)
            if code and code != initial_code:
                _LOGGER.debug("Received new IR code: %s", code)
                # exit learn mode
                exit_data = {
                    "cluster_type": "in",
                    "endpoint_id": 1,
                    "command": 0,
                    "ieee": self._controller_data,
                    "command_type": "server",
                    # the quirk expects a JSON string payload
                    "params": {"data": json.dumps({"study": 1})},
                    "cluster_id": 57348,
                }
                try:
                    _LOGGER.debug("Exiting learn mode")
                    await self.hass.services.async_call(
                        "zha", "issue_zigbee_cluster_command", exit_data
                    )
                except Exception as err:  # pragma: no cover - depends on HA
                    _LOGGER.debug("Failed to exit learn mode: %s", err)
                return code

        _LOGGER.debug("Timed out waiting for learned IR code")
        # make a best effort to exit learn mode
        try:
            _LOGGER.debug("Exiting learn mode after timeout")
            await self.hass.services.async_call(
                "zha",
                "issue_zigbee_cluster_command",
                {
                    "cluster_type": "in",
                    "endpoint_id": 1,
                    "command": 0,
                    "ieee": self._controller_data,
                    "command_type": "server",
                    "params": {"data": json.dumps({"study": 1})},
                    "cluster_id": 57348,
                },
            )
        except Exception as err:  # pragma: no cover - depends on HA
            _LOGGER.debug("Failed to exit learn mode after timeout: %s", err)
        return None


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

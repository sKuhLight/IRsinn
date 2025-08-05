"""IRsinn component helpers and setup."""

from __future__ import annotations

import aiofiles
import aiohttp
import binascii
from distutils.version import StrictVersion
import json
import logging
import os.path
import struct
from typing import Any

import voluptuous as vol
from homeassistant.const import __version__ as current_ha_version
from homeassistant.core import HomeAssistant, ServiceCall
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .storage_manager import StorageManager

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'irsinn'
VERSION = '1.19.0'
MANIFEST_URL = (
    "https://raw.githubusercontent.com/"
    "sKuhLight/IRsinn/{}/"
    "custom_components/irsinn/manifest.json")
REMOTE_BASE_URL = (
    "https://raw.githubusercontent.com/"
    "sKuhLight/IRsinn/{}/"
    "custom_components/irsinn/")
COMPONENT_ABS_DIR = os.path.dirname(
    os.path.abspath(__file__))

CONF_CHECK_UPDATES = 'check_updates'
CONF_UPDATE_BRANCH = 'update_branch'
CONF_ENTITY_TYPE = 'entity_type'

PLATFORMS = ["remote", "climate", "fan", "light", "media_player"]

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_CHECK_UPDATES, default=True): cv.boolean,
                vol.Optional(CONF_UPDATE_BRANCH, default="master"): vol.In(
                    ["master", "rc"]
                ),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the IRsinn component."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["storage"] = StorageManager(hass)
    hass.data[DOMAIN]["entities"] = {}

    conf = config.get(DOMAIN)

    if conf is None:
        conf = {}

    check_updates = conf.get(CONF_CHECK_UPDATES, True)
    update_branch = conf.get(CONF_UPDATE_BRANCH, "master")

    async def _check_updates(service):
        await _update(hass, update_branch)

    async def _update_component(service):
        await _update(hass, update_branch, True)

    hass.services.async_register(DOMAIN, 'check_updates', _check_updates)
    hass.services.async_register(DOMAIN, 'update_component', _update_component)

    async def _learn_command(call: ServiceCall):
        entity = hass.data[DOMAIN]["entities"].get(call.data["entity_id"])
        if entity:
            await entity.async_learn_command(command=call.data.get("key"))

    async def _save_command(call: ServiceCall):
        entity = hass.data[DOMAIN]["entities"].get(call.data["entity_id"])
        if entity:
            entity._commands[call.data["key"]] = call.data["code"]
            await entity._storage.async_save_command(
                "remote", entity._device_code, call.data["key"], call.data["code"]
            )

    async def _delete_command(call: ServiceCall):
        entity = hass.data[DOMAIN]["entities"].get(call.data["entity_id"])
        if entity:
            entity._commands.pop(call.data["key"], None)
            await entity._storage.async_delete_command(
                "remote", entity._device_code, call.data["key"]
            )

    async def _test_command(call: ServiceCall):
        entity = hass.data[DOMAIN]["entities"].get(call.data["entity_id"])
        if entity:
            await entity._backend.async_send(call.data["code"])

    hass.services.async_register(
        DOMAIN,
        "learn_command",
        _learn_command,
        schema=vol.Schema({"entity_id": cv.entity_id, "key": cv.string}),
    )
    hass.services.async_register(
        DOMAIN,
        "save_command",
        _save_command,
        schema=vol.Schema(
            {"entity_id": cv.entity_id, "key": cv.string, "code": cv.string}
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "delete_command",
        _delete_command,
        schema=vol.Schema({"entity_id": cv.entity_id, "key": cv.string}),
    )
    hass.services.async_register(
        DOMAIN,
        "test_command",
        _test_command,
        schema=vol.Schema({"entity_id": cv.entity_id, "code": cv.string}),
    )

    if check_updates:
        await _update(hass, update_branch, False, False)

    return True


async def async_setup_entry(hass: HomeAssistant, entry) -> bool:
    """Set up IRsinn from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("storage", StorageManager(hass))
    hass.data[DOMAIN].setdefault("entities", {})
    platform = entry.data.get(CONF_ENTITY_TYPE, "remote")
    await hass.config_entries.async_forward_entry_setups(entry, [platform])
    return True


async def async_unload_entry(hass: HomeAssistant, entry) -> bool:
    platform = entry.data.get(CONF_ENTITY_TYPE, "remote")
    return await hass.config_entries.async_unload_platforms(entry, [platform])


async def async_get_device_config(domain: str, device_code: int) -> dict[str, Any]:
    """Load the device configuration for the given domain and code."""
    device_files_subdir = os.path.join("codes", domain)
    device_files_absdir = os.path.join(COMPONENT_ABS_DIR, device_files_subdir)
    os.makedirs(device_files_absdir, exist_ok=True)

    device_json_path = os.path.join(
        device_files_absdir, f"{device_code}.json"
    )

    if not os.path.exists(device_json_path):
        _LOGGER.warning(
            "Couldn't find the device Json file. The component will try to download it from the GitHub repo."
        )
        codes_source = (
            "https://raw.githubusercontent.com/"
            "sKuhLight/IRsinn/master/"
            f"codes/{domain}/{device_code}.json"
        )
        try:
            await Helper.downloader(codes_source, device_json_path)
        except Exception as exc:
            _LOGGER.error(
                "There was an error while downloading the device Json file.",
                exc_info=exc,
            )
            raise

    async with aiofiles.open(device_json_path, mode="r") as file:
        return json.loads(await file.read())


async def _update(
    hass: HomeAssistant,
    branch: str,
    do_update: bool = False,
    notify_if_latest: bool = True,
) -> None:
    """Check for and optionally perform component updates."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(MANIFEST_URL.format(branch)) as response:
                if response.status != 200:
                    return

                data = await response.json(content_type="text/plain")
                min_ha_version = data["homeassistant"]
                last_version = data["updater"]["version"]
                release_notes = data["updater"]["releaseNotes"]

                if StrictVersion(last_version) <= StrictVersion(VERSION):
                    if notify_if_latest:
                        hass.components.persistent_notification.async_create(
                            "You're already using the latest version!", title="IRsinn"
                        )
                    return

                if StrictVersion(current_ha_version) < StrictVersion(min_ha_version):
                    hass.components.persistent_notification.async_create(
                        "There is a new version of IRsinn integration, but it is **incompatible** "
                        "with your system. Please first update Home Assistant.",
                        title="IRsinn",
                    )
                    return

                if not do_update:
                    hass.components.persistent_notification.async_create(
                        "A new version of IRsinn integration is available ({}). "
                        "Call the ``irsinn.update_component`` service to update "
                        "the integration. \n\n **Release notes:** \n{}".format(
                            last_version, release_notes
                        ),
                        title="IRsinn",
                    )
                    return

                files = data["updater"]["files"]
                has_errors = False

                for file in files:
                    try:
                        source = REMOTE_BASE_URL.format(branch) + file
                        dest = os.path.join(COMPONENT_ABS_DIR, file)
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        await Helper.downloader(source, dest)
                    except Exception:
                        has_errors = True
                        _LOGGER.error(
                            "Error updating %s. Please update the file manually.", file
                        )

                if has_errors:
                    hass.components.persistent_notification.async_create(
                        "There was an error updating one or more files of IRsinn. "
                        "Please check the logs for more information.",
                        title="IRsinn",
                    )
                else:
                    hass.components.persistent_notification.async_create(
                        "Successfully updated to {}. Please restart Home Assistant.".format(
                            last_version
                        ),
                        title="IRsinn",
                    )
    except Exception:
        _LOGGER.error("An error occurred while checking for updates.")

class Helper:
    """Collection of helper methods for IR code manipulation."""

    @staticmethod
    async def downloader(source: str, dest: str) -> None:
        """Download a file from ``source`` to ``dest`` asynchronously."""
        async with aiohttp.ClientSession() as session:
            async with session.get(source) as response:
                if response.status != 200:
                    raise FileNotFoundError(source)
                async with aiofiles.open(dest, mode="wb") as file:
                    await file.write(await response.read())

    @staticmethod
    def pronto2lirc(pronto: bytes) -> list[int]:
        """Convert a Pronto code to a list of LIRC pulse widths."""
        codes = [int(binascii.hexlify(pronto[i : i + 2]), 16) for i in range(0, len(pronto), 2)]

        if codes[0]:
            raise ValueError("Pronto code should start with 0000")
        if len(codes) != 4 + 2 * (codes[2] + codes[3]):
            raise ValueError("Number of pulse widths does not match the preamble")

        frequency = 1 / (codes[1] * 0.241246)
        return [int(round(code / frequency)) for code in codes[4:]]

    @staticmethod
    def lirc2broadlink(pulses: list[int]) -> bytearray:
        """Convert LIRC pulses to Broadlink packet format."""
        array = bytearray()
        for pulse in pulses:
            pulse = int(pulse * 269 / 8192)
            if pulse < 256:
                array += bytearray(struct.pack(">B", pulse))
            else:
                array += bytearray([0x00])
                array += bytearray(struct.pack(">H", pulse))

        packet = bytearray([0x26, 0x00])
        packet += bytearray(struct.pack("<H", len(array)))
        packet += array
        packet += bytearray([0x0D, 0x05])

        # Pad packet size to multiple of 16 bytes for 128-bit AES encryption.
        remainder = (len(packet) + 4) % 16
        if remainder:
            packet += bytearray(16 - remainder)
        return packet

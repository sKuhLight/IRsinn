"""Handle layered configuration for IRsinn commands."""

from __future__ import annotations

from typing import Any, Dict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store


STORAGE_KEY = "irsinn_overrides"


class StorageManager:
    """Merge default codes with user overrides."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store = Store(hass, 1, STORAGE_KEY)

    async def async_load_device(self, domain: str, device_code: int) -> Dict[str, Any]:
        """Load device configuration with overrides applied."""
        from . import async_get_device_config  # avoid circular import

        defaults = await async_get_device_config(domain, device_code)
        overrides = await self._store.async_load() or {}
        domain_data = overrides.get(domain, {})
        device_override = domain_data.get(str(device_code), {})
        commands = {**defaults.get("commands", {}), **device_override.get("commands", {})}
        result = defaults.copy()
        result["commands"] = commands
        return result

    async def async_save_command(
        self, domain: str, device_code: int, key: str, value: str
    ) -> None:
        data = await self._store.async_load() or {}
        domain_data = data.setdefault(domain, {})
        device_data = domain_data.setdefault(str(device_code), {"commands": {}})
        device_data["commands"][key] = value
        await self._store.async_save(data)

    async def async_delete_command(
        self, domain: str, device_code: int, key: str
    ) -> None:
        data = await self._store.async_load() or {}
        try:
            commands = data[domain][str(device_code)]["commands"]
        except KeyError:
            return
        commands.pop(key, None)
        await self._store.async_save(data)

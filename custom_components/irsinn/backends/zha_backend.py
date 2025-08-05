"""ZHA backend implementation for IRsinn."""

from __future__ import annotations

from homeassistant.helpers.device_registry import async_get as async_get_dr

from . import IRBackend, register_backend

ZHA_CLUSTER_ID = 0xE004  # cluster used for IR commands
ZHA_COMMAND_ID = 2


class ZhaBackend(IRBackend):
    """Backend that sends commands via ZHA."""

    async def async_send(self, command: str) -> None:
        service_data = {
            "cluster_type": "in",
            "endpoint_id": 1,
            "command": ZHA_COMMAND_ID,
            "ieee": self._controller_data,
            "command_type": "server",
            "params": {"code": command},
            "cluster_id": ZHA_CLUSTER_ID,
        }
        await self.hass.services.async_call(
            "zha", "issue_zigbee_cluster_command", service_data
        )

    @classmethod
    async def async_controller_options(cls, hass):
        """Return available ZHA devices for selection."""
        registry = async_get_dr(hass)
        controllers: dict[str, str] = {}
        for device in registry.devices.values():
            for domain, ident in device.identifiers:
                if domain == "zha":
                    controllers[ident] = device.name or ident
        return controllers


register_backend("zha", ZhaBackend)

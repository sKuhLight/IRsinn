"""ZHA backend implementation for IRsinn."""

from __future__ import annotations

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


register_backend("zha", ZhaBackend)

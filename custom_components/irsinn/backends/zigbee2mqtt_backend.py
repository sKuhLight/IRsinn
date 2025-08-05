"""Zigbee2MQTT backend stub."""

from __future__ import annotations

from . import IRBackend, register_backend


class Zigbee2MQTTBackend(IRBackend):
    """Backend placeholder for Zigbee2MQTT."""

    async def async_send(self, command: str) -> None:
        topic = f"{self._controller_data}/set"
        await self.hass.services.async_call(
            "mqtt", "publish", {"topic": topic, "payload": command}
        )

    @classmethod
    async def async_controller_options(cls, hass):  # pragma: no cover - stub
        """Return discovered MQTT topics, if any."""
        return {}


register_backend("zigbee2mqtt", Zigbee2MQTTBackend)

"""Backend interface and factory for IRsinn."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Type

from homeassistant.core import HomeAssistant

SUPPORTED_BACKENDS: Dict[str, Type["IRBackend"]] = {}


class IRBackend(ABC):
    """Abstract backend used by IRsinn to send and learn IR commands."""

    def __init__(self, hass: HomeAssistant, controller_data: str, delay: float) -> None:
        self.hass = hass
        self._controller_data = controller_data
        self._delay = delay

    @abstractmethod
    async def async_send(self, command: str) -> None:
        """Send a command to the backend."""

    async def async_learn(self) -> str | None:  # pragma: no cover - backend optional
        """Learn a command from the backend."""
        return None


def register_backend(name: str, backend: Type[IRBackend]) -> None:
    """Register a backend implementation."""
    SUPPORTED_BACKENDS[name] = backend


def get_backend(
    hass: HomeAssistant, name: str, controller_data: str, delay: float
) -> IRBackend:
    """Return an instance of a registered backend."""
    backend_cls = SUPPORTED_BACKENDS.get(name)
    if backend_cls is None:
        raise ValueError(f"Backend {name} not supported")
    return backend_cls(hass, controller_data, delay)


# Import built-in backends so they register on import
from . import zha_backend  # noqa: F401
from . import zigbee2mqtt_backend  # noqa: F401

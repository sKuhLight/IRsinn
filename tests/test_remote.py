import types
import pathlib
import sys
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "custom_components"))
from irsinn.remote import IRsinnRemote, CONF_BACKEND


class DummyBackend:
    def __init__(self):
        self.sent = []

    async def async_send(self, command):
        self.sent.append(command)


class DummyStorage:
    async def async_save_command(self, *args, **kwargs):
        return None

    async def async_delete_command(self, *args, **kwargs):
        return None


@pytest.mark.asyncio
async def test_send_and_power(monkeypatch):
    hass = types.SimpleNamespace()
    config = {
        "name": "Test Remote",
        "device_code": 1000,
        "controller_data": "dummy",
        "delay": 0,
        CONF_BACKEND: "dummy",
    }
    device_data = {
        "manufacturer": "Generic",
        "supportedModels": ["Demo Remote"],
        "supportedController": "Broadlink",
        "commandsEncoding": "Base64",
        "commands": {
            "turn_on": "on_cmd",
            "turn_off": "off_cmd",
            "volume_up": "vol_up_cmd",
        },
    }

    dummy = DummyBackend()
    storage = DummyStorage()

    entity = IRsinnRemote(hass, config, device_data, dummy, storage)

    # Avoid Home Assistant state machine requirements in tests
    entity.async_write_ha_state = lambda: None

    await entity.async_send_command(["volume_up"])
    assert dummy.sent == ["vol_up_cmd"]

    await entity.async_turn_on()
    assert entity.is_on

    await entity.async_turn_off()
    assert not entity.is_on

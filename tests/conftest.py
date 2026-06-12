"""Shared pytest fixtures for migros_list tests."""
from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest


def _make_ha_stubs() -> None:
    """Inject minimal homeassistant stubs so the custom component can be imported."""
    if "homeassistant" in sys.modules:
        return

    ha = types.ModuleType("homeassistant")
    ha.core = types.ModuleType("homeassistant.core")
    ha.core.HomeAssistant = object

    ha.const = types.ModuleType("homeassistant.const")
    ha.const.Platform = MagicMock()
    ha.const.CONF_ACCESS_TOKEN = "access_token"

    ha.config_entries = types.ModuleType("homeassistant.config_entries")
    ha.config_entries.ConfigEntry = object

    class _ConfigFlow:
        """Stub ConfigFlow that accepts domain= keyword in subclass declaration."""
        def __init_subclass__(cls, domain: str = "", **kwargs):
            super().__init_subclass__(**kwargs)

    ha.config_entries.ConfigFlow = _ConfigFlow
    ha.config_entries.OptionsFlow = object

    ha.exceptions = types.ModuleType("homeassistant.exceptions")
    ha.exceptions.ConfigEntryNotReady = Exception

    ha.helpers = types.ModuleType("homeassistant.helpers")
    ha.helpers.aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")
    ha.helpers.aiohttp_client.async_get_clientsession = MagicMock()

    ha.helpers.update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")

    class _GenericCoordinator:
        """Stub that supports DataUpdateCoordinator[X] subscript syntax."""
        def __class_getitem__(cls, item):
            return cls

    ha.helpers.update_coordinator.DataUpdateCoordinator = _GenericCoordinator
    ha.helpers.update_coordinator.UpdateFailed = Exception

    ha.data_entry_flow = types.ModuleType("homeassistant.data_entry_flow")
    ha.data_entry_flow.FlowResult = dict

    for name in [
        "homeassistant",
        "homeassistant.core",
        "homeassistant.const",
        "homeassistant.config_entries",
        "homeassistant.exceptions",
        "homeassistant.helpers",
        "homeassistant.helpers.aiohttp_client",
        "homeassistant.helpers.update_coordinator",
        "homeassistant.data_entry_flow",
    ]:
        sys.modules.setdefault(name, getattr(ha, name.removeprefix("homeassistant."), ha))

    # Fix top-level mapping
    sys.modules["homeassistant"] = ha
    sys.modules["homeassistant.core"] = ha.core
    sys.modules["homeassistant.const"] = ha.const
    sys.modules["homeassistant.config_entries"] = ha.config_entries
    sys.modules["homeassistant.exceptions"] = ha.exceptions
    sys.modules["homeassistant.helpers"] = ha.helpers
    sys.modules["homeassistant.helpers.aiohttp_client"] = ha.helpers.aiohttp_client
    sys.modules["homeassistant.helpers.update_coordinator"] = ha.helpers.update_coordinator
    sys.modules["homeassistant.data_entry_flow"] = ha.data_entry_flow


# Run before any imports of the custom component
_make_ha_stubs()


@pytest.fixture
async def hass():
    """Return a minimal hass-like object; patches async_get_clientsession in api.py."""
    session = aiohttp.ClientSession()
    with patch(
        "custom_components.migros_list.api.async_get_clientsession",
        return_value=session,
    ):
        yield MagicMock()
    await session.close()


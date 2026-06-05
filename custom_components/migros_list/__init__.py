from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .api import MigrosApiAuthError, MigrosApiClient, MigrosApiError
from .const import CONF_ACCESS_TOKEN, CONF_LIST_ID, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL, DOMAIN
from .coordinator import MigrosDataUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON]


@dataclass(slots=True)
class MigrosRuntimeData:
    client: MigrosApiClient
    coordinator: MigrosDataUpdateCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = MigrosApiClient(
        access_token=entry.data[CONF_ACCESS_TOKEN],
        shopping_list_id=str(entry.data[CONF_LIST_ID]),
    )
    coordinator = MigrosDataUpdateCoordinator(
        hass=hass,
        client=client,
        update_interval=timedelta(
            minutes=entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        ),
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except MigrosApiAuthError as err:
        raise ConfigEntryNotReady("Migros authentication failed") from err
    except MigrosApiError as err:
        raise ConfigEntryNotReady("Migros API is unavailable") from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = MigrosRuntimeData(
        client=client,
        coordinator=coordinator,
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
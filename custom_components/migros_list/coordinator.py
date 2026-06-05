from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MigrosApiAuthError, MigrosApiClient, MigrosApiError
from .const import DOMAIN
from .models import MigrosShoppingList


class MigrosDataUpdateCoordinator(DataUpdateCoordinator[MigrosShoppingList]):
    def __init__(
        self,
        hass: HomeAssistant,
        client: MigrosApiClient,
        update_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            logger=__import__("logging").getLogger(__name__),
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.client = client

    async def _async_update_data(self) -> MigrosShoppingList:
        try:
            return await self.client.async_get_shopping_list(self.hass)
        except MigrosApiAuthError as err:
            raise UpdateFailed("Authentication failed") from err
        except MigrosApiError as err:
            raise UpdateFailed(str(err)) from err
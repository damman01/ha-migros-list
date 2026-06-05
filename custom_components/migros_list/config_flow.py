from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.data_entry_flow import FlowResult

from .api import MigrosApiAuthError, MigrosApiClient, MigrosApiError
from .const import CONF_LIST_ID, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL, DOMAIN


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_LIST_ID): str,
        vol.Required(CONF_ACCESS_TOKEN): str,
    }
)


class MigrosConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            list_id = user_input[CONF_LIST_ID].strip()
            token = user_input[CONF_ACCESS_TOKEN].strip()

            await self.async_set_unique_id(list_id)
            self._abort_if_unique_id_configured()

            errors = await self._validate_input(list_id, token)
            if not errors:
                return self.async_create_entry(
                    title=f"Migros {list_id}",
                    data={
                        CONF_LIST_ID: list_id,
                        CONF_ACCESS_TOKEN: token,
                    },
                    options={CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        self.context["entry_id"] = self._get_reauth_entry().entry_id
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            token = user_input[CONF_ACCESS_TOKEN].strip()
            errors = await self._validate_input(str(entry.data[CONF_LIST_ID]), token)
            if not errors:
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={**entry.data, CONF_ACCESS_TOKEN: token},
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_ACCESS_TOKEN): str}),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return MigrosOptionsFlow(config_entry)

    async def _validate_input(self, list_id: str, token: str) -> dict[str, str]:
        client = MigrosApiClient(access_token=token, shopping_list_id=list_id)
        try:
            await client.async_get_shopping_list(self.hass)
        except MigrosApiAuthError:
            return {"base": "invalid_auth"}
        except MigrosApiError:
            return {"base": "cannot_connect"}
        except Exception:
            return {"base": "unknown"}
        return {}


class MigrosOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_UPDATE_INTERVAL,
                        default=self._entry.options.get(
                            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=240))
                }
            ),
        )
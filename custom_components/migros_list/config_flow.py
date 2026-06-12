from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.data_entry_flow import FlowResult

from .api import MigrosApiAuthError, MigrosApiClient, MigrosApiError, MigrosApiHttpError
from .const import (
    CONF_LIST_ID,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MIGROS_SHOPPING_LIST_URL,
)

_STEP_TOKEN_SCHEMA = vol.Schema({vol.Required(CONF_ACCESS_TOKEN): str})


class MigrosConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._token: str = ""
        self._available_lists: dict[str, str] = {}  # id -> name

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input[CONF_ACCESS_TOKEN].strip()
            if not token:
                errors["base"] = "empty_access_token"
            else:
                client = MigrosApiClient(access_token=token)
                try:
                    await client.async_validate_token(self.hass)
                except MigrosApiAuthError:
                    errors["base"] = "invalid_auth"
                except MigrosApiError:
                    errors["base"] = "cannot_connect"
                except Exception:
                    errors["base"] = "unknown"
                else:
                    # Token valid; fetch available lists (best-effort, falls back to text input)
                    try:
                        lists = await client.async_get_lists_overview(self.hass)
                    except MigrosApiError:
                        lists = []
                    self._token = token
                    self._available_lists = {entry["id"]: entry["name"] for entry in lists}
                    return await self.async_step_select_list()

        return self.async_show_form(
            step_id="user",
            data_schema=_STEP_TOKEN_SCHEMA,
            errors=errors,
            description_placeholders={"shopping_list_url": MIGROS_SHOPPING_LIST_URL},
        )

    async def async_step_select_list(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            list_id = user_input[CONF_LIST_ID]
            if isinstance(list_id, str):
                list_id = list_id.strip()

            if self._available_lists:
                list_name = self._available_lists[list_id]
            else:
                # Manual ID entry — validate by fetching the list
                client = MigrosApiClient(access_token=self._token, shopping_list_id=list_id)
                try:
                    shopping_list = await client.async_get_shopping_list(self.hass)
                    list_name = shopping_list.name
                except MigrosApiAuthError:
                    errors["base"] = "invalid_auth"
                except MigrosApiHttpError as err:
                    if err.status_code == 404:
                        errors["base"] = "invalid_list_id"
                    elif err.status_code == 429:
                        errors["base"] = "rate_limited"
                    else:
                        errors["base"] = "cannot_connect"
                except MigrosApiError:
                    errors["base"] = "cannot_connect"
                except Exception:
                    errors["base"] = "unknown"

                if errors:
                    return self.async_show_form(
                        step_id="select_list",
                        data_schema=vol.Schema({vol.Required(CONF_LIST_ID): str}),
                        errors=errors,
                    )

            await self.async_set_unique_id(list_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=list_name,
                data={
                    CONF_LIST_ID: list_id,
                    CONF_ACCESS_TOKEN: self._token,
                },
                options={CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL},
            )

        if self._available_lists:
            schema = vol.Schema({vol.Required(CONF_LIST_ID): vol.In(self._available_lists)})
        else:
            schema = vol.Schema({vol.Required(CONF_LIST_ID): str})

        return self.async_show_form(
            step_id="select_list",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            token = user_input[CONF_ACCESS_TOKEN].strip()
            errors = await self._validate_token(str(entry.data[CONF_LIST_ID]), token)
            if not errors:
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={**entry.data, CONF_ACCESS_TOKEN: token},
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_STEP_TOKEN_SCHEMA,
            errors=errors,
            description_placeholders={"shopping_list_url": MIGROS_SHOPPING_LIST_URL},
        )

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return MigrosOptionsFlow(config_entry)

    async def _validate_token(self, list_id: str, token: str) -> dict[str, str]:
        if not token:
            return {"base": "empty_access_token"}

        client = MigrosApiClient(access_token=token, shopping_list_id=list_id)
        try:
            await client.async_get_shopping_list(self.hass)
        except MigrosApiAuthError:
            return {"base": "invalid_auth"}
        except MigrosApiHttpError as err:
            if err.status_code == 404:
                return {"base": "invalid_list_id"}
            if err.status_code == 429:
                return {"base": "rate_limited"}
            return {"base": "cannot_connect"}
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
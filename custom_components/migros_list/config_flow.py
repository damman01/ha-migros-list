from __future__ import annotations

import logging
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

_LOGGER = logging.getLogger(__name__)

_STEP_TOKEN_SCHEMA = vol.Schema({vol.Required(CONF_ACCESS_TOKEN): str})


class MigrosConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._token: str = ""          # normalized (Bearer prefix stripped)
        self._available_lists: dict[str, str] = {}  # id -> name

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input[CONF_ACCESS_TOKEN].strip()
            if not token:
                errors["base"] = "empty_access_token"
            else:
                # Normalize once up front; store the clean token, not the raw input.
                client = MigrosApiClient(access_token=token)
                normalized = client._access_token
                _LOGGER.debug(
                    "Config flow: token provided (length=%d, prefix=%s...)",
                    len(normalized),
                    normalized[:12],
                )

                # Step 1: Validate token via OIDC userinfo (works with Bearer token alone).
                _LOGGER.debug("Config flow: validating token via OIDC userinfo")
                try:
                    await client.async_validate_token(self.hass)
                    _LOGGER.debug("Config flow: token validated successfully")
                except MigrosApiAuthError as err:
                    _LOGGER.warning(
                        "Config flow: token rejected by userinfo endpoint: %s (cause: %s)",
                        err,
                        err.__cause__,
                    )
                    errors["base"] = "invalid_auth"
                except MigrosApiError as err:
                    _LOGGER.warning(
                        "Config flow: could not reach auth server: %s (cause: %s)",
                        err,
                        err.__cause__,
                    )
                    errors["base"] = "cannot_connect"
                except Exception as err:
                    _LOGGER.exception("Config flow: unexpected error during token validation")
                    errors["base"] = "unknown"

                if not errors:
                    # Step 2: Fetch available lists (best-effort; may fail if cookies are
                    # required by the overview endpoint). Any failure → text input fallback.
                    _LOGGER.debug("Config flow: fetching shopping lists overview")
                    try:
                        lists = await client.async_get_lists_overview(self.hass)
                        _LOGGER.debug(
                            "Config flow: found %d list(s): %s",
                            len(lists),
                            [f"{l['name']} ({l['id']})" for l in lists],
                        )
                    except Exception as err:
                        _LOGGER.debug(
                            "Config flow: overview fetch failed (%s: %s) — falling back to manual list ID entry",
                            type(err).__name__,
                            err,
                        )
                        lists = []

                    self._token = normalized
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

            _LOGGER.debug("Config flow: list selected: %s", list_id)

            if self._available_lists:
                list_name = self._available_lists[list_id]
                _LOGGER.debug("Config flow: resolved list name from dropdown: %s", list_name)
            else:
                # Manual ID entry — validate by fetching the list
                _LOGGER.debug("Config flow: no dropdown available, validating list ID %s via API", list_id)
                client = MigrosApiClient(access_token=self._token, shopping_list_id=list_id)
                try:
                    shopping_list = await client.async_get_shopping_list(self.hass)
                    list_name = shopping_list.name
                    _LOGGER.debug("Config flow: list validated, name=%s", list_name)
                except MigrosApiAuthError as err:
                    _LOGGER.warning(
                        "Config flow: auth error during list validation: %s (cause: %s)",
                        err,
                        err.__cause__,
                    )
                    errors["base"] = "invalid_auth"
                except MigrosApiHttpError as err:
                    _LOGGER.warning(
                        "Config flow: HTTP %s fetching list %s (cause: %s)",
                        err.status_code,
                        list_id,
                        err.__cause__,
                    )
                    if err.status_code == 404:
                        errors["base"] = "invalid_list_id"
                    elif err.status_code == 429:
                        errors["base"] = "rate_limited"
                    else:
                        errors["base"] = "cannot_connect"
                except MigrosApiError as err:
                    _LOGGER.warning(
                        "Config flow: API error during list validation: %s (cause: %s)",
                        err,
                        err.__cause__,
                    )
                    errors["base"] = "cannot_connect"
                except Exception as err:
                    _LOGGER.exception("Config flow: unexpected error during list validation")
                    errors["base"] = "unknown"

                if errors:
                    return self.async_show_form(
                        step_id="select_list",
                        data_schema=vol.Schema({vol.Required(CONF_LIST_ID): str}),
                        errors=errors,
                    )

            await self.async_set_unique_id(list_id)
            self._abort_if_unique_id_configured()

            _LOGGER.info("Config flow: creating entry for list '%s' (id=%s)", list_name, list_id)
            return self.async_create_entry(
                title=list_name,
                data={
                    CONF_LIST_ID: list_id,
                    CONF_ACCESS_TOKEN: self._token,
                },
                options={CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL},
            )

        mode = "dropdown" if self._available_lists else "text input"
        _LOGGER.debug("Config flow: showing select_list form (mode=%s, %d list(s))", mode, len(self._available_lists))
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
        _LOGGER.debug("Config flow: starting reauth for entry %s", self.context.get("entry_id"))
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            token = user_input[CONF_ACCESS_TOKEN].strip()
            _LOGGER.debug("Config flow: reauth token provided for list %s", entry.data.get(CONF_LIST_ID))
            errors = await self._validate_token(str(entry.data[CONF_LIST_ID]), token)
            if not errors:
                _LOGGER.info(
                    "Config flow: reauth successful for list %s, reloading entry",
                    entry.data.get(CONF_LIST_ID),
                )
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={**entry.data, CONF_ACCESS_TOKEN: token},
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")
            else:
                _LOGGER.warning("Config flow: reauth failed: %s", errors)

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

        _LOGGER.debug("Config flow: validating token for list %s", list_id)
        client = MigrosApiClient(access_token=token, shopping_list_id=list_id)
        try:
            await client.async_get_shopping_list(self.hass)
            _LOGGER.debug("Config flow: token validation successful for list %s", list_id)
        except MigrosApiAuthError as err:
            _LOGGER.warning(
                "Config flow: token rejected for list %s: %s (cause: %s)",
                list_id,
                err,
                err.__cause__,
            )
            return {"base": "invalid_auth"}
        except MigrosApiHttpError as err:
            _LOGGER.warning(
                "Config flow: HTTP %s validating list %s (cause: %s)",
                err.status_code,
                list_id,
                err.__cause__,
            )
            if err.status_code == 404:
                return {"base": "invalid_list_id"}
            if err.status_code == 429:
                return {"base": "rate_limited"}
            return {"base": "cannot_connect"}
        except MigrosApiError as err:
            _LOGGER.warning(
                "Config flow: API error validating list %s: %s (cause: %s)",
                list_id,
                err,
                err.__cause__,
            )
            return {"base": "cannot_connect"}
        except Exception as err:
            _LOGGER.exception("Config flow: unexpected error validating list %s", list_id)
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
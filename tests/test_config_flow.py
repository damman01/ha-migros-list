"""Tests for MigrosConfigFlow."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.migros_list.config_flow import MigrosConfigFlow
from custom_components.migros_list.api import MigrosApiAuthError, MigrosApiError
from custom_components.migros_list.const import (
    CONF_LIST_ID,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
)

VALID_TOKEN = "eyJhbGciOiJSUzI1NiJ9.test.sig"
BEARER_JSON = f'{{"accessToken": "Bearer {VALID_TOKEN}"}}'

LISTS = [
    {"id": "346969", "name": "Einkaufsliste"},
    {"id": "346936", "name": "Tischgrill"},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_flow(hass=None):
    flow = MigrosConfigFlow()
    flow.hass = hass or MagicMock()
    flow.context = {}
    flow.async_set_unique_id = AsyncMock(return_value=None)
    flow._abort_if_unique_id_configured = MagicMock()
    flow.async_show_form = MagicMock(side_effect=lambda **kw: {"type": "form", **kw})
    flow.async_create_entry = MagicMock(side_effect=lambda **kw: {"type": "create_entry", **kw})
    flow.async_abort = MagicMock(side_effect=lambda **kw: {"type": "abort", **kw})
    return flow


# ---------------------------------------------------------------------------
# async_step_user — token entry step
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_step_shows_form_initially():
    flow = _make_flow()
    result = await flow.async_step_user(None)
    assert result["type"] == "form"
    assert result["step_id"] == "user"
    assert not result.get("errors")


@pytest.mark.asyncio
async def test_user_step_empty_token_shows_error():
    flow = _make_flow()
    result = await flow.async_step_user({"access_token": "  "})
    assert result["type"] == "form"
    assert result["errors"]["base"] == "empty_access_token"


@pytest.mark.asyncio
async def test_user_step_overview_auth_error_shows_invalid_auth():
    flow = _make_flow()
    with (
        patch(
            "custom_components.migros_list.api.MigrosApiClient.async_validate_token",
            return_value=None,
        ),
        patch(
            "custom_components.migros_list.api.MigrosApiClient.async_get_lists_overview",
            side_effect=MigrosApiAuthError("401 from overview (cookies missing)"),
        ),
    ):
        result = await flow.async_step_user({"access_token": VALID_TOKEN})
    # Overview 401 is NOT auth error — should fall back to text input select_list form
    assert result["type"] == "form"
    assert result["step_id"] == "select_list"
    assert not result.get("errors")


@pytest.mark.asyncio
async def test_user_step_userinfo_auth_error_shows_invalid_auth():
    flow = _make_flow()
    with patch(
        "custom_components.migros_list.api.MigrosApiClient.async_validate_token",
        side_effect=MigrosApiAuthError("bad token"),
    ):
        result = await flow.async_step_user({"access_token": VALID_TOKEN})
    assert result["type"] == "form"
    assert result["errors"]["base"] == "invalid_auth"


@pytest.mark.asyncio
async def test_user_step_overview_network_error_falls_back_to_text_input():
    """Any non-auth error from overview falls through to text input."""
    flow = _make_flow()
    with (
        patch(
            "custom_components.migros_list.api.MigrosApiClient.async_validate_token",
            return_value=None,
        ),
        patch(
            "custom_components.migros_list.api.MigrosApiClient.async_get_lists_overview",
            side_effect=MigrosApiError("needs cookies"),
        ),
    ):
        result = await flow.async_step_user({"access_token": VALID_TOKEN})
    assert result["type"] == "form"
    assert result["step_id"] == "select_list"


@pytest.mark.asyncio
async def test_user_step_overview_success_shows_dropdown():
    flow = _make_flow()
    with (
        patch(
            "custom_components.migros_list.api.MigrosApiClient.async_validate_token",
            return_value=None,
        ),
        patch(
            "custom_components.migros_list.api.MigrosApiClient.async_get_lists_overview",
            return_value=LISTS,
        ),
    ):
        result = await flow.async_step_user({"access_token": VALID_TOKEN})
    assert result["type"] == "form"
    assert result["step_id"] == "select_list"


@pytest.mark.asyncio
async def test_user_step_stores_normalized_token():
    """Raw JSON input is stored as the normalized bare JWT."""
    flow = _make_flow()
    with (
        patch(
            "custom_components.migros_list.api.MigrosApiClient.async_validate_token",
            return_value=None,
        ),
        patch(
            "custom_components.migros_list.api.MigrosApiClient.async_get_lists_overview",
            return_value=LISTS,
        ),
    ):
        await flow.async_step_user({"access_token": BEARER_JSON})
    assert flow._token == VALID_TOKEN


# ---------------------------------------------------------------------------
# async_step_select_list — list selection step
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_select_list_shows_form_initially():
    flow = _make_flow()
    flow._available_lists = {l["id"]: l["name"] for l in LISTS}
    result = await flow.async_step_select_list(None)
    assert result["type"] == "form"
    assert result["step_id"] == "select_list"


@pytest.mark.asyncio
async def test_select_list_dropdown_creates_entry():
    flow = _make_flow()
    flow._token = VALID_TOKEN
    flow._available_lists = {l["id"]: l["name"] for l in LISTS}

    result = await flow.async_step_select_list({CONF_LIST_ID: "346969"})
    assert result["type"] == "create_entry"
    assert result["title"] == "Einkaufsliste"
    assert result["data"]["access_token"] == VALID_TOKEN
    assert result["data"][CONF_LIST_ID] == "346969"


@pytest.mark.asyncio
async def test_select_list_manual_creates_entry_on_success():
    """No lists available → manual text input → validates via list details."""
    from custom_components.migros_list.models import MigrosShoppingList, MigrosTotals

    flow = _make_flow()
    flow._token = VALID_TOKEN
    flow._available_lists = {}

    fake_list = MigrosShoppingList(
        shopping_list_id="346969",
        name="Einkaufsliste",
        categories=(),
        totals=MigrosTotals(instore_total=0.0, online_estimated_total=0.0),
    )
    with patch(
        "custom_components.migros_list.api.MigrosApiClient.async_get_shopping_list",
        return_value=fake_list,
    ):
        result = await flow.async_step_select_list({CONF_LIST_ID: "346969"})

    assert result["type"] == "create_entry"
    assert result["title"] == "Einkaufsliste"
    assert result["data"]["access_token"] == VALID_TOKEN


@pytest.mark.asyncio
async def test_select_list_manual_invalid_id_shows_error():
    from custom_components.migros_list.api import MigrosApiHttpError

    flow = _make_flow()
    flow._token = VALID_TOKEN
    flow._available_lists = {}

    with patch(
        "custom_components.migros_list.api.MigrosApiClient.async_get_shopping_list",
        side_effect=MigrosApiHttpError(404),
    ):
        result = await flow.async_step_select_list({CONF_LIST_ID: "999"})

    assert result["type"] == "form"
    assert result["errors"]["base"] == "invalid_list_id"


@pytest.mark.asyncio
async def test_select_list_manual_auth_error_shows_error():
    flow = _make_flow()
    flow._token = VALID_TOKEN
    flow._available_lists = {}

    with patch(
        "custom_components.migros_list.api.MigrosApiClient.async_get_shopping_list",
        side_effect=MigrosApiAuthError("expired"),
    ):
        result = await flow.async_step_select_list({CONF_LIST_ID: "346969"})

    assert result["type"] == "form"
    assert result["errors"]["base"] == "invalid_auth"

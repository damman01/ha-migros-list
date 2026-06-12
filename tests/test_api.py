"""Tests for MigrosApiClient."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.migros_list.api import (
    MigrosApiAuthError,
    MigrosApiClient,
    MigrosApiError,
    MigrosApiHttpError,
)
from custom_components.migros_list.const import (
    MIGROS_LIST_DETAILS_URL,
    MIGROS_LISTS_OVERVIEW_URL,
)

VALID_TOKEN = "eyJhbGciOiJSUzI1NiJ9.test.sig"

OVERVIEW_RESPONSE = [
    {"shoppingListId": 346969, "shoppingListName": "Einkaufsliste"},
    {"shoppingListId": 346936, "shoppingListName": "Tischgrill"},
]

# Load real API response recorded via Bruno
SHOPPING_LIST_RESPONSE: dict = json.loads(
    (Path(__file__).parent / "overview_response.json").read_text(encoding="utf-8")
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(status: int = 200, json_data=None):
    """Build an AsyncMock that behaves like an aiohttp response context manager."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data or {})
    if status >= 400:
        resp.raise_for_status = MagicMock(
            side_effect=aiohttp.ClientResponseError(
                request_info=MagicMock(), history=(), status=status
            )
        )
    else:
        resp.raise_for_status = MagicMock()
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


# ---------------------------------------------------------------------------
# _normalize_access_token  (pure, no I/O)
# ---------------------------------------------------------------------------


class TestNormalizeToken:
    def test_plain_token(self):
        client = MigrosApiClient(access_token=VALID_TOKEN)
        assert client._access_token == VALID_TOKEN

    def test_strips_bearer_prefix(self):
        client = MigrosApiClient(access_token=f"Bearer {VALID_TOKEN}")
        assert client._access_token == VALID_TOKEN

    def test_strips_bearer_prefix_case_insensitive(self):
        client = MigrosApiClient(access_token=f"bearer {VALID_TOKEN}")
        assert client._access_token == VALID_TOKEN

    def test_parses_json_with_camelcase_key(self):
        raw = json.dumps({"accessToken": f"Bearer {VALID_TOKEN}"})
        client = MigrosApiClient(access_token=raw)
        assert client._access_token == VALID_TOKEN

    def test_parses_json_with_snake_case_key(self):
        raw = json.dumps({"access_token": VALID_TOKEN})
        client = MigrosApiClient(access_token=raw)
        assert client._access_token == VALID_TOKEN

    def test_strips_whitespace(self):
        client = MigrosApiClient(access_token=f"  {VALID_TOKEN}  ")
        assert client._access_token == VALID_TOKEN


# ---------------------------------------------------------------------------
# async_validate_token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_token_success(hass):
    client = MigrosApiClient(access_token=VALID_TOKEN)
    with patch("custom_components.migros_list.api.async_get_clientsession") as mock_session:
        mock_session.return_value.get.return_value = _mock_response(200, {"sub": "abc"})
        await client.async_validate_token(hass)  # should not raise


@pytest.mark.asyncio
async def test_validate_token_invalid(hass):
    client = MigrosApiClient(access_token="bad-token")
    with patch("custom_components.migros_list.api.async_get_clientsession") as mock_session:
        mock_session.return_value.get.return_value = _mock_response(401)
        with pytest.raises(MigrosApiAuthError):
            await client.async_validate_token(hass)


@pytest.mark.asyncio
async def test_validate_token_forbidden(hass):
    client = MigrosApiClient(access_token="bad-token")
    with patch("custom_components.migros_list.api.async_get_clientsession") as mock_session:
        mock_session.return_value.get.return_value = _mock_response(403)
        with pytest.raises(MigrosApiAuthError):
            await client.async_validate_token(hass)


# ---------------------------------------------------------------------------
# async_get_lists_overview
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_lists_overview_success(hass):
    client = MigrosApiClient(access_token=VALID_TOKEN)
    with patch("custom_components.migros_list.api.async_get_clientsession") as mock_session:
        mock_session.return_value.get.return_value = _mock_response(200, OVERVIEW_RESPONSE)
        lists = await client.async_get_lists_overview(hass)

    assert len(lists) == 2
    assert lists[0] == {"id": "346969", "name": "Einkaufsliste"}
    assert lists[1] == {"id": "346936", "name": "Tischgrill"}


@pytest.mark.asyncio
async def test_get_lists_overview_auth_error(hass):
    client = MigrosApiClient(access_token=VALID_TOKEN)
    with patch("custom_components.migros_list.api.async_get_clientsession") as mock_session:
        mock_session.return_value.get.return_value = _mock_response(401)
        with pytest.raises(MigrosApiAuthError):
            await client.async_get_lists_overview(hass)


@pytest.mark.asyncio
async def test_get_lists_overview_skips_incomplete_entries(hass):
    client = MigrosApiClient(access_token=VALID_TOKEN)
    incomplete = [{"shoppingListId": 1}, {"shoppingListName": "only name"}]
    with patch("custom_components.migros_list.api.async_get_clientsession") as mock_session:
        mock_session.return_value.get.return_value = _mock_response(200, incomplete)
        lists = await client.async_get_lists_overview(hass)
    assert lists == []


# ---------------------------------------------------------------------------
# async_get_shopping_list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_shopping_list_success(hass):
    client = MigrosApiClient(access_token=VALID_TOKEN, shopping_list_id="346969")
    with patch("custom_components.migros_list.api.async_get_clientsession") as mock_session:
        mock_session.return_value.get.return_value = _mock_response(200, SHOPPING_LIST_RESPONSE)
        shopping_list = await client.async_get_shopping_list(hass)

    assert shopping_list.name == "Einkaufsliste"
    assert shopping_list.shopping_list_id == "346969"
    assert len(shopping_list.categories) == 1
    assert shopping_list.categories[0].category_id == "7494734"
    assert len(shopping_list.categories[0].items) == 1
    item = shopping_list.categories[0].items[0]
    assert item.name == "Vanille"
    assert item.item_type == "PRODUCT"
    assert item.availability == "UNAVAILABLE"
    assert shopping_list.totals.instore_total == 1.1
    assert shopping_list.totals.online_estimated_total == 0.0


@pytest.mark.asyncio
async def test_get_shopping_list_auth_error(hass):
    client = MigrosApiClient(access_token="bad", shopping_list_id="1")
    with patch("custom_components.migros_list.api.async_get_clientsession") as mock_session:
        mock_session.return_value.get.return_value = _mock_response(401)
        with pytest.raises(MigrosApiAuthError):
            await client.async_get_shopping_list(hass)


@pytest.mark.asyncio
async def test_get_shopping_list_not_found(hass):
    client = MigrosApiClient(access_token=VALID_TOKEN, shopping_list_id="99999")
    with patch("custom_components.migros_list.api.async_get_clientsession") as mock_session:
        mock_session.return_value.get.return_value = _mock_response(404)
        with pytest.raises(MigrosApiHttpError) as exc_info:
            await client.async_get_shopping_list(hass)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_shopping_list_empty_categories(hass):
    client = MigrosApiClient(access_token=VALID_TOKEN, shopping_list_id="346969")
    payload = {**SHOPPING_LIST_RESPONSE, "categories": []}
    with patch("custom_components.migros_list.api.async_get_clientsession") as mock_session:
        mock_session.return_value.get.return_value = _mock_response(200, payload)
        shopping_list = await client.async_get_shopping_list(hass)
    assert shopping_list.categories == ()


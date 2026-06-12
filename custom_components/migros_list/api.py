from __future__ import annotations

import json
from typing import Any

from aiohttp import ClientError, ClientResponseError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import MIGROS_LANGUAGE, MIGROS_LIST_DETAILS_URL, MIGROS_LISTS_OVERVIEW_URL, MIGROS_PEER_ID, MIGROS_REFERER
from .models import MigrosCategory, MigrosShoppingList, MigrosShoppingListItem, MigrosTotals


class MigrosApiError(Exception):
    """Base error for the Migros API client."""


class MigrosApiAuthError(MigrosApiError):
    """Raised when Migros rejects the configured token."""


class MigrosApiHttpError(MigrosApiError):
    """Raised when Migros API responds with an HTTP error."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"Migros API returned HTTP {status_code}")
        self.status_code = status_code


class MigrosApiClient:
    def __init__(self, access_token: str, shopping_list_id: str = "") -> None:
        self._access_token = self._normalize_access_token(access_token)
        self._shopping_list_id = shopping_list_id

    @property
    def shopping_list_id(self) -> str:
        return self._shopping_list_id

    async def async_validate_token(self, hass) -> None:
        """Validate bearer token via OIDC userinfo. Raises MigrosApiAuthError if rejected."""
        session = async_get_clientsession(hass)
        try:
            async with session.get(
                "https://login.migros.ch/oauth2/userinfo",
                headers={"authorization": f"Bearer {self._access_token}"},
            ) as response:
                response.raise_for_status()
        except ClientResponseError as err:
            if err.status in (401, 403):
                raise MigrosApiAuthError("Token rejected by auth server") from err
            raise MigrosApiHttpError(err.status) from err
        except ClientError as err:
            raise MigrosApiError("Could not reach Migros auth server") from err

    async def async_get_lists_overview(self, hass) -> list[dict[str, Any]]:
        session = async_get_clientsession(hass)
        try:
            async with session.get(
                MIGROS_LISTS_OVERVIEW_URL,
                headers=self._build_headers(),
            ) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
        except ClientResponseError as err:
            if err.status in (401, 403):
                raise MigrosApiAuthError("Authentication failed") from err
            raise MigrosApiHttpError(err.status) from err
        except ClientError as err:
            raise MigrosApiError("Could not reach Migros API") from err
        except ValueError as err:
            raise MigrosApiError("Migros API returned invalid JSON") from err

        return [
            {"id": str(entry["shoppingListId"]), "name": entry["shoppingListName"]}
            for entry in payload
            if "shoppingListId" in entry and "shoppingListName" in entry
        ]

    async def async_get_shopping_list(self, hass) -> MigrosShoppingList:
        session = async_get_clientsession(hass)
        try:
            async with session.get(
                MIGROS_LIST_DETAILS_URL,
                params={"shoppingListId": self._shopping_list_id},
                headers=self._build_headers(),
            ) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
        except ClientResponseError as err:
            if err.status in (401, 403):
                raise MigrosApiAuthError("Authentication failed") from err
            raise MigrosApiHttpError(err.status) from err
        except ClientError as err:
            raise MigrosApiError("Could not reach Migros API") from err
        except ValueError as err:
            raise MigrosApiError("Migros API returned invalid JSON") from err

        return self._parse_shopping_list(payload)

    def _build_headers(self) -> dict[str, str]:
        return {
            "accept": "application/json, text/plain, */*",
            "authorization": f"Bearer {self._access_token}",
            "migros-language": MIGROS_LANGUAGE,
            "peer-id": MIGROS_PEER_ID,
            "referer": MIGROS_REFERER,
        }

    def _parse_shopping_list(self, payload: dict[str, Any]) -> MigrosShoppingList:
        categories: list[MigrosCategory] = []
        for raw_category in payload.get("categories", []):
            raw_items = raw_category.get("items", [])
            items = tuple(self._parse_item(raw_item) for raw_item in raw_items)
            categories.append(
                MigrosCategory(
                    category_id=str(raw_category.get("id", "")),
                    items=items,
                )
            )

        online_total = payload.get("totals", {}).get("onlineTotal", {})
        totals = MigrosTotals(
            instore_total=self._as_float(payload.get("totals", {}).get("instoreTotal")),
            online_estimated_total=self._as_float(online_total.get("estimatedTotal")),
        )

        return MigrosShoppingList(
            shopping_list_id=str(payload.get("shoppingListId", self._shopping_list_id)),
            name=payload.get("name", "Migros"),
            categories=tuple(categories),
            totals=totals,
        )

    @staticmethod
    def _parse_item(payload: dict[str, Any]) -> MigrosShoppingListItem:
        return MigrosShoppingListItem(
            item_id=str(payload.get("id", "")),
            item_type=payload.get("type", "UNKNOWN"),
            quantity=MigrosApiClient._as_float(payload.get("quantity"), fallback=1.0),
            name=payload.get("name", ""),
            note=payload.get("note", ""),
            availability=payload.get("ecomProductAvailability", "UNKNOWN"),
        )

    @staticmethod
    def _as_float(value: Any, fallback: float = 0.0) -> float:
        try:
            if value is None:
                return fallback
            return float(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _normalize_access_token(access_token: str) -> str:
        token = access_token.strip()
        if token.startswith("{"):
            try:
                token_data = json.loads(token)
            except ValueError:
                token_data = None
            if isinstance(token_data, dict):
                # API response uses camelCase; stored config uses snake_case
                extracted = token_data.get("accessToken") or token_data.get("access_token")
                if isinstance(extracted, str):
                    token = extracted.strip()
        if token[:7].lower() == "bearer ":
            token = token[7:].strip()
        return token
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MigrosShoppingListItem:
    item_id: str
    item_type: str
    quantity: float
    name: str
    note: str
    availability: str

    @property
    def display_name(self) -> str:
        if self.note:
            return f"{self.name} ({self.note})"
        return self.name

    def as_dict(self) -> dict[str, str | float]:
        return {
            "id": self.item_id,
            "name": self.name,
            "display_name": self.display_name,
            "note": self.note,
            "quantity": self.quantity,
            "type": self.item_type,
            "availability": self.availability,
        }


@dataclass(frozen=True, slots=True)
class MigrosCategory:
    category_id: str
    items: tuple[MigrosShoppingListItem, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.category_id,
            "items": [item.as_dict() for item in self.items],
        }


@dataclass(frozen=True, slots=True)
class MigrosTotals:
    instore_total: float
    online_estimated_total: float


@dataclass(frozen=True, slots=True)
class MigrosShoppingList:
    shopping_list_id: str
    name: str
    categories: tuple[MigrosCategory, ...]
    totals: MigrosTotals

    @property
    def items(self) -> tuple[MigrosShoppingListItem, ...]:
        return tuple(item for category in self.categories for item in category.items)

    @property
    def item_count(self) -> int:
        return len(self.items)

    def categories_as_dict(self) -> list[dict[str, object]]:
        return [category.as_dict() for category in self.categories]

    def items_as_dict(self) -> list[dict[str, str | float]]:
        return [item.as_dict() for item in self.items]
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import MigrosRuntimeData
from .const import ATTR_CATEGORIES, ATTR_ITEMS, DOMAIN
from .models import MigrosShoppingList


@dataclass(frozen=True, kw_only=True)
class MigrosSensorDescription(SensorEntityDescription):
    value_fn: Callable[[MigrosShoppingList], int | float]


SENSOR_DESCRIPTIONS: tuple[MigrosSensorDescription, ...] = (
    MigrosSensorDescription(
        key="item_count",
        translation_key="item_count",
        icon="mdi:cart-outline",
        value_fn=lambda data: data.item_count,
    ),
    MigrosSensorDescription(
        key="instore_total",
        translation_key="instore_total",
        icon="mdi:currency-chf",
        native_unit_of_measurement="CHF",
        device_class=SensorDeviceClass.MONETARY,
        value_fn=lambda data: round(data.totals.instore_total, 2),
    ),
    MigrosSensorDescription(
        key="online_total",
        translation_key="online_total",
        icon="mdi:cash-fast",
        native_unit_of_measurement="CHF",
        device_class=SensorDeviceClass.MONETARY,
        value_fn=lambda data: round(data.totals.online_estimated_total, 2),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime_data: MigrosRuntimeData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        MigrosSensor(entry, runtime_data.coordinator, description)
        for description in SENSOR_DESCRIPTIONS
    )


class MigrosSensor(CoordinatorEntity, SensorEntity):
    entity_description: MigrosSensorDescription
    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, coordinator, description: MigrosSensorDescription) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> int | float:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": self.coordinator.data.name,
            "manufacturer": "Migros",
            "model": "Shopping List",
        }

    @property
    def extra_state_attributes(self) -> dict[str, object] | None:
        if self.entity_description.key != "item_count":
            return None

        data = self.coordinator.data
        return {
            ATTR_ITEMS: data.items_as_dict(),
            ATTR_CATEGORIES: data.categories_as_dict(),
        }
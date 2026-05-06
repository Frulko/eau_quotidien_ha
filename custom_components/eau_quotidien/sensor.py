"""Entités sensor pour Eau Quotidien."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EauQuotidienCoordinator


@dataclass(frozen=True, kw_only=True)
class EauSensorDescription(SensorEntityDescription):
    """Description d'un sensor de compteur d'eau."""

    value_fn: Callable[[dict[str, Any]], Any]


SENSORS: tuple[EauSensorDescription, ...] = (
    EauSensorDescription(
        key="index",
        translation_key="index",
        name="Index",
        icon="mdi:counter",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        value_fn=lambda d: (d.get("latest") or {}).get("index_releve"),
    ),
    EauSensorDescription(
        key="consumption_today",
        translation_key="consumption_today",
        name="Consommation aujourd'hui",
        icon="mdi:water",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        value_fn=lambda d: d.get("last_conso"),
    ),
    EauSensorDescription(
        key="consumption_average",
        translation_key="consumption_average",
        name="Consommation moyenne",
        icon="mdi:chart-line",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        value_fn=lambda d: d.get("conso_avg"),
    ),
    EauSensorDescription(
        key="threshold_high",
        translation_key="threshold_high",
        name="Seuil d'alerte haut",
        icon="mdi:alert",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("threshold_high"),
    ),
    EauSensorDescription(
        key="threshold_low",
        translation_key="threshold_low",
        name="Seuil d'alerte bas",
        icon="mdi:alert-outline",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("threshold_low"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crée les entités à partir du coordinator."""
    bag = hass.data[DOMAIN][entry.entry_id]
    coordinator: EauQuotidienCoordinator = bag["coordinator"]
    async_add_entities(
        EauQuotidienSensor(coordinator, desc) for desc in SENSORS
    )


class EauQuotidienSensor(
    CoordinatorEntity[EauQuotidienCoordinator], SensorEntity
):
    """Sensor générique adossé au coordinator."""

    entity_description: EauSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EauQuotidienCoordinator,
        description: EauSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.meter_id}_{description.key}"

        meter = (coordinator.data or {}).get("meter") or {}
        designation = meter.get("designation") or str(coordinator.meter_id)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(coordinator.meter_id))},
            name=f"Compteur {designation}",
            manufacturer=meter.get("marque"),
            model=meter.get("modele"),
            sw_version=meter.get("type_releve"),
            serial_number=meter.get("sn"),
        )

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.key == "index":
            latest = (self.coordinator.data or {}).get("latest") or {}
            return {
                "last_reading_date": latest.get("dt"),
                "meter_id": self.coordinator.meter_id,
            }
        return None

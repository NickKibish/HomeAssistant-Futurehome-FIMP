"""Sensor platform for Futurehome FIMP thermostats."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import (
    UnitOfTemperature,
    UnitOfPower,
    UnitOfEnergy,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
)

from .const import (
    DOMAIN,
    ENTRY_DATA_CLIENT,
    ENTRY_DATA_DEVICES,
    FIMP_SERVICE_SENSOR_TEMP,
    FIMP_SERVICE_METER_ELEC,
    FIMP_INTERFACE_CMD_SENSOR_GET_REPORT,
    FIMP_INTERFACE_EVT_SENSOR_REPORT,
    FIMP_INTERFACE_CMD_METER_EXT_GET_REPORT,
    FIMP_INTERFACE_EVT_METER_EXT_REPORT,
)
from .fimp_client import FimpClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Futurehome FIMP sensor entities from a config entry."""
    client: FimpClient = hass.data[DOMAIN][config_entry.entry_id][ENTRY_DATA_CLIENT]
    devices: dict[str, dict] = hass.data[DOMAIN][config_entry.entry_id][ENTRY_DATA_DEVICES]

    entities = []
    
    for device_address, device_data in devices.items():
        services = device_data.get("services", [])
        
        # Create temperature sensor entities
        for service in services:
            if service.get("name") == FIMP_SERVICE_SENSOR_TEMP:
                entity = FimpTemperatureSensor(
                    client=client,
                    device_address=device_address,
                    device_data=device_data,
                    service_data=service,
                )
                entities.append(entity)
                _LOGGER.info(
                    "Added temperature sensor entity for device %s, service %s",
                    device_address,
                    service.get("address", "unknown")
                )
        
        # Create power consumption sensor entities
        for service in services:
            if service.get("name") == FIMP_SERVICE_METER_ELEC:
                # Create multiple sensors for different meter values
                meter_sensors = [
                    ("p_import", "Power", UnitOfPower.WATT, SensorDeviceClass.POWER),
                    ("e_import", "Energy", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY),
                    ("u1", "Voltage", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE),
                    ("i1", "Current", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT),
                ]
                
                for meter_key, name_suffix, unit, device_class in meter_sensors:
                    entity = FimpMeterSensor(
                        client=client,
                        device_address=device_address,
                        device_data=device_data,
                        service_data=service,
                        meter_key=meter_key,
                        name_suffix=name_suffix,
                        unit=unit,
                        device_class=device_class,
                    )
                    entities.append(entity)
                    _LOGGER.info(
                        "Added %s sensor entity for device %s",
                        name_suffix,
                        device_address
                    )

    if entities:
        async_add_entities(entities, True)


class FimpTemperatureSensor(SensorEntity):
    """Representation of a Futurehome FIMP temperature sensor."""

    def __init__(
        self,
        client: FimpClient,
        device_address: str,
        device_data: dict,
        service_data: dict,
    ) -> None:
        """Initialize the temperature sensor."""
        self._client = client
        self._device_address = device_address
        self._device_data = device_data
        self._service_data = service_data
        self._value = None
        
        # Extract service address for topic generation
        service_address = service_data.get("address", "")
        address_parts = service_address.split("/")
        self._service_address = address_parts[-1] if address_parts else "unknown"
        
        # Build sensor name
        product_name = device_data.get("product_name", "Thermostat")
        self._attr_name = f"{product_name} Temperature ({self._service_address})"
        
        # Generate unique ID
        self._attr_unique_id = f"{DOMAIN}_{device_address}_{self._service_address}_temp"
        
        # Device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_address)},
            "name": product_name,
            "manufacturer": device_data.get("manufacturer_id", "Unknown"),
            "model": device_data.get("product_id", "Unknown"),
            "sw_version": device_data.get("sw_ver"),
            "hw_version": device_data.get("hw_ver"),
            "via_device": (DOMAIN, "hub"),
        }
        
        # Sensor properties
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        
        # Subscribe to temperature updates
        self._setup_subscriptions()

    def _setup_subscriptions(self) -> None:
        """Set up MQTT subscriptions for temperature updates."""
        topic_pattern = f"pt:j1/mt:evt/rt:dev/rn:zigbee/ad:1/sv:sensor_temp/ad:{self._service_address}"
        self._client.register_message_callback(topic_pattern, self._handle_temperature_update)

    def _handle_temperature_update(self, topic: str, message: dict[str, Any]) -> None:
        """Handle temperature sensor updates."""
        if message.get("type") == FIMP_INTERFACE_EVT_SENSOR_REPORT:
            if message.get("serv") == FIMP_SERVICE_SENSOR_TEMP:
                self._value = message.get("val")
                self.schedule_update_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return the current temperature."""
        return self._value

    async def async_update(self) -> None:
        """Request temperature update from device."""
        topic = f"pt:j1/mt:cmd/rt:dev/rn:zigbee/ad:1/sv:sensor_temp/ad:{self._service_address}"
        await self._client.async_send_fimp_message(
            topic=topic,
            service=FIMP_SERVICE_SENSOR_TEMP,
            msg_type=FIMP_INTERFACE_CMD_SENSOR_GET_REPORT,
            value_type="string",
            value="",
        )


class FimpMeterSensor(SensorEntity):
    """Representation of a Futurehome FIMP power meter sensor."""

    def __init__(
        self,
        client: FimpClient,
        device_address: str,
        device_data: dict,
        service_data: dict,
        meter_key: str,
        name_suffix: str,
        unit: str,
        device_class: SensorDeviceClass,
    ) -> None:
        """Initialize the meter sensor."""
        self._client = client
        self._device_address = device_address
        self._device_data = device_data
        self._service_data = service_data
        self._meter_key = meter_key
        self._value = None
        
        # Extract service address for topic generation
        service_address = service_data.get("address", "")
        address_parts = service_address.split("/")
        self._service_address = address_parts[-1] if address_parts else "unknown"
        
        # Build sensor name
        product_name = device_data.get("product_name", "Thermostat")
        self._attr_name = f"{product_name} {name_suffix}"
        
        # Generate unique ID
        self._attr_unique_id = f"{DOMAIN}_{device_address}_{self._service_address}_{meter_key}"
        
        # Device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_address)},
            "name": product_name,
            "manufacturer": device_data.get("manufacturer_id", "Unknown"),
            "model": device_data.get("product_id", "Unknown"),
            "sw_version": device_data.get("sw_ver"),
            "hw_version": device_data.get("hw_ver"),
            "via_device": (DOMAIN, "hub"),
        }
        
        # Sensor properties
        self._attr_device_class = device_class
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = unit
        
        # Subscribe to meter updates
        self._setup_subscriptions()

    def _setup_subscriptions(self) -> None:
        """Set up MQTT subscriptions for meter updates."""
        topic_pattern = f"pt:j1/mt:evt/rt:dev/rn:zigbee/ad:1/sv:meter_elec/ad:{self._service_address}"
        self._client.register_message_callback(topic_pattern, self._handle_meter_update)

    def _handle_meter_update(self, topic: str, message: dict[str, Any]) -> None:
        """Handle meter sensor updates."""
        if message.get("type") == FIMP_INTERFACE_EVT_METER_EXT_REPORT:
            if message.get("serv") == FIMP_SERVICE_METER_ELEC:
                meter_data = message.get("val", {})
                if isinstance(meter_data, dict) and self._meter_key in meter_data:
                    self._value = meter_data[self._meter_key]
                    self.schedule_update_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return the current meter value."""
        return self._value

    async def async_update(self) -> None:
        """Request meter update from device."""
        topic = f"pt:j1/mt:cmd/rt:dev/rn:zigbee/ad:1/sv:meter_elec/ad:{self._service_address}"
        await self._client.async_send_fimp_message(
            topic=topic,
            service=FIMP_SERVICE_METER_ELEC,
            msg_type=FIMP_INTERFACE_CMD_METER_EXT_GET_REPORT,
            value_type="null",
            value=None,
        )
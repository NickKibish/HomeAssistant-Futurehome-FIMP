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
    EntityCategory,
)

from .const import (
    DOMAIN,
    ENTRY_DATA_CLIENT,
    ENTRY_DATA_DEVICES,
    ENTRY_DATA_BRIDGE_DEVICE_ID,
    ENTRY_DATA_HUB_INFO,
    FIMP_SERVICE_SENSOR_TEMP,
    FIMP_SERVICE_METER_ELEC,
    FIMP_INTERFACE_CMD_SENSOR_GET_REPORT,
    FIMP_INTERFACE_EVT_SENSOR_REPORT,
    FIMP_INTERFACE_CMD_METER_EXT_GET_REPORT,
    FIMP_INTERFACE_EVT_METER_EXT_REPORT,
    BRIDGE_MANUFACTURER,
    BRIDGE_MODEL,
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
    bridge_device_id: str = hass.data[DOMAIN][config_entry.entry_id][ENTRY_DATA_BRIDGE_DEVICE_ID]
    hub_info: dict = hass.data[DOMAIN][config_entry.entry_id][ENTRY_DATA_HUB_INFO]

    entities = []
    
    # Add bridge diagnostic sensors
    bridge_sensors = [
        BridgeConnectionSensor(client, bridge_device_id, hub_info),
        BridgeDeviceCountSensor(client, bridge_device_id, hub_info),
    ]
    entities.extend(bridge_sensors)
    
    for device_address, device_data in devices.items():
        services = device_data.get("services", [])
        service_names = [svc.get("name") for svc in services]
        _LOGGER.info("Processing device %s with services: %s", device_address, ", ".join(service_names))
        
        # Create temperature sensor entities
        for service in services:
            if service.get("name") == FIMP_SERVICE_SENSOR_TEMP:
                entity = FimpTemperatureSensor(
                    client=client,
                    device_address=device_address,
                    device_data=device_data,
                    service_data=service,
                    bridge_device_id=bridge_device_id,
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
                    ("p_import", "Power", UnitOfPower.WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
                    ("e_import", "Energy", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING),
                    ("u1", "Voltage", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT),
                    ("i1", "Current", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT),
                ]
                
                for meter_key, name_suffix, unit, device_class, state_class in meter_sensors:
                    entity = FimpMeterSensor(
                        client=client,
                        device_address=device_address,
                        device_data=device_data,
                        service_data=service,
                        meter_key=meter_key,
                        name_suffix=name_suffix,
                        unit=unit,
                        device_class=device_class,
                        state_class=state_class,
                        bridge_device_id=bridge_device_id,
                    )
                    entities.append(entity)
                    _LOGGER.info(
                        "Added %s sensor entity for device %s",
                        name_suffix,
                        device_address
                    )

    if entities:
        _LOGGER.info("Adding %d sensor entities total", len(entities))
        async_add_entities(entities, True)
    else:
        _LOGGER.warning("No sensor entities to add")


class FimpTemperatureSensor(SensorEntity):
    """Representation of a Futurehome FIMP temperature sensor."""

    def __init__(
        self,
        client: FimpClient,
        device_address: str,
        device_data: dict,
        service_data: dict,
        bridge_device_id: str,
    ) -> None:
        """Initialize the temperature sensor."""
        self._client = client
        self._device_address = device_address
        self._device_data = device_data
        self._service_data = service_data
        self._value = None
        
        # Extract service address for topic generation
        service_address = service_data.get("address", "")
        # Extract the last part after the last /ad:
        # Example: "/rt:dev/rn:zigbee/ad:1/sv:sensor_temp/ad:1_1" -> "1_1"
        address_parts = service_address.split("/ad:")
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
            "via_device": (DOMAIN, bridge_device_id),
        }
        
        # Sensor properties
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        
        # Register for connection status updates
        self._client.register_connection_status_callback(self._on_connection_status_changed)
        
        # Subscribe to temperature updates
        self._setup_subscriptions()

    def _setup_subscriptions(self) -> None:
        """Set up MQTT subscriptions for temperature updates."""
        topic_pattern = f"pt:j1/mt:evt/rt:dev/rn:zigbee/ad:1/sv:sensor_temp/ad:{self._service_address}"
        self._client.register_message_callback(topic_pattern, self._handle_temperature_update)

    async def async_added_to_hass(self) -> None:
        """Handle entity added to Home Assistant."""
        await super().async_added_to_hass()
        # Request initial temperature reading
        await self.async_update()

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

    def _on_connection_status_changed(self, connected: bool) -> None:
        """Handle MQTT connection status change."""
        _LOGGER.debug("Temperature sensor %s connection status changed to %s", self.name, connected)
        # Update Home Assistant about availability change
        self.schedule_update_ha_state()

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._client.is_connected


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
        state_class: SensorStateClass,
        bridge_device_id: str,
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
        # Extract the last part after the last /ad:
        # Example: "/rt:dev/rn:zigbee/ad:1/sv:sensor_temp/ad:1_1" -> "1_1"
        address_parts = service_address.split("/ad:")
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
            "via_device": (DOMAIN, bridge_device_id),
        }
        
        # Sensor properties
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_native_unit_of_measurement = unit
        
        # Register for connection status updates
        self._client.register_connection_status_callback(self._on_connection_status_changed)
        
        # Subscribe to meter updates
        self._setup_subscriptions()

    def _setup_subscriptions(self) -> None:
        """Set up MQTT subscriptions for meter updates."""
        topic_pattern = f"pt:j1/mt:evt/rt:dev/rn:zigbee/ad:1/sv:meter_elec/ad:{self._service_address}"
        self._client.register_message_callback(topic_pattern, self._handle_meter_update)
        
        # For energy sensors, also subscribe to broader meter topics in case energy comes separately
        if self._meter_key == "e_import":
            # Subscribe to all meter messages for this device to catch energy data
            device_pattern = f"pt:j1/mt:evt/rt:dev/rn:zigbee/ad:1/sv:*/ad:{self._service_address}"
            self._client.register_message_callback(device_pattern, self._handle_energy_update)

    async def async_added_to_hass(self) -> None:
        """Handle entity added to Home Assistant."""
        await super().async_added_to_hass()
        # Request initial meter reading
        await self.async_update()

    def _handle_meter_update(self, topic: str, message: dict[str, Any]) -> None:
        """Handle meter sensor updates."""
        _LOGGER.debug("Meter sensor %s received message: %s", self._meter_key, message)
        
        msg_type = message.get("type")
        
        # Handle both regular meter reports and extended meter reports
        if msg_type in [FIMP_INTERFACE_EVT_METER_EXT_REPORT, "evt.meter.report"]:
            if message.get("serv") == FIMP_SERVICE_METER_ELEC:
                meter_data = message.get("val")
                _LOGGER.debug("Meter data for %s: %s (type: %s)", self._meter_key, meter_data, type(meter_data))
                
                # Handle simple numeric values (likely energy consumption)
                if isinstance(meter_data, (int, float)):
                    # Simple numeric value - this is likely energy consumption for e_import sensors
                    if self._meter_key == "e_import":
                        old_value = self._value
                        self._value = meter_data
                        _LOGGER.info("Energy sensor %s updated from simple value: %s -> %s", 
                                   self._meter_key, old_value, self._value)
                        self.schedule_update_ha_state()
                        return
                    else:
                        # For other sensors, skip simple values as they're likely energy data
                        _LOGGER.debug("Skipping simple value %s for non-energy sensor %s", meter_data, self._meter_key)
                        return
                
                # Handle dictionary values (power, current, voltage data)
                elif isinstance(meter_data, dict):
                    # Check for the meter key directly
                    if self._meter_key in meter_data:
                        old_value = self._value
                        self._value = meter_data[self._meter_key]
                        _LOGGER.info("Meter sensor %s updated: %s -> %s", self._meter_key, old_value, self._value)
                        self.schedule_update_ha_state()
                    # For energy, also check alternative key names in dict
                    elif self._meter_key == "e_import":
                        energy_keys = ["e_import", "energy", "energy_import", "consumption", "kwh", "e_consumed"]
                        for key in energy_keys:
                            if key in meter_data:
                                old_value = self._value
                                self._value = meter_data[key]
                                _LOGGER.info("Meter sensor %s found energy data with key '%s': %s -> %s", 
                                           self._meter_key, key, old_value, self._value)
                                self.schedule_update_ha_state()
                                return
                        _LOGGER.debug("Energy key %s not found in meter data dict: %s", self._meter_key, meter_data)
                    else:
                        _LOGGER.debug("Meter key %s not found in data dict: %s", self._meter_key, meter_data)
                else:
                    _LOGGER.warning("Unexpected meter data type for %s: %s (%s)", self._meter_key, meter_data, type(meter_data))

    def _handle_energy_update(self, topic: str, message: dict[str, Any]) -> None:
        """Handle energy-specific updates from any service for this device."""
        _LOGGER.debug("Energy sensor searching in message from topic %s: %s", topic, message)
        
        # Check if this message contains energy data
        msg_type = message.get("type")
        service = message.get("serv")
        value = message.get("val")
        
        # Look for energy in various message types and services
        if "meter" in service.lower() if service else False:
            if isinstance(value, dict):
                # Check for energy keys in the value dict
                energy_keys = ["e_import", "energy", "energy_import", "consumption", "kwh", "e_consumed", "e_total"]
                for key in energy_keys:
                    if key in value:
                        old_value = self._value
                        self._value = value[key]
                        _LOGGER.info("Found energy data for %s in service %s with key '%s': %s -> %s", 
                                   self._meter_key, service, key, old_value, self._value)
                        self.schedule_update_ha_state()
                        return
            elif isinstance(value, (int, float)) and "energy" in msg_type.lower():
                # Simple energy value
                old_value = self._value
                self._value = value
                _LOGGER.info("Found simple energy value for %s: %s -> %s", 
                           self._meter_key, old_value, self._value)
                self.schedule_update_ha_state()
                return

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

    def _on_connection_status_changed(self, connected: bool) -> None:
        """Handle MQTT connection status change."""
        _LOGGER.debug("Meter sensor %s connection status changed to %s", self.name, connected)
        # Update Home Assistant about availability change
        self.schedule_update_ha_state()

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._client.is_connected


class BridgeConnectionSensor(SensorEntity):
    """Bridge connection status sensor."""

    def __init__(self, client: FimpClient, bridge_device_id: str, hub_info: dict) -> None:
        """Initialize the bridge connection sensor."""
        self._client = client
        self._bridge_device_id = bridge_device_id
        self._hub_info = hub_info
        
        # Entity configuration
        self._attr_name = "Connection Status"
        self._attr_unique_id = f"{DOMAIN}_{bridge_device_id}_connection"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_class = None  # No specific device class for connection status
        self._attr_should_poll = False
        
        # Device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, bridge_device_id)},
            "manufacturer": BRIDGE_MANUFACTURER,
            "model": BRIDGE_MODEL,
            "name": f"Futurehome Hub ({hub_info['host']})",
        }

    @property
    def native_value(self) -> str:
        """Return the connection status."""
        return "Connected" if self._client.is_connected else "Disconnected"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return True  # Always available to show connection status

    async def async_added_to_hass(self) -> None:
        """Handle entity added to Home Assistant."""
        await super().async_added_to_hass()
        # Register for connection state changes
        self._client.register_message_callback("connection_status", self._handle_connection_change)

    def _handle_connection_change(self, topic: str, message: dict) -> None:
        """Handle connection status changes."""
        self.schedule_update_ha_state()


class BridgeDeviceCountSensor(SensorEntity):
    """Bridge connected device count sensor."""

    def __init__(self, client: FimpClient, bridge_device_id: str, hub_info: dict) -> None:
        """Initialize the bridge device count sensor."""
        self._client = client
        self._bridge_device_id = bridge_device_id
        self._hub_info = hub_info
        
        # Entity configuration
        self._attr_name = "Connected Devices"
        self._attr_unique_id = f"{DOMAIN}_{bridge_device_id}_device_count"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_should_poll = False
        self._attr_native_unit_of_measurement = "devices"
        
        # Device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, bridge_device_id)},
            "manufacturer": BRIDGE_MANUFACTURER,
            "model": BRIDGE_MODEL,
            "name": f"Futurehome Hub ({hub_info['host']})",
        }

    @property
    def native_value(self) -> int:
        """Return the number of connected devices."""
        return self._client.discovered_device_count

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._client.is_connected

    async def async_added_to_hass(self) -> None:
        """Handle entity added to Home Assistant."""
        await super().async_added_to_hass()
        # Register for device discovery updates
        self._client.register_device_discovery_callback(self._handle_device_update)

    def _handle_device_update(self, device_address: str, device_data: dict) -> None:
        """Handle device discovery updates."""
        self.schedule_update_ha_state()
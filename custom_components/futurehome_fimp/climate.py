"""Climate platform for Futurehome FIMP thermostats."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    HVACAction,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import UnitOfTemperature

from .const import (
    DOMAIN,
    ENTRY_DATA_CLIENT,
    ENTRY_DATA_DEVICES,
    ENTRY_DATA_BRIDGE_DEVICE_ID,
    FIMP_SERVICE_THERMOSTAT,
    FIMP_INTERFACE_CMD_MODE_GET_REPORT,
    FIMP_INTERFACE_CMD_MODE_SET,
    FIMP_INTERFACE_EVT_MODE_REPORT,
    FIMP_INTERFACE_CMD_SETPOINT_GET_REPORT,
    FIMP_INTERFACE_CMD_SETPOINT_SET,
    FIMP_INTERFACE_EVT_SETPOINT_REPORT,
    FIMP_INTERFACE_CMD_STATE_GET_REPORT,
    FIMP_INTERFACE_EVT_STATE_REPORT,
)
from .fimp_client import FimpClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Futurehome FIMP climate entities from a config entry."""
    client: FimpClient = hass.data[DOMAIN][config_entry.entry_id][ENTRY_DATA_CLIENT]
    devices: dict[str, dict] = hass.data[DOMAIN][config_entry.entry_id][ENTRY_DATA_DEVICES]
    bridge_device_id: str = hass.data[DOMAIN][config_entry.entry_id][ENTRY_DATA_BRIDGE_DEVICE_ID]

    # Track which devices have already had entities created
    processed_devices: set[str] = set()

    def create_entities_for_device(device_address: str, device_data: dict) -> list[FimpThermostat]:
        """Create thermostat entities for a device."""
        entities = []
        services = device_data.get("services", [])

        # Find thermostat services
        for service in services:
            if service.get("name") == FIMP_SERVICE_THERMOSTAT:
                entity = FimpThermostat(
                    client=client,
                    device_address=device_address,
                    device_data=device_data,
                    service_data=service,
                    bridge_device_id=bridge_device_id,
                )
                entities.append(entity)
                _LOGGER.info(
                    "Added thermostat entity for device %s: %s",
                    device_address,
                    device_data.get("product_name", "Unknown Thermostat")
                )
        return entities

    # Create entities for devices that already exist
    initial_entities = []
    for device_address, device_data in devices.items():
        entities = create_entities_for_device(device_address, device_data)
        initial_entities.extend(entities)
        if entities:
            processed_devices.add(device_address)

    if initial_entities:
        async_add_entities(initial_entities, True)
        _LOGGER.info("Added %d initial thermostat entities", len(initial_entities))

    # Register callback for dynamically discovered devices
    def on_device_discovered(device_address: str, device_data: dict) -> None:
        """Handle newly discovered devices (called from MQTT thread)."""
        # Schedule entity creation in Home Assistant event loop
        def add_entities_callback():
            if device_address not in processed_devices:
                entities = create_entities_for_device(device_address, device_data)
                if entities:
                    async_add_entities(entities, update_before_add=True)
                    processed_devices.add(device_address)
                    _LOGGER.info(
                        "Dynamically added %d thermostat entities for device %s",
                        len(entities),
                        device_address
                    )

        hass.loop.call_soon_threadsafe(add_entities_callback)

    client.register_device_discovery_callback(on_device_discovered)




class FimpThermostat(ClimateEntity):
    """Representation of a Futurehome FIMP thermostat (discovery only)."""

    def __init__(
        self,
        client: FimpClient,
        device_address: str,
        device_data: dict,
        service_data: dict,
        bridge_device_id: str,
    ) -> None:
        """Initialize the thermostat."""
        self._client = client
        self._device_address = device_address
        self._device_data = device_data
        self._service_data = service_data
        
        # Build device name
        product_name = device_data.get("product_name") or device_data.get("product_hash", "Unknown")
        self._attr_name = f"{product_name} Thermostat"
        
        # Generate unique ID
        self._attr_unique_id = f"{DOMAIN}_{device_address}_thermostat"
        
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
        
        # Climate attributes
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE |
            ClimateEntityFeature.PRESET_MODE
        )
        
        # Ensure temperature step and precision for UI controls
        self._attr_target_temperature_step = 1.0
        self._attr_precision = 1.0
        
        # Extract thermostat capabilities from service properties
        props = service_data.get("props", {})
        sup_modes = props.get("sup_modes", [])
        sup_temperatures = props.get("sup_temperatures", {})
        
        # Map FIMP modes to Home Assistant HVAC modes
        # For floor heating thermostats, we only use HEAT mode
        self._fimp_to_ha_mode = {
            "heat": HVACMode.HEAT,
        }

        self._ha_to_fimp_mode = {HVACMode.HEAT: "heat"}

        # Set supported HVAC modes - only HEAT for floor heating
        self._attr_hvac_modes = [HVACMode.HEAT]

        # Set preset modes (custom FIMP modes like sleep, away, home, etc.)
        # These are scheduling/comfort modes that control the thermostat behavior
        self._attr_preset_modes = [mode for mode in sup_modes if mode not in ["off", "heat", "cool", "auto"]]

        _LOGGER.info(
            "Thermostat %s initialized - Supported modes: %s, HVAC modes: %s, Preset modes: %s",
            device_address,
            sup_modes,
            self._attr_hvac_modes,
            self._attr_preset_modes
        )
        
        # Set temperature limits
        heat_temps = sup_temperatures.get("heat", {})
        self._attr_min_temp = heat_temps.get("min", 5)
        self._attr_max_temp = heat_temps.get("max", 35)
        
        # Current state with defaults to show controls
        self._attr_hvac_mode = HVACMode.HEAT  # Default to heat mode
        self._attr_hvac_action = HVACAction.IDLE  # Default to idle state
        self._attr_current_temperature = None
        self._attr_target_temperature = 20.0  # Default target temperature to show controls
        self._attr_preset_mode = None
        
        # Extract service address for topic generation
        service_address = service_data.get("address", "")
        # Extract the last part after the last /ad:
        # Example: "/rt:dev/rn:zigbee/ad:1/sv:thermostat/ad:1_1" -> "1_1"
        address_parts = service_address.split("/ad:")
        self._service_address = address_parts[-1] if address_parts else "unknown"

        _LOGGER.info(
            "Thermostat device %s service address extracted: %s (from: %s)",
            device_address,
            self._service_address,
            service_address
        )
        
        # Set up subscriptions for thermostat updates
        self._setup_subscriptions()

    def _setup_subscriptions(self) -> None:
        """Set up MQTT subscriptions for thermostat updates."""
        # Subscribe to thermostat mode and setpoint updates
        topic_pattern = f"pt:j1/mt:evt/rt:dev/rn:zigbee/ad:1/sv:thermostat/ad:{self._service_address}"
        self._client.register_message_callback(topic_pattern, self._handle_thermostat_update)
        
        # Find temperature sensor service addresses for this device
        device_services = self._device_data.get("services", [])
        temp_sensor_addresses = []
        
        for service in device_services:
            if service.get("name") == "sensor_temp":
                service_address = service.get("address", "")
                # Extract the service address part (e.g., "1_1" from "/rt:dev/rn:zigbee/ad:1/sv:sensor_temp/ad:1_1")
                address_parts = service_address.split("/ad:")
                if len(address_parts) > 1:
                    temp_sensor_addresses.append(address_parts[-1])
        
        # Subscribe to all temperature sensor updates for this device
        for temp_address in temp_sensor_addresses:
            temp_topic_pattern = f"pt:j1/mt:evt/rt:dev/rn:zigbee/ad:1/sv:sensor_temp/ad:{temp_address}"
            self._client.register_message_callback(temp_topic_pattern, self._handle_temperature_update)
            _LOGGER.debug("Thermostat %s subscribing to temperature sensor: %s", self._device_address, temp_topic_pattern)

    async def async_added_to_hass(self) -> None:
        """Handle entity added to Home Assistant."""
        await super().async_added_to_hass()
        # Request initial thermostat data
        await self.async_update()

    def _handle_thermostat_update(self, topic: str, message: dict[str, Any]) -> None:
        """Handle thermostat mode and setpoint updates."""
        msg_type = message.get("type")
        
        if msg_type == FIMP_INTERFACE_EVT_MODE_REPORT:
            # Handle mode updates
            fimp_mode = message.get("val")

            # Check if this is a preset mode
            if fimp_mode in self._attr_preset_modes:
                # This is a custom preset mode (home, away, sleep, etc.)
                self._attr_preset_mode = fimp_mode
                self._attr_hvac_mode = HVACMode.HEAT  # Preset modes operate in heat mode
            elif fimp_mode == "heat":
                # Standard heat mode - clear preset
                self._attr_hvac_mode = HVACMode.HEAT
                self._attr_preset_mode = None
            else:
                # Unknown mode - log warning
                _LOGGER.warning(
                    "Thermostat %s received unexpected mode: %s",
                    self._device_address,
                    fimp_mode
                )
                return

            if self.hass is not None:
                self.schedule_update_ha_state()
                
        elif msg_type == FIMP_INTERFACE_EVT_SETPOINT_REPORT:
            # Handle setpoint updates
            setpoint_data = message.get("val", {})
            if isinstance(setpoint_data, dict):
                temp_str = setpoint_data.get("temp")
                if temp_str:
                    try:
                        self._attr_target_temperature = float(temp_str)
                        if self.hass is not None:
                            self.schedule_update_ha_state()
                    except (ValueError, TypeError):
                        pass

        elif msg_type == FIMP_INTERFACE_EVT_STATE_REPORT:
            # Handle state updates (idle or heat for floor heating thermostats)
            fimp_state = message.get("val")
            _LOGGER.info(
                "Thermostat %s state report received - FIMP state: %s, current HA action: %s",
                self._device_address,
                fimp_state,
                self._attr_hvac_action
            )

            # Map FIMP state to Home Assistant HVAC action
            if fimp_state == "idle":
                self._attr_hvac_action = HVACAction.IDLE
            elif fimp_state == "heat":
                self._attr_hvac_action = HVACAction.HEATING
            else:
                _LOGGER.warning(
                    "Thermostat %s received unexpected FIMP state: %s (expected 'idle' or 'heat')",
                    self._device_address,
                    fimp_state
                )
                return

            _LOGGER.info(
                "Thermostat %s HVAC action updated to: %s (FIMP state: %s)",
                self._device_address,
                self._attr_hvac_action,
                fimp_state
            )
            if self.hass is not None:
                self.schedule_update_ha_state()

    def _handle_temperature_update(self, topic: str, message: dict[str, Any]) -> None:
        """Handle current temperature updates."""
        if message.get("type") == "evt.sensor.report":
            temp_value = message.get("val")
            if temp_value is not None:
                self._attr_current_temperature = temp_value
                if self.hass is not None:
                    self.schedule_update_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        if hvac_mode not in self._attr_hvac_modes:
            return

        # For floor heating thermostats, we only support HEAT mode
        # Setting HEAT mode means clearing any preset
        if hvac_mode == HVACMode.HEAT:
            topic = f"pt:j1/mt:cmd/rt:dev/rn:zigbee/ad:1/sv:thermostat/ad:{self._service_address}"
            await self._client.async_send_fimp_message(
                topic=topic,
                service="thermostat",
                msg_type=FIMP_INTERFACE_CMD_MODE_SET,
                value_type="string",
                value="heat",
            )

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        temperature = kwargs.get("temperature")
        if temperature is None:
            return
            
        # Clamp temperature to limits
        temperature = max(self._attr_min_temp, min(self._attr_max_temp, temperature))
        
        # Send setpoint command
        setpoint_data = {
            "type": "heat",
            "temp": str(temperature),
            "unit": "C"
        }
        
        topic = f"pt:j1/mt:cmd/rt:dev/rn:zigbee/ad:1/sv:thermostat/ad:{self._service_address}"
        await self._client.async_send_fimp_message(
            topic=topic,
            service="thermostat",
            msg_type=FIMP_INTERFACE_CMD_SETPOINT_SET,
            value_type="str_map",
            value=setpoint_data,
        )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        if preset_mode not in self._attr_preset_modes:
            return
            
        topic = f"pt:j1/mt:cmd/rt:dev/rn:zigbee/ad:1/sv:thermostat/ad:{self._service_address}"
        await self._client.async_send_fimp_message(
            topic=topic,
            service="thermostat",
            msg_type=FIMP_INTERFACE_CMD_MODE_SET,
            value_type="string",
            value=preset_mode,
        )

    async def async_update(self) -> None:
        """Update thermostat state from device."""
        topic = f"pt:j1/mt:cmd/rt:dev/rn:zigbee/ad:1/sv:thermostat/ad:{self._service_address}"
        
        # Request current mode
        await self._client.async_send_fimp_message(
            topic=topic,
            service="thermostat",
            msg_type=FIMP_INTERFACE_CMD_MODE_GET_REPORT,
            value_type="null",
            value=None,
        )
        
        # Request current setpoint
        await self._client.async_send_fimp_message(
            topic=topic,
            service="thermostat",
            msg_type=FIMP_INTERFACE_CMD_SETPOINT_GET_REPORT,
            value_type="string",
            value="heat",
        )

        # Request current state (idle/heating)
        await self._client.async_send_fimp_message(
            topic=topic,
            service="thermostat",
            msg_type=FIMP_INTERFACE_CMD_STATE_GET_REPORT,
            value_type="null",
            value=None,
        )
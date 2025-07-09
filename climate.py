"""Climate platform for Futurehome FIMP thermostats."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import UnitOfTemperature

from .const import (
    DOMAIN,
    ENTRY_DATA_CLIENT,
    ENTRY_DATA_DEVICES,
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

    entities = []
    
    for device_address, device_data in devices.items():
        services = device_data.get("services", [])
        
        # Find thermostat services
        for service in services:
            if service.get("name") == FIMP_SERVICE_THERMOSTAT:
                entity = FimpThermostat(
                    client=client,
                    device_address=device_address,
                    device_data=device_data,
                    service_data=service,
                )
                entities.append(entity)
                _LOGGER.info(
                    "Added thermostat entity for device %s: %s",
                    device_address,
                    device_data.get("product_name", "Unknown Thermostat")
                )

    if entities:
        async_add_entities(entities, True)




class FimpThermostat(ClimateEntity):
    """Representation of a Futurehome FIMP thermostat (discovery only)."""

    def __init__(
        self,
        client: FimpClient,
        device_address: str,
        device_data: dict,
        service_data: dict,
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
            "via_device": (DOMAIN, "hub"),
        }
        
        # Climate attributes
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE |
            ClimateEntityFeature.PRESET_MODE
        )
        
        # Extract thermostat capabilities from service properties
        props = service_data.get("props", {})
        sup_modes = props.get("sup_modes", [])
        sup_temperatures = props.get("sup_temperatures", {})
        
        # Map FIMP modes to Home Assistant HVAC modes
        self._fimp_to_ha_mode = {
            "off": HVACMode.OFF,
            "heat": HVACMode.HEAT,
            "cool": HVACMode.COOL,
            "auto": HVACMode.AUTO,
            "home": HVACMode.HEAT,  # Custom mode mapped to heat
            "away": HVACMode.OFF,   # Custom mode mapped to off
            "sleep": HVACMode.HEAT, # Custom mode mapped to heat
        }
        
        self._ha_to_fimp_mode = {v: k for k, v in self._fimp_to_ha_mode.items()}
        
        # Set supported HVAC modes
        self._attr_hvac_modes = []
        for fimp_mode in sup_modes:
            if fimp_mode in self._fimp_to_ha_mode:
                ha_mode = self._fimp_to_ha_mode[fimp_mode]
                if ha_mode not in self._attr_hvac_modes:
                    self._attr_hvac_modes.append(ha_mode)
        
        # Always ensure OFF mode is available
        if HVACMode.OFF not in self._attr_hvac_modes:
            self._attr_hvac_modes.append(HVACMode.OFF)
            
        # Set preset modes (custom FIMP modes)
        self._attr_preset_modes = [mode for mode in sup_modes if mode not in ["off", "heat", "cool", "auto"]]
        
        # Set temperature limits
        heat_temps = sup_temperatures.get("heat", {})
        self._attr_min_temp = heat_temps.get("min", 5)
        self._attr_max_temp = heat_temps.get("max", 35)
        
        # Current state
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_current_temperature = None
        self._attr_target_temperature = None
        self._attr_preset_mode = None
        
        # Extract service address for topic generation
        service_address = service_data.get("address", "")
        address_parts = service_address.split("/")
        self._service_address = address_parts[-1] if address_parts else "unknown"
        
        # Set up subscriptions for thermostat updates
        self._setup_subscriptions()

    def _setup_subscriptions(self) -> None:
        """Set up MQTT subscriptions for thermostat updates."""
        # Subscribe to thermostat mode and setpoint updates
        topic_pattern = f"pt:j1/mt:evt/rt:dev/rn:zigbee/ad:1/sv:thermostat/ad:{self._service_address}"
        self._client.register_message_callback(topic_pattern, self._handle_thermostat_update)
        
        # Subscribe to temperature sensor updates for current temperature
        temp_topic_pattern = f"pt:j1/mt:evt/rt:dev/rn:zigbee/ad:1/sv:sensor_temp/ad:{self._device_address}_1"
        self._client.register_message_callback(temp_topic_pattern, self._handle_temperature_update)

    def _handle_thermostat_update(self, topic: str, message: dict[str, Any]) -> None:
        """Handle thermostat mode and setpoint updates."""
        msg_type = message.get("type")
        
        if msg_type == FIMP_INTERFACE_EVT_MODE_REPORT:
            # Handle mode updates
            fimp_mode = message.get("val")
            if fimp_mode in self._fimp_to_ha_mode:
                if fimp_mode in ["home", "away", "sleep"]:
                    # Custom preset modes
                    self._attr_preset_mode = fimp_mode
                    self._attr_hvac_mode = self._fimp_to_ha_mode[fimp_mode]
                else:
                    # Standard HVAC modes
                    self._attr_hvac_mode = self._fimp_to_ha_mode[fimp_mode]
                    self._attr_preset_mode = None
                self.schedule_update_ha_state()
                
        elif msg_type == FIMP_INTERFACE_EVT_SETPOINT_REPORT:
            # Handle setpoint updates
            setpoint_data = message.get("val", {})
            if isinstance(setpoint_data, dict):
                temp_str = setpoint_data.get("temp")
                if temp_str:
                    try:
                        self._attr_target_temperature = float(temp_str)
                        self.schedule_update_ha_state()
                    except (ValueError, TypeError):
                        pass

    def _handle_temperature_update(self, topic: str, message: dict[str, Any]) -> None:
        """Handle current temperature updates."""
        if message.get("type") == "evt.sensor.report":
            temp_value = message.get("val")
            if temp_value is not None:
                self._attr_current_temperature = temp_value
                self.schedule_update_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        if hvac_mode not in self._attr_hvac_modes:
            return
            
        # Find corresponding FIMP mode
        fimp_mode = None
        for fimp, ha in self._fimp_to_ha_mode.items():
            if ha == hvac_mode:
                fimp_mode = fimp
                break
                
        if fimp_mode:
            topic = f"pt:j1/mt:cmd/rt:dev/rn:zigbee/ad:1/sv:thermostat/ad:{self._service_address}"
            await self._client.async_send_fimp_message(
                topic=topic,
                service="thermostat",
                msg_type=FIMP_INTERFACE_CMD_MODE_SET,
                value_type="string",
                value=fimp_mode,
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
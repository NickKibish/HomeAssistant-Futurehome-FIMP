"""Climate platform for Futurehome FIMP thermostats."""
from __future__ import annotations

import logging

from homeassistant.components.climate import (
    ClimateEntity,
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
        
        # Basic climate attributes (discovery only - no control)
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_hvac_modes = [HVACMode.OFF]  # Minimal mode for discovery
        self._attr_hvac_mode = HVACMode.OFF
        # No features for discovery only - use empty flag instead of integer 0

    async def async_update(self) -> None:
        """Update method - no actual updates for discovery only."""
        pass
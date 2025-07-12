"""The Futurehome FIMP integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntryType

from .const import (
    DOMAIN,
    CONF_HUB_IP,
    CONF_MQTT_USERNAME,
    CONF_MQTT_PASSWORD,
    CONF_MQTT_PORT,
    ENTRY_DATA_CLIENT,
    ENTRY_DATA_HUB_INFO,
    ENTRY_DATA_DEVICES,
    ENTRY_DATA_BRIDGE_DEVICE_ID,
    BRIDGE_MANUFACTURER,
    BRIDGE_MODEL,
)
from .fimp_client import FimpClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["climate", "sensor", "button"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Futurehome FIMP from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    hub_ip = entry.data[CONF_HUB_IP]
    username = entry.data[CONF_MQTT_USERNAME]
    password = entry.data[CONF_MQTT_PASSWORD]
    port = entry.data[CONF_MQTT_PORT]

    _LOGGER.debug("Setting up Futurehome FIMP integration for hub %s:%s", hub_ip, port)

    # Create FIMP client
    client = FimpClient(
        host=hub_ip,
        port=port,
        username=username,
        password=password,
        hass=hass,
    )

    try:
        # Connect to MQTT broker and verify connection
        await client.async_connect()
        _LOGGER.info("Successfully connected to Futurehome hub at %s:%s", hub_ip, port)
    except Exception as err:
        _LOGGER.error("Failed to connect to Futurehome hub: %s", err)
        raise ConfigEntryNotReady(f"Could not connect to hub: {err}") from err

    # Create bridge device in device registry
    device_registry = dr.async_get(hass)
    bridge_device_id = f"{DOMAIN}_bridge_{hub_ip.replace('.', '_')}"
    bridge_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, bridge_device_id)},
        manufacturer=BRIDGE_MANUFACTURER,
        model=BRIDGE_MODEL,
        name=f"Futurehome Hub ({hub_ip})",
        entry_type=DeviceEntryType.SERVICE,
        sw_version="1.0.0",
    )
    _LOGGER.debug("Created bridge device: %s", bridge_device_id)

    # Store client and hub info
    hass.data[DOMAIN][entry.entry_id] = {
        ENTRY_DATA_CLIENT: client,
        ENTRY_DATA_HUB_INFO: {
            "host": hub_ip,
            "port": port,
            "username": username,
        },
        ENTRY_DATA_DEVICES: {},
        ENTRY_DATA_BRIDGE_DEVICE_ID: bridge_device_id,
    }
    
    # Track if platforms have been set up to avoid duplicates
    platforms_setup = False
    
    # Register device discovery callback
    def on_device_discovered(device_address: str, device_data: dict) -> None:
        """Handle discovered thermostat devices."""
        nonlocal platforms_setup
        
        _LOGGER.info("Discovered thermostat device: %s", device_address)
        
        # Check if this is a new device
        existing_devices = hass.data[DOMAIN][entry.entry_id][ENTRY_DATA_DEVICES]
        is_new_device = device_address not in existing_devices
        
        # Store device data
        existing_devices[device_address] = device_data
        
        # Set up platforms after first device discovery
        if not platforms_setup:
            platforms_setup = True
            _LOGGER.info("Setting up platforms after first device discovery")
            asyncio.run_coroutine_threadsafe(
                hass.config_entries.async_forward_entry_setups(entry, PLATFORMS), hass.loop
            )
        # If platforms are already set up and this is a new device, reload platforms
        elif is_new_device:
            _LOGGER.info("New device discovered, reloading platforms to include device %s", device_address)
            # Reload platforms instead of entire integration to preserve existing data
            async def reload_platforms():
                await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
                await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
            
            asyncio.run_coroutine_threadsafe(reload_platforms(), hass.loop)
    
    client.register_device_discovery_callback(on_device_discovered)
    
    # Start device discovery
    await client.async_start_device_discovery()

    _LOGGER.info("Futurehome FIMP integration setup completed")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading Futurehome FIMP integration")

    # Unload platforms
    if PLATFORMS:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        if not unload_ok:
            return False

    # Disconnect MQTT client
    if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        client: FimpClient = hass.data[DOMAIN][entry.entry_id][ENTRY_DATA_CLIENT]
        await client.async_disconnect()

        # Remove data
        hass.data[DOMAIN].pop(entry.entry_id)

    _LOGGER.info("Futurehome FIMP integration unloaded successfully")
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
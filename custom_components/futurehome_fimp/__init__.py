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

PLATFORMS: list[str] = ["climate", "sensor", "button", "switch"]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Futurehome FIMP integration from YAML configuration."""
    _LOGGER.info("Futurehome FIMP integration loaded from YAML configuration")
    return True


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
    
    # Track platform setup state
    platforms_setup = False
    platforms_setting_up = False

    # Register device discovery callback
    def on_device_discovered(device_address: str, device_data: dict) -> None:
        """Handle discovered devices with supported services."""
        nonlocal platforms_setup, platforms_setting_up

        _LOGGER.info("Discovered device: %s", device_address)

        # Store device data
        existing_devices = hass.data[DOMAIN][entry.entry_id][ENTRY_DATA_DEVICES]
        existing_devices[device_address] = device_data

        # Set up platforms after first device discovery (only once)
        if not platforms_setup and not platforms_setting_up:
            platforms_setting_up = True
            _LOGGER.info("First device discovered, waiting for more devices before platform setup...")

            async def setup_platforms_delayed():
                nonlocal platforms_setup, platforms_setting_up
                try:
                    device_count = len(hass.data[DOMAIN][entry.entry_id][ENTRY_DATA_DEVICES])
                    _LOGGER.info("Setting up platforms with %d discovered devices", device_count)
                    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
                    platforms_setup = True
                    _LOGGER.info("Platforms setup completed")
                except Exception as err:
                    _LOGGER.error("Failed to setup platforms: %s", err)
                finally:
                    platforms_setting_up = False

            asyncio.run_coroutine_threadsafe(setup_platforms_delayed(), hass.loop)

    client.register_device_discovery_callback(on_device_discovered)

    # Start device discovery
    await client.async_start_device_discovery()

    _LOGGER.info("Futurehome FIMP integration setup completed")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading Futurehome FIMP integration")

    # Check if integration data exists
    if DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]:
        _LOGGER.debug("Integration data not found, nothing to unload")
        return True

    # Disconnect MQTT client first
    try:
        client: FimpClient = hass.data[DOMAIN][entry.entry_id][ENTRY_DATA_CLIENT]
        await client.async_disconnect()
        _LOGGER.debug("MQTT client disconnected")
    except Exception as err:
        _LOGGER.warning("Error disconnecting MQTT client: %s", err)

    # Unload platforms only if they were loaded
    unload_ok = True
    try:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        _LOGGER.debug("Platforms unloaded successfully")
    except ValueError as err:
        if "Config entry was never loaded" in str(err):
            _LOGGER.debug("Platforms were never loaded, skipping unload")
            unload_ok = True  # This is not an error, just means platforms weren't loaded
        else:
            _LOGGER.error("Error unloading platforms: %s", err)
            unload_ok = False
    except Exception as err:
        _LOGGER.error("Unexpected error unloading platforms: %s", err)
        unload_ok = False

    # Remove data
    try:
        hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.debug("Integration data removed")
    except KeyError:
        _LOGGER.debug("Integration data was already removed")

    if unload_ok:
        _LOGGER.info("Futurehome FIMP integration unloaded successfully")
    else:
        _LOGGER.warning("Futurehome FIMP integration unloaded with warnings")

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
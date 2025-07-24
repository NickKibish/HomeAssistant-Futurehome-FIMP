"""Button platform for Futurehome FIMP bridge controls."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import EntityCategory

from .const import (
    DOMAIN,
    ENTRY_DATA_CLIENT,
    ENTRY_DATA_BRIDGE_DEVICE_ID,
    ENTRY_DATA_HUB_INFO,
    BRIDGE_MANUFACTURER,
    BRIDGE_MODEL,
    FIMP_ZIGBEE_ADAPTER_TOPIC,
    FIMP_GATEWAY_TOPIC,
    FIMP_INTERFACE_CMD_ZIGBEE_PERMIT_JOIN,
    FIMP_INTERFACE_CMD_SYSTEM_REBOOT,
    FIMP_VAL_TYPE_BOOL,
    FIMP_VAL_TYPE_NULL,
)
from .fimp_client import FimpClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Futurehome FIMP button entities from a config entry."""
    client: FimpClient = hass.data[DOMAIN][config_entry.entry_id][ENTRY_DATA_CLIENT]
    bridge_device_id: str = hass.data[DOMAIN][config_entry.entry_id][ENTRY_DATA_BRIDGE_DEVICE_ID]
    hub_info: dict = hass.data[DOMAIN][config_entry.entry_id][ENTRY_DATA_HUB_INFO]

    entities = [
        PermitJoinButton(client, bridge_device_id, hub_info),
        RebootHubButton(client, bridge_device_id, hub_info),
    ]

    async_add_entities(entities, True)


class PermitJoinButton(ButtonEntity):
    """Button to enable Zigbee device pairing."""

    def __init__(self, client: FimpClient, bridge_device_id: str, hub_info: dict) -> None:
        """Initialize the permit join button."""
        self._client = client
        self._bridge_device_id = bridge_device_id
        self._hub_info = hub_info
        
        # Entity configuration
        self._attr_name = "Permit Join"
        self._attr_unique_id = f"{DOMAIN}_{bridge_device_id}_permit_join"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_icon = "mdi:plus-network"
        
        # Device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, bridge_device_id)},
            "manufacturer": BRIDGE_MANUFACTURER,
            "model": BRIDGE_MODEL,
            "name": f"Futurehome Hub ({hub_info['host']})",
        }

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._client.is_connected

    async def async_press(self) -> None:
        """Enable Zigbee device pairing for 2 minutes."""
        _LOGGER.info("Enabling Zigbee device pairing for 2 minutes")
        
        try:
            # Send permit join command to Zigbee adapter according to FIMP specification
            await self._client.async_send_fimp_message(
                topic=FIMP_ZIGBEE_ADAPTER_TOPIC,
                service="zigbee",
                msg_type=FIMP_INTERFACE_CMD_ZIGBEE_PERMIT_JOIN,
                value_type=FIMP_VAL_TYPE_BOOL,
                value=True,
                properties={"supports_pin_request": "true"},  # Enable PIN support
            )
            _LOGGER.info("Permit join command sent successfully")
            
            # Automatically stop permit join after 2 minutes (120 seconds)
            # Most adapters will stop automatically, but we can send stop command as well
            import asyncio
            asyncio.create_task(self._auto_stop_permit_join())
            
        except Exception as err:
            _LOGGER.error("Failed to send permit join command: %s", err)
    
    async def _auto_stop_permit_join(self) -> None:
        """Automatically stop permit join after 2 minutes."""
        import asyncio
        await asyncio.sleep(120)  # Wait 2 minutes
        try:
            await self._client.async_send_fimp_message(
                topic=FIMP_ZIGBEE_ADAPTER_TOPIC,
                service="zigbee", 
                msg_type=FIMP_INTERFACE_CMD_ZIGBEE_PERMIT_JOIN,
                value_type=FIMP_VAL_TYPE_BOOL,
                value=False,
            )
            _LOGGER.info("Permit join automatically stopped after 2 minutes")
        except Exception as err:
            _LOGGER.error("Failed to stop permit join: %s", err)


class RebootHubButton(ButtonEntity):
    """Button to reboot the Futurehome hub."""

    def __init__(self, client: FimpClient, bridge_device_id: str, hub_info: dict) -> None:
        """Initialize the reboot hub button."""
        self._client = client
        self._bridge_device_id = bridge_device_id
        self._hub_info = hub_info
        
        # Entity configuration
        self._attr_name = "Reboot Hub"
        self._attr_unique_id = f"{DOMAIN}_{bridge_device_id}_reboot"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_icon = "mdi:restart"
        
        # Device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, bridge_device_id)},
            "manufacturer": BRIDGE_MANUFACTURER,
            "model": BRIDGE_MODEL,
            "name": f"Futurehome Hub ({hub_info['host']})",
        }

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._client.is_connected

    async def async_press(self) -> None:
        """Reboot the Futurehome hub."""
        _LOGGER.warning("Rebooting Futurehome hub - this will cause temporary disconnection")
        
        try:
            # Send reboot command to gateway
            await self._client.async_send_fimp_message(
                topic=FIMP_GATEWAY_TOPIC,
                service="gateway",
                msg_type=FIMP_INTERFACE_CMD_SYSTEM_REBOOT,
                value_type=FIMP_VAL_TYPE_NULL,
                value=None,
            )
            _LOGGER.info("Hub reboot command sent successfully")
        except Exception as err:
            _LOGGER.error("Failed to send hub reboot command: %s", err)
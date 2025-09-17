"""Switch platform for Futurehome FIMP integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    ENTRY_DATA_CLIENT,
    ENTRY_DATA_DEVICES,
    ENTRY_DATA_BRIDGE_DEVICE_ID,
    BRIDGE_MANUFACTURER,
    BRIDGE_MODEL,
    FIMP_SERVICE_OUT_BIN_SWITCH,
    FIMP_INTERFACE_CMD_BINARY_SET,
    FIMP_INTERFACE_CMD_BINARY_GET_REPORT,
    FIMP_INTERFACE_EVT_BINARY_REPORT,
)
from .fimp_client import FimpClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch entities from config entry."""
    client: FimpClient = hass.data[DOMAIN][entry.entry_id][ENTRY_DATA_CLIENT]
    devices = hass.data[DOMAIN][entry.entry_id][ENTRY_DATA_DEVICES]
    bridge_device_id = hass.data[DOMAIN][entry.entry_id][ENTRY_DATA_BRIDGE_DEVICE_ID]

    entities = []

    for device_address, device_data in devices.items():
        if "services" not in device_data:
            continue

        # Find binary switch services
        for service in device_data["services"]:
            if service["name"] == FIMP_SERVICE_OUT_BIN_SWITCH and service.get("enabled", True):
                service_address = service["address"]
                
                _LOGGER.debug(
                    "Creating switch entity for device %s, service %s",
                    device_address,
                    service_address
                )
                
                entity = FimpSwitchEntity(
                    client=client,
                    device_address=device_address,
                    device_data=device_data,
                    service_address=service_address,
                    bridge_device_id=bridge_device_id,
                )
                entities.append(entity)

    if entities:
        async_add_entities(entities, update_before_add=True)
        _LOGGER.info("Added %d switch entities", len(entities))


class FimpSwitchEntity(SwitchEntity):
    """Representation of a FIMP binary switch."""

    def __init__(
        self,
        client: FimpClient,
        device_address: str,
        device_data: dict,
        service_address: str,
        bridge_device_id: str,
    ) -> None:
        """Initialize the switch."""
        self._client = client
        self._device_address = device_address
        self._device_data = device_data
        self._service_address = service_address
        self._bridge_device_id = bridge_device_id
        self._is_on = False
        self._available = True
        
        # Register for connection status updates
        self._client.register_connection_status_callback(self._on_connection_status_changed)

        # Extract service address components for topic construction
        # Format: /rt:dev/rn:zigbee/ad:1/sv:out_bin_switch/ad:9_1
        parts = service_address.strip("/").split("/")
        self._resource_name = None
        self._adapter_id = None
        self._service_id = None
        
        for part in parts:
            if part.startswith("rn:"):
                self._resource_name = part[3:]
            elif part.startswith("ad:") and self._adapter_id is None:
                self._adapter_id = part[3:]
            elif part.startswith("ad:") and self._adapter_id is not None:
                self._service_id = part[3:]

        # Generate unique ID and name
        self._attr_unique_id = f"{DOMAIN}_{device_address}_switch_{self._service_id}"
        
        product_name = device_data.get("product_name", f"Device {device_address}")
        self._attr_name = f"{product_name} Switch"
        
        # Register for FIMP messages
        self._register_fimp_callbacks()

    def _register_fimp_callbacks(self) -> None:
        """Register callbacks for FIMP messages."""
        def on_binary_report(topic: str, message_data: dict) -> None:
            """Handle binary switch report."""
            if message_data.get("type") == FIMP_INTERFACE_EVT_BINARY_REPORT:
                self._is_on = bool(message_data.get("val", False))
                self._available = True
                if self.hass is not None:
                    self.schedule_update_ha_state()
                _LOGGER.debug(
                    "Switch %s state updated to %s",
                    self.name,
                    "on" if self._is_on else "off"
                )

        # Register callback with client
        topic_pattern = f"pt:j1/mt:evt/rt:dev/rn:{self._resource_name}/ad:{self._adapter_id}/sv:out_bin_switch/ad:{self._service_id}"
        self._client.register_message_callback(topic_pattern, on_binary_report)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_address)},
            name=self._device_data.get("product_name", f"Device {self._device_address}"),
            manufacturer=self._device_data.get("manufacturer_id", "Unknown"),
            model=self._device_data.get("product_id", "Unknown"),
            sw_version=self._device_data.get("sw_ver", "Unknown"),
            hw_version=self._device_data.get("hw_ver", "Unknown"),
            via_device=(DOMAIN, self._bridge_device_id),
        )

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        return self._is_on

    @property
    def available(self) -> bool:
        """Return true if switch is available."""
        return self._available and self._client.is_connected

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._send_binary_command(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._send_binary_command(False)

    async def async_update(self) -> None:
        """Request switch status update."""
        topic = f"pt:j1/mt:cmd/rt:dev/rn:{self._resource_name}/ad:{self._adapter_id}/sv:out_bin_switch/ad:{self._service_id}"
        
        await self._client.async_send_fimp_message(
            topic=topic,
            service=FIMP_SERVICE_OUT_BIN_SWITCH,
            msg_type=FIMP_INTERFACE_CMD_BINARY_GET_REPORT,
            value_type="null",
            value=None,
        )

    async def _send_binary_command(self, state: bool) -> None:
        """Send binary switch command to device."""
        topic = f"pt:j1/mt:cmd/rt:dev/rn:{self._resource_name}/ad:{self._adapter_id}/sv:out_bin_switch/ad:{self._service_id}"
        
        try:
            await self._client.async_send_fimp_message(
                topic=topic,
                service=FIMP_SERVICE_OUT_BIN_SWITCH,
                msg_type=FIMP_INTERFACE_CMD_BINARY_SET,
                value_type="bool",
                value=state,
            )
            _LOGGER.debug(
                "Sent switch command to %s: %s",
                self.name,
                "on" if state else "off"
            )
        except Exception as err:
            _LOGGER.error(
                "Failed to send switch command to %s: %s",
                self.name,
                err
            )
            self._available = False
            if self.hass is not None:
                self.schedule_update_ha_state()

    def _on_connection_status_changed(self, connected: bool) -> None:
        """Handle MQTT connection status change."""
        _LOGGER.debug("Switch %s connection status changed to %s", self.name, connected)
        # Update Home Assistant about availability change
        if self.hass is not None:
            self.schedule_update_ha_state()
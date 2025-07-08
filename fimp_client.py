"""FIMP MQTT Client for Futurehome integration."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Callable

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None

from .const import (
    FIMP_DISCOVERY_TOPIC,
    FIMP_DISCOVERY_EVENT_TOPIC,
    FIMP_GATEWAY_TOPIC,
    FIMP_GATEWAY_EVENT_TOPIC,
    FIMP_ZIGBEE_ADAPTER_TOPIC,
    FIMP_ZIGBEE_ADAPTER_EVENT_TOPIC,
    FIMP_TOPIC_ROOT,
    FIMP_SERVICE_THERMOSTAT,
    FIMP_INTERFACE_CMD_NETWORK_GET_ALL_NODES,
    FIMP_INTERFACE_EVT_NETWORK_ALL_NODES_REPORT,
    FIMP_INTERFACE_CMD_THING_GET_INCLUSION_REPORT,
    FIMP_INTERFACE_EVT_THING_INCLUSION_REPORT,
    FIMP_INTERFACE_CMD_DISCOVERY_REQUEST,
    FIMP_INTERFACE_EVT_DISCOVERY_REPORT,
)

_LOGGER = logging.getLogger(__name__)


class FimpClient:
    """FIMP MQTT client for communicating with Futurehome hub."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        hass: HomeAssistant,
    ) -> None:
        """Initialize the FIMP client."""
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.hass = hass
        self._client = None
        self._connected = False
        self._message_callbacks: dict[str, list[Callable]] = {}
        self._loop = None
        self._discovered_devices: dict[str, dict] = {}
        self._device_discovery_callbacks: list[Callable] = []

    async def async_connect(self) -> None:
        """Connect to the MQTT broker."""
        if mqtt is None:
            raise RuntimeError("paho-mqtt not installed")

        self._client = mqtt.Client()
        self._client.username_pw_set(self.username, self.password)
        
        # Set up callbacks
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

        # Connect to broker
        try:
            _LOGGER.debug("Connecting to MQTT broker at %s:%s", self.host, self.port)
            self._client.connect(self.host, self.port, 60)
            
            # Start the MQTT loop in a separate thread
            self._client.loop_start()
            
            # Wait for connection
            for _ in range(100):  # Wait up to 10 seconds
                if self._connected:
                    break
                await asyncio.sleep(0.1)
            else:
                raise RuntimeError("Connection timeout")
                
            _LOGGER.info("Connected to FIMP MQTT broker")
            
            # Subscribe to discovery events and gateway events
            await self._setup_subscriptions()
            
        except Exception as err:
            _LOGGER.error("Failed to connect to MQTT broker: %s", err)
            raise

    async def async_disconnect(self) -> None:
        """Disconnect from the MQTT broker."""
        if self._client and self._connected:
            _LOGGER.debug("Disconnecting from MQTT broker")
            self._client.loop_stop()
            self._client.disconnect()
            self._connected = False

    async def _setup_subscriptions(self) -> None:
        """Set up MQTT subscriptions for FIMP topics."""
        # Subscribe to all FIMP events
        fimp_event_topic = f"{FIMP_TOPIC_ROOT}/mt:evt/+/+/+/+/+"
        fimp_response_topic = f"{FIMP_TOPIC_ROOT}/mt:rsp/+/+/+/+/+"
        
        _LOGGER.debug("Subscribing to FIMP topics")
        self._client.subscribe(fimp_event_topic)
        self._client.subscribe(fimp_response_topic)
        self._client.subscribe(FIMP_DISCOVERY_EVENT_TOPIC)
        self._client.subscribe(FIMP_GATEWAY_EVENT_TOPIC)
        self._client.subscribe(FIMP_ZIGBEE_ADAPTER_EVENT_TOPIC)
        
        # Register internal callbacks for device discovery
        self.register_message_callback(
            FIMP_ZIGBEE_ADAPTER_EVENT_TOPIC, self._handle_zigbee_adapter_message
        )
        self.register_message_callback(
            FIMP_DISCOVERY_EVENT_TOPIC, self._handle_discovery_message
        )

    def _on_connect(self, client, userdata, flags, rc) -> None:
        """Called when MQTT client connects."""
        if rc == 0:
            self._connected = True
            _LOGGER.debug("MQTT client connected successfully")
        else:
            _LOGGER.error("MQTT connection failed with code %s", rc)

    def _on_disconnect(self, client, userdata, rc) -> None:
        """Called when MQTT client disconnects."""
        self._connected = False
        if rc != 0:
            _LOGGER.warning("MQTT client disconnected unexpectedly (code: %s)", rc)
        else:
            _LOGGER.debug("MQTT client disconnected")

    def _on_message(self, client, userdata, msg) -> None:
        """Called when a message is received."""
        try:
            topic = msg.topic
            payload = msg.payload.decode("utf-8")
            
            _LOGGER.debug("Received FIMP message on topic %s: %s", topic, payload)
            
            # Parse FIMP message
            try:
                fimp_message = json.loads(payload)
                self._process_fimp_message(topic, fimp_message)
            except json.JSONDecodeError as err:
                _LOGGER.warning("Failed to parse FIMP message JSON: %s", err)
                
        except Exception as err:
            _LOGGER.error("Error processing MQTT message: %s", err)

    def _process_fimp_message(self, topic: str, message: dict[str, Any]) -> None:
        """Process a received FIMP message."""
        # Extract basic FIMP message properties
        service = message.get("serv")
        msg_type = message.get("type")
        value_type = message.get("val_t")
        value = message.get("val")
        properties = message.get("props", {})
        source = message.get("src")
        
        _LOGGER.debug(
            "Processing FIMP message: service=%s, type=%s, value_type=%s, value=%s",
            service, msg_type, value_type, value
        )
        
        # Call registered callbacks for this topic pattern
        for pattern, callbacks in self._message_callbacks.items():
            if self._topic_matches_pattern(topic, pattern):
                for callback in callbacks:
                    try:
                        callback(topic, message)
                    except Exception as err:
                        _LOGGER.error("Error in FIMP message callback: %s", err)

    def _topic_matches_pattern(self, topic: str, pattern: str) -> bool:
        """Check if a topic matches a pattern with wildcards."""
        topic_parts = topic.split("/")
        pattern_parts = pattern.split("/")
        
        if len(topic_parts) != len(pattern_parts):
            return False
            
        for topic_part, pattern_part in zip(topic_parts, pattern_parts):
            if pattern_part != "+" and pattern_part != topic_part:
                return False
                
        return True

    def register_message_callback(
        self, topic_pattern: str, callback: Callable[[str, dict], None]
    ) -> None:
        """Register a callback for messages on a specific topic pattern."""
        if topic_pattern not in self._message_callbacks:
            self._message_callbacks[topic_pattern] = []
        self._message_callbacks[topic_pattern].append(callback)

    async def async_send_fimp_message(
        self,
        topic: str,
        service: str,
        msg_type: str,
        value_type: str,
        value: Any,
        properties: dict[str, Any] | None = None,
        response_topic: str | None = None,
    ) -> None:
        """Send a FIMP message."""
        if not self._connected:
            _LOGGER.error("Cannot send FIMP message: not connected to MQTT broker")
            return

        # Create FIMP message
        fimp_message = {
            "serv": service,
            "type": msg_type,
            "val_t": value_type,
            "val": value,
            "props": properties or {},
            "tags": [],
            "uid": str(uuid.uuid4()),
            "ctime": dt_util.now().isoformat(),
            "src": "homeassistant",
            "ver": "1",
        }
        
        if response_topic:
            fimp_message["resp_to"] = response_topic

        try:
            payload = json.dumps(fimp_message)
            _LOGGER.debug("Sending FIMP message to %s: %s", topic, payload)
            self._client.publish(topic, payload)
        except Exception as err:
            _LOGGER.error("Failed to send FIMP message: %s", err)

    async def async_request_discovery(self) -> None:
        """Request discovery of all devices on the hub."""
        _LOGGER.debug("Requesting device discovery")
        await self.async_send_fimp_message(
            topic=FIMP_DISCOVERY_TOPIC,
            service="gateway",
            msg_type="cmd.discovery.get_report",
            value_type="null",
            value=None,
        )
    
    async def async_request_zigbee_devices(self) -> None:
        """Request all Zigbee devices from the Zigbee adapter."""
        _LOGGER.debug("Requesting Zigbee devices from adapter")
        await self.async_send_fimp_message(
            topic=FIMP_ZIGBEE_ADAPTER_TOPIC,
            service="zigbee",
            msg_type=FIMP_INTERFACE_CMD_NETWORK_GET_ALL_NODES,
            value_type="null",
            value=None,
        )
    
    async def async_request_device_inclusion_report(self, device_address: str) -> None:
        """Request inclusion report for a specific device."""
        _LOGGER.debug("Requesting inclusion report for device %s", device_address)
        await self.async_send_fimp_message(
            topic=FIMP_ZIGBEE_ADAPTER_TOPIC,
            service="zigbee",
            msg_type=FIMP_INTERFACE_CMD_THING_GET_INCLUSION_REPORT,
            value_type="string",
            value=device_address,
        )
    
    def _handle_zigbee_adapter_message(self, topic: str, message: dict[str, Any]) -> None:
        """Handle messages from the Zigbee adapter."""
        msg_type = message.get("type")
        service = message.get("serv")
        
        if service != "zigbee":
            return
            
        _LOGGER.debug("Received Zigbee adapter message: %s", msg_type)
        
        if msg_type == FIMP_INTERFACE_EVT_NETWORK_ALL_NODES_REPORT:
            self._handle_all_nodes_report(message)
        elif msg_type == FIMP_INTERFACE_EVT_THING_INCLUSION_REPORT:
            self._handle_inclusion_report(message)
    
    def _handle_discovery_message(self, topic: str, message: dict[str, Any]) -> None:
        """Handle system component discovery messages."""
        msg_type = message.get("type")
        service = message.get("serv")
        
        if service != "system" or msg_type != FIMP_INTERFACE_EVT_DISCOVERY_REPORT:
            return
            
        discovery_data = message.get("val", {})
        resource_type = discovery_data.get("resource_type")
        adapter_info = discovery_data.get("adapter_info", {})
        technology = adapter_info.get("technology")
        
        # Check if this is a Zigbee adapter
        if resource_type == "ad" and technology == "zigbee":
            _LOGGER.info("Found Zigbee adapter: %s", discovery_data.get("resource_full_name"))
            # Request all Zigbee devices after finding the adapter
            asyncio.run_coroutine_threadsafe(
                self.async_request_zigbee_devices(), self.hass.loop
            )
    
    def _handle_all_nodes_report(self, message: dict[str, Any]) -> None:
        """Handle all nodes report from Zigbee adapter."""
        nodes = message.get("val", [])
        if not isinstance(nodes, list):
            nodes = [nodes] if nodes else []
            
        _LOGGER.info("Received %d Zigbee nodes from adapter", len(nodes))
        
        for node in nodes:
            address = node.get("address")
            if address:
                # Store node info and request detailed inclusion report
                self._discovered_devices[address] = node
                _LOGGER.debug("Found Zigbee device: %s (%s)", address, node.get("alias", "Unknown"))
                # Request inclusion report to get service details
                asyncio.run_coroutine_threadsafe(
                    self.async_request_device_inclusion_report(address), self.hass.loop
                )
    
    def _handle_inclusion_report(self, message: dict[str, Any]) -> None:
        """Handle inclusion report for a specific device."""
        device_data = message.get("val", {})
        address = device_data.get("address")
        services = device_data.get("services", [])
        comm_tech = device_data.get("comm_tech")
        
        # Only process Zigbee devices
        if comm_tech != "zigbee":
            return
            
        # Filter for thermostat services only
        thermostat_services = [
            service for service in services 
            if service.get("name") == FIMP_SERVICE_THERMOSTAT
        ]
        
        if not thermostat_services:
            _LOGGER.debug("Device %s has no thermostat services, skipping", address)
            return
            
        _LOGGER.info(
            "Found Zigbee thermostat device: %s (%s) with %d thermostat services",
            address,
            device_data.get("product_name", "Unknown"),
            len(thermostat_services)
        )
        
        # Store full device data including services
        if address in self._discovered_devices:
            self._discovered_devices[address].update(device_data)
        else:
            self._discovered_devices[address] = device_data
            
        # Notify discovery callbacks
        for callback in self._device_discovery_callbacks:
            try:
                callback(address, device_data)
            except Exception as err:
                _LOGGER.error("Error in device discovery callback: %s", err)
    
    def register_device_discovery_callback(self, callback: Callable[[str, dict], None]) -> None:
        """Register a callback for when thermostat devices are discovered."""
        self._device_discovery_callbacks.append(callback)
    
    def get_discovered_devices(self) -> dict[str, dict]:
        """Get all discovered thermostat devices."""
        return self._discovered_devices.copy()
    
    async def async_start_device_discovery(self) -> None:
        """Start the device discovery process."""
        _LOGGER.info("Starting Zigbee thermostat device discovery")
        
        # First request system component discovery to find adapters
        await self.async_send_fimp_message(
            topic=FIMP_DISCOVERY_TOPIC,
            service="system",
            msg_type=FIMP_INTERFACE_CMD_DISCOVERY_REQUEST,
            value_type="null",
            value=None,
        )

    @property
    def is_connected(self) -> bool:
        """Return True if connected to MQTT broker."""
        return self._connected
    
    @property
    def discovered_device_count(self) -> int:
        """Return the number of discovered thermostat devices."""
        return len(self._discovered_devices)
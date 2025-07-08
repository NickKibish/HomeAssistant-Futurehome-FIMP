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
    FIMP_TOPIC_ROOT,
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

    @property
    def is_connected(self) -> bool:
        """Return True if connected to MQTT broker."""
        return self._connected
"""Config flow for Futurehome FIMP integration."""
from __future__ import annotations

import logging
import time
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None

from .const import (
    DOMAIN,
    CONF_HUB_IP,
    CONF_MQTT_USERNAME,
    CONF_MQTT_PASSWORD,
    CONF_MQTT_PORT,
    DEFAULT_MQTT_PORT,
    DEFAULT_NAME,
    ERROR_CANNOT_CONNECT,
    ERROR_INVALID_AUTH,
    ERROR_UNKNOWN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HUB_IP): str,
        vol.Required(CONF_MQTT_USERNAME): str,
        vol.Required(CONF_MQTT_PASSWORD): str,
        vol.Optional(CONF_MQTT_PORT, default=DEFAULT_MQTT_PORT): cv.port,
    }
)


def _test_mqtt_connection(hub_ip: str, port: int, username: str, password: str) -> dict[str, Any]:
    """Test MQTT connection in a blocking way."""
    if mqtt is None:
        raise CannotConnect("paho-mqtt not installed")

    client = mqtt.Client()
    client.username_pw_set(username, password)
    
    # Set up connection result tracking
    connection_result = {"connected": False, "error": None, "finished": False}
    
    def on_connect(client, userdata, flags, rc):
        """Callback for MQTT connection."""
        del userdata, flags  # Unused parameters
        if rc == 0:
            connection_result["connected"] = True
            _LOGGER.debug("MQTT connection successful")
        else:
            connection_result["error"] = rc
            _LOGGER.error("MQTT connection failed with code %s", rc)
        connection_result["finished"] = True
        client.disconnect()
    
    def on_disconnect(client, userdata, rc):
        """Callback for MQTT disconnection."""
        del client, userdata  # Unused parameters
        _LOGGER.debug("MQTT disconnected with code %s", rc)
        connection_result["finished"] = True
    
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    
    try:
        # Try to connect with a timeout
        _LOGGER.debug("Attempting MQTT connection to %s:%s", hub_ip, port)
        client.connect(hub_ip, port, 10)
        
        # Start the loop and wait for connection result
        client.loop_start()
        
        # Wait up to 10 seconds for connection
        for _ in range(100):  # 10 seconds with 0.1s intervals
            if connection_result["finished"]:
                break
            time.sleep(0.1)
        
        client.loop_stop()
        
        if not connection_result["connected"]:
            error_code = connection_result["error"]
            if error_code == 5:  # Connection refused - bad username or password
                raise InvalidAuth(f"Invalid credentials (error code: {error_code})")
            elif error_code is not None:
                raise CannotConnect(f"Connection failed (error code: {error_code})")
            else:
                raise CannotConnect("Connection timeout")
                
    except OSError as err:
        _LOGGER.error("Failed to connect to MQTT broker: %s", err)
        raise CannotConnect(f"Network error: {err}") from err
    except Exception as err:
        _LOGGER.error("Unexpected error during MQTT connection test: %s", err)
        raise CannotConnect(f"Unexpected error: {err}") from err
    finally:
        try:
            client.disconnect()
        except Exception:
            pass

    return {"success": True}


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect to the hub.
    
    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    hub_ip = data[CONF_HUB_IP]
    username = data[CONF_MQTT_USERNAME]
    password = data[CONF_MQTT_PASSWORD]
    port = data[CONF_MQTT_PORT]

    # Test MQTT connection using executor to avoid blocking
    await hass.async_add_executor_job(
        _test_mqtt_connection, hub_ip, port, username, password
    )

    # Return info that you want to store in the config entry
    return {
        "title": f"{DEFAULT_NAME} ({hub_ip})",
        "hub_ip": hub_ip,
        "mqtt_port": port,
    }


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Futurehome FIMP."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = ERROR_CANNOT_CONNECT
            except InvalidAuth:
                errors["base"] = ERROR_INVALID_AUTH
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = ERROR_UNKNOWN
            else:
                # Check if already configured
                await self.async_set_unique_id(user_input[CONF_HUB_IP])
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "default_port": str(DEFAULT_MQTT_PORT),
            },
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
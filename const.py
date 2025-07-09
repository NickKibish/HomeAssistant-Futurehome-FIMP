"""Constants for the Futurehome FIMP integration."""

# Integration domain
DOMAIN = "futurehome_fimp"

# Configuration keys
CONF_HUB_IP = "hub_ip"
CONF_MQTT_USERNAME = "mqtt_username"
CONF_MQTT_PASSWORD = "mqtt_password"
CONF_MQTT_PORT = "mqtt_port"

# Default values
DEFAULT_MQTT_PORT = 1883
DEFAULT_NAME = "Futurehome Hub"

# FIMP Protocol constants
FIMP_TOPIC_ROOT = "pt:j1"
FIMP_MSG_TYPE_CMD = "cmd"
FIMP_MSG_TYPE_EVT = "evt"
FIMP_MSG_TYPE_RSP = "rsp"

# FIMP Resource types
FIMP_RT_DEVICE = "dev"
FIMP_RT_LOCATION = "loc"
FIMP_RT_ADAPTER = "ad"
FIMP_RT_APP = "app"
FIMP_RT_CLOUD = "cloud"
FIMP_RT_DISCOVERY = "discovery"

# FIMP Discovery topics
FIMP_DISCOVERY_TOPIC = f"{FIMP_TOPIC_ROOT}/mt:cmd/rt:discovery"
FIMP_DISCOVERY_EVENT_TOPIC = f"{FIMP_TOPIC_ROOT}/mt:evt/rt:discovery"

# FIMP Gateway service
FIMP_GATEWAY_TOPIC = f"{FIMP_TOPIC_ROOT}/mt:cmd/rt:ad/rn:gateway/ad:1"
FIMP_GATEWAY_EVENT_TOPIC = f"{FIMP_TOPIC_ROOT}/mt:evt/rt:ad/rn:gateway/ad:1"

# FIMP Zigbee Adapter topics
FIMP_ZIGBEE_ADAPTER_TOPIC = f"{FIMP_TOPIC_ROOT}/mt:cmd/rt:ad/rn:zigbee/ad:1"
FIMP_ZIGBEE_ADAPTER_EVENT_TOPIC = f"{FIMP_TOPIC_ROOT}/mt:evt/rt:ad/rn:zigbee/ad:1"

# Common FIMP services
FIMP_SERVICE_OUT_BIN_SWITCH = "out_bin_switch"
FIMP_SERVICE_OUT_LVL_SWITCH = "out_lvl_switch"
FIMP_SERVICE_SENSOR_TEMP = "sensor_temp"
FIMP_SERVICE_SENSOR_HUMID = "sensor_humid"
FIMP_SERVICE_METER_ELEC = "meter_elec"
FIMP_SERVICE_THERMOSTAT = "thermostat"
FIMP_SERVICE_PARAMETERS = "parameters"

# FIMP Interface types
FIMP_INTERFACE_CMD_BINARY_SET = "cmd.binary.set"
FIMP_INTERFACE_CMD_BINARY_GET_REPORT = "cmd.binary.get_report"
FIMP_INTERFACE_EVT_BINARY_REPORT = "evt.binary.report"
FIMP_INTERFACE_CMD_LVL_SET = "cmd.lvl.set"
FIMP_INTERFACE_CMD_LVL_GET_REPORT = "cmd.lvl.get_report"
FIMP_INTERFACE_EVT_LVL_REPORT = "evt.lvl.report"
FIMP_INTERFACE_CMD_SENSOR_GET_REPORT = "cmd.sensor.get_report"
FIMP_INTERFACE_EVT_SENSOR_REPORT = "evt.sensor.report"
FIMP_INTERFACE_CMD_METER_EXT_GET_REPORT = "cmd.meter_ext.get_report"
FIMP_INTERFACE_EVT_METER_EXT_REPORT = "evt.meter_ext.report"

# FIMP Network and discovery interfaces
FIMP_INTERFACE_CMD_NETWORK_GET_ALL_NODES = "cmd.network.get_all_nodes"
FIMP_INTERFACE_EVT_NETWORK_ALL_NODES_REPORT = "evt.network.all_nodes_report"
FIMP_INTERFACE_CMD_THING_GET_INCLUSION_REPORT = "cmd.thing.get_inclusion_report"
FIMP_INTERFACE_EVT_THING_INCLUSION_REPORT = "evt.thing.inclusion_report"
FIMP_INTERFACE_CMD_DISCOVERY_REQUEST = "cmd.discovery.request"
FIMP_INTERFACE_EVT_DISCOVERY_REPORT = "evt.discovery.report"

# FIMP Thermostat interfaces
FIMP_INTERFACE_CMD_MODE_GET_REPORT = "cmd.mode.get_report"
FIMP_INTERFACE_CMD_MODE_SET = "cmd.mode.set"
FIMP_INTERFACE_EVT_MODE_REPORT = "evt.mode.report"
FIMP_INTERFACE_CMD_SETPOINT_GET_REPORT = "cmd.setpoint.get_report"
FIMP_INTERFACE_CMD_SETPOINT_SET = "cmd.setpoint.set"
FIMP_INTERFACE_EVT_SETPOINT_REPORT = "evt.setpoint.report"
FIMP_INTERFACE_CMD_STATE_GET_REPORT = "cmd.state.get_report"
FIMP_INTERFACE_EVT_STATE_REPORT = "evt.state.report"

# FIMP Value types
FIMP_VAL_TYPE_BOOL = "bool"
FIMP_VAL_TYPE_INT = "int"
FIMP_VAL_TYPE_FLOAT = "float"
FIMP_VAL_TYPE_STRING = "string"
FIMP_VAL_TYPE_STR_ARRAY = "str_array"
FIMP_VAL_TYPE_INT_ARRAY = "int_array"
FIMP_VAL_TYPE_FLOAT_ARRAY = "float_array"
FIMP_VAL_TYPE_STR_MAP = "str_map"
FIMP_VAL_TYPE_INT_MAP = "int_map"
FIMP_VAL_TYPE_FLOAT_MAP = "float_map"
FIMP_VAL_TYPE_OBJECT = "object"
FIMP_VAL_TYPE_NULL = "null"

# Error messages
ERROR_CANNOT_CONNECT = "cannot_connect"
ERROR_INVALID_AUTH = "invalid_auth"
ERROR_UNKNOWN = "unknown"

# Entry data keys
ENTRY_DATA_CLIENT = "client"
ENTRY_DATA_HUB_INFO = "hub_info"
ENTRY_DATA_DEVICES = "devices"
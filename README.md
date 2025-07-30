# Futurehome FIMP Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/NickKibish/HomeAssistant-Futurehome-FIMP?style=for-the-badge)

A Home Assistant integration for Futurehome hubs using the FIMP (Futurehome IoT Messaging Protocol) over MQTT.

## Features

- 🏠 **Complete Device Support**: Thermostats, sensors, switches, and smart relays
- ⚡ **Real-time Updates**: Push-based communication via MQTT
- 🔌 **Smart Relay Control**: Binary switches with power consumption monitoring
- 📊 **Power Monitoring**: Current, voltage, power consumption, and energy usage
- 🌡️ **Climate Control**: Temperature sensors and thermostat control
- 🔄 **Automatic Discovery**: Devices are automatically discovered and configured
- ⚙️ **Easy Setup**: Configuration via Home Assistant UI

## Supported Devices

### Thermostats
- Temperature control and monitoring
- Mode switching (heating, cooling, auto)
- Setpoint adjustment

### Sensors
- Temperature sensors
- Humidity sensors (when available)
- Power consumption monitoring

### Smart Relays/Switches
- Binary switch control (on/off)
- Real-time power consumption (Watts)
- Energy consumption tracking (kWh)
- Voltage and current monitoring
- Unified device representation

## Requirements

- Home Assistant 2023.1 or later
- Futurehome hub with MQTT access
- Zigbee devices connected to the Futurehome hub

## Installation

### HACS (Recommended)

1. Add this repository to HACS as a custom repository
2. Install "Futurehome FIMP" from HACS
3. Restart Home Assistant
4. Add the integration through the UI

### Manual Installation

1. Copy the `custom_components/futurehome_fimp` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Add the integration through the UI

## Configuration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "Futurehome FIMP"
3. Enter your Futurehome hub details:
   - **Hub IP Address**: The IP address of your Futurehome hub
   - **MQTT Port**: Usually 1883 (default)
   - **MQTT Username**: Your MQTT username
   - **MQTT Password**: Your MQTT password

## Entities Created

For each discovered thermostat device, the integration creates:

### Climate Entity
- **Thermostat**: Full climate control with temperature setpoints and HVAC modes
- Supports: Heat, Cool, Auto, Off modes
- Preset modes: Home, Away, Sleep (if supported by device)

### Sensor Entities
- **Temperature**: Current room temperature
- **Power**: Real-time power consumption (W)
- **Energy**: Total energy consumption (kWh)
- **Voltage**: Line voltage (V)
- **Current**: Electrical current (A)

## FIMP Protocol

This integration implements the Futurehome IoT Messaging Protocol (FIMP) for device communication:

- **Service Types**: `thermostat`, `sensor_temp`, `meter_elec`
- **Transport**: MQTT over standard Futurehome topics
- **Message Format**: JSON-based FIMP messages
- **Discovery**: Automatic Zigbee device discovery via adapter queries

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

# HomeAssistant-Futurehome-FIMP

Home Assistant custom integration for Futurehome FIMP protocol - enables control of Zigbee thermostats and sensors through the Futurehome hub.

## Overview

This integration allows Home Assistant to communicate with Futurehome devices using the FIMP (Futurehome IoT Messaging Protocol) over MQTT. It provides seamless integration for Zigbee thermostats, temperature sensors, and energy meters connected to your Futurehome hub.

## Features

- **Thermostat Control**: Full climate control with temperature setpoints, HVAC modes, and preset modes
- **Temperature Sensors**: Real-time temperature monitoring from connected sensors
- **Energy Monitoring**: Power consumption, energy usage, voltage, and current monitoring
- **Automatic Discovery**: Discovers all compatible Zigbee devices automatically
- **Real-time Updates**: Push-based updates for instant state changes

## Supported Devices

- Zigbee thermostats with FIMP thermostat service
- Temperature sensors (sensor_temp service)
- Electric meters (meter_elec service) for power and energy monitoring

## Requirements

- Home Assistant 2023.1 or later
- Futurehome hub with MQTT access
- Zigbee devices connected to the Futurehome hub
- Python package: `paho-mqtt`

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

## Troubleshooting

### Connection Issues
- Verify hub IP address and MQTT credentials
- Check that MQTT service is running on the hub
- Ensure Home Assistant can reach the hub network

### Device Discovery
- Wait 30-60 seconds after adding integration for device discovery
- Check Home Assistant logs for FIMP messages
- Verify devices are properly paired with Futurehome hub

### Entity States
- Entities may show "Unknown" initially until first data is received
- Check MQTT traffic for proper FIMP message flow
- Restart integration if entities remain unavailable

## Development

This integration includes a complete development environment:

```bash
cd ha/
docker-compose up -d
```

Access the development Home Assistant instance at http://localhost:8123

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

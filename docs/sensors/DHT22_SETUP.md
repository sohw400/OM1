# DHT22 Temperature and Humidity Sensor Setup

This guide covers how to integrate a DHT22 sensor with OM1 for environmental monitoring.

## Overview

The DHT22 is a digital temperature and humidity sensor that provides reliable readings with good accuracy. This plugin allows OM1 agents to react to environmental conditions in real-time.

## Hardware Requirements

- DHT22 (AM2302) sensor
- Raspberry Pi or compatible board with GPIO
- 10kΩ pull-up resistor (some modules include this)
- Jumper wires

## Wiring

Connect the DHT22 to your board:

- VCC (Pin 1) → 3.3V or 5V
- DATA (Pin 2) → GPIO pin (default: GPIO 4)
- NC (Pin 3) → Not connected
- GND (Pin 4) → Ground

If your sensor doesn't have a built-in pull-up resistor, add a 10kΩ resistor between VCC and DATA.

## Software Installation

Install the required library:

```bash
pip install adafruit-circuitpython-dht
```

For Raspberry Pi, you may also need:

```bash
sudo apt-get install libgpiod2
```

## Configuration

### Basic Setup

Add the DHT22 sensor to your agent configuration:

```json
{
  "agent_inputs": [
    {
      "type": "DHT22Sensor",
      "config": {
        "pin": 4,
        "mock_mode": false
      }
    }
  ]
}
```

### Configuration Options

- `pin`: GPIO pin number where the sensor is connected (default: 4)
- `mock_mode`: Set to `true` for testing without hardware (default: false)

### Supported GPIO Pins

The following GPIO pins are supported:
- GPIO 4 (default)
- GPIO 17
- GPIO 18
- GPIO 22
- GPIO 23
- GPIO 24
- GPIO 25
- GPIO 27

## Testing Without Hardware

For development and testing, you can use mock mode:

```json
{
  "type": "DHT22Sensor",
  "config": {
    "mock_mode": true
  }
}
```

This generates simulated temperature (20-24°C) and humidity (50-60%) readings.

## Running the Agent

Use the provided example configuration:

```bash
uv run src/run.py dht22_environment
```

The agent will monitor temperature and humidity, providing natural language descriptions of the current conditions.

## Sensor Output

The sensor provides readings every 2 seconds containing:

- Temperature in Celsius and Fahrenheit
- Relative humidity percentage
- Comfort level interpretation

Example output:
```
Current temperature is 22.3°C (72.1°F), which feels comfortable.
Humidity is at 55.2%.
```

## Troubleshooting

**Sensor returns None values:**
- Check wiring connections
- Verify the correct GPIO pin is specified
- Ensure the pull-up resistor is present
- Try a different GPIO pin

**Import errors:**
- Verify `adafruit-circuitpython-dht` is installed
- On Raspberry Pi, ensure `libgpiod2` is installed
- The system will automatically fall back to mock mode if libraries are missing

**Read failures:**
- DHT22 sensors occasionally fail reads due to timing issues - this is normal
- The provider automatically retries on the next cycle
- Ensure readings aren't requested more than once every 2 seconds

## Integration Examples

### Climate Control Agent

```json
{
  "system_prompt_base": "Monitor the environment and suggest climate adjustments when needed. If temperature drops below 18°C, recommend heating. If humidity exceeds 70%, suggest ventilation."
}
```

### Greenhouse Monitor

```json
{
  "system_prompt_base": "You are monitoring a greenhouse. Ideal conditions are 20-25°C and 60-70% humidity. Alert when conditions drift outside this range."
}
```

## Technical Notes

- DHT22 has a measurement range of -40 to 80°C with ±0.5°C accuracy
- Humidity range is 0-100% with ±2-5% accuracy
- Minimum 2-second interval between readings per datasheet
- The sensor operates on 3.3V or 5V power

## License

This integration is part of the OM1 project and is available under the MIT License.

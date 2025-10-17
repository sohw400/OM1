# BH1750 Ambient Light Sensor Setup

This guide explains how to integrate the BH1750 digital light sensor with OM1.

## Overview

The BH1750 is a popular I2C light sensor that measures illuminance in lux units. It's commonly used in applications like automatic brightness control, photography light meters, and environmental monitoring. This integration allows OM1 agents to perceive and respond to lighting conditions.

## Hardware Requirements

- BH1750 light sensor module (GY-302 or similar)
- Raspberry Pi or compatible board with I2C support
- Jumper wires for connections

Most BH1750 modules include necessary pull-up resistors and voltage regulation, making them easy to use.

## Wiring

Connect the BH1750 to your board using I2C:

- VCC → 3.3V or 5V (check your module's specifications)
- GND → Ground
- SCL → I2C Clock (GPIO 3 on Raspberry Pi)
- SDA → I2C Data (GPIO 2 on Raspberry Pi)
- ADDR → GND (for address 0x23) or VCC (for address 0x5C)

## Enable I2C

On Raspberry Pi, enable I2C if it's not already active:

```bash
sudo raspi-config
```

Navigate to: Interface Options → I2C → Enable

Reboot after enabling:

```bash
sudo reboot
```

Verify the sensor is detected:

```bash
sudo i2cdetect -y 1
```

You should see `23` (or `5c` if ADDR is connected to VCC) in the output grid.

## Software Installation

Install the required I2C library:

```bash
pip install smbus2
```

## Configuration

### Basic Setup

Add the BH1750 sensor to your agent configuration:

```json
{
  "agent_inputs": [
    {
      "type": "BH1750Light",
      "config": {
        "address": 35,
        "bus": 1,
        "mock_mode": false
      }
    }
  ]
}
```

### Configuration Parameters

- `address`: I2C address in decimal (35 for 0x23, 92 for 0x5C)
- `bus`: I2C bus number (usually 1 on Raspberry Pi)
- `mock_mode`: Set to `true` for testing without hardware

### Common I2C Addresses

- **0x23 (35)**: Default when ADDR pin is connected to GND
- **0x5C (92)**: When ADDR pin is connected to VCC

## Mock Mode for Testing

Test your setup without hardware by enabling mock mode:

```json
{
  "type": "BH1750Light",
  "config": {
    "mock_mode": true
  }
}
```

This generates simulated light readings around 250 lux with realistic variations.

## Running the Agent

Use the provided configuration:

```bash
uv run src/run.py bh1750_lighting
```

The agent will monitor light levels and provide contextual descriptions.

## Understanding Light Levels

The sensor reports illuminance in lux:

- **< 10 lux**: Dark (nighttime, closet)
- **10-100 lux**: Dim (twilight, hallway)
- **100-500 lux**: Moderate (living room, office)
- **500-1000 lux**: Bright (well-lit office, overcast day)
- **> 1000 lux**: Very bright (direct sunlight)

## Example Output

```
The ambient light level is 320 lux. The lighting is comfortable for most
activities, typical of well-lit indoor spaces.
```

## Troubleshooting

**Sensor not detected by i2cdetect:**
- Check wiring connections
- Verify I2C is enabled in system configuration
- Try the alternate I2C address
- Ensure the sensor has power

**Import errors for smbus2:**
- Install the library: `pip install smbus2`
- The system automatically falls back to mock mode if unavailable

**Inconsistent readings:**
- BH1750 sensors can be sensitive to viewing angle
- Ensure the sensor window is not obstructed
- Allow a few seconds for readings to stabilize

**Permission errors:**
- Add your user to the i2c group: `sudo usermod -a -G i2c $USER`
- Log out and back in for changes to take effect

## Use Cases

### Automatic Screen Brightness

```json
{
  "system_prompt_base": "Monitor ambient light and suggest screen brightness adjustments. If it's bright, recommend increasing brightness. In dark conditions, suggest lowering it to reduce eye strain."
}
```

### Photography Assistant

```json
{
  "system_prompt_base": "You're helping with photography. Report lighting conditions and suggest whether additional lighting is needed or if natural light is sufficient."
}
```

### Energy Efficiency

```json
{
  "system_prompt_base": "Monitor room lighting and recommend turning off artificial lights when natural light is sufficient. Help save energy while maintaining comfortable conditions."
}
```

## Technical Specifications

- Measurement range: 1 to 65535 lux
- Accuracy: ±20% typical
- Response time: 120-180ms
- Operating voltage: 2.4V to 3.6V (most modules handle 5V)
- Interface: I2C with 7-bit addressing
- Power consumption: ~0.12mA typical

## Advanced Configuration

### Using Multiple Sensors

If you need multiple light sensors, connect them with different addresses:

```json
{
  "agent_inputs": [
    {
      "type": "BH1750Light",
      "config": {
        "address": 35,
        "bus": 1
      }
    },
    {
      "type": "BH1750Light",
      "config": {
        "address": 92,
        "bus": 1
      }
    }
  ]
}
```

### Integration with Other Sensors

Combine with temperature sensors for complete environmental monitoring:

```json
{
  "agent_inputs": [
    {
      "type": "BH1750Light"
    },
    {
      "type": "DHT22Sensor"
    }
  ]
}
```

## License

This integration is part of the OM1 project and is released under the MIT License.

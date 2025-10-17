from unittest.mock import Mock, patch

import pytest

from inputs.base import SensorConfig
from inputs.plugins.dht22_sensor import DHT22Sensor, Message


@pytest.fixture
def mock_dht22_provider():
    with patch("inputs.plugins.dht22_sensor.DHT22Provider") as mock:
        mock_instance = Mock()
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def dht22_input(mock_dht22_provider):
    return DHT22Sensor(config=SensorConfig(pin=4, mock_mode=True))


def test_init(dht22_input, mock_dht22_provider):
    """Test DHT22 sensor initializes correctly."""
    assert dht22_input.messages == []
    assert dht22_input.descriptor_for_LLM == "Environment Sensor"


def test_init_with_custom_config():
    """Test initialization with custom configuration."""
    with patch("inputs.plugins.dht22_sensor.DHT22Provider") as mock:
        sensor = DHT22Sensor(config=SensorConfig(pin=17, mock_mode=True))
        mock.assert_called_once_with(pin=17, mock_mode=True)


@pytest.mark.asyncio
async def test_poll_with_data(dht22_input, mock_dht22_provider):
    """Test polling returns sensor data when available."""
    test_data = {
        "temperature_celsius": 22.5,
        "temperature_fahrenheit": 72.5,
        "humidity_percent": 55.0,
        "timestamp": 123456.0,
    }
    mock_dht22_provider.data = test_data
    result = await dht22_input._poll()
    assert result == test_data


@pytest.mark.asyncio
async def test_poll_no_data(dht22_input, mock_dht22_provider):
    """Test polling returns None when no data available."""
    mock_dht22_provider.data = None
    result = await dht22_input._poll()
    assert result is None


@pytest.mark.asyncio
async def test_raw_to_text_comfortable_conditions(dht22_input):
    """Test text conversion for comfortable environmental conditions."""
    raw_data = {
        "temperature_celsius": 22.0,
        "temperature_fahrenheit": 71.6,
        "humidity_percent": 50.0,
        "timestamp": 123456.0,
    }
    result = await dht22_input._raw_to_text(raw_data)
    assert result is not None
    assert "22.0°C" in result.message
    assert "71.6°F" in result.message
    assert "50.0%" in result.message
    assert "comfortable" in result.message


@pytest.mark.asyncio
async def test_raw_to_text_cold_conditions(dht22_input):
    """Test text conversion for cold conditions."""
    raw_data = {
        "temperature_celsius": 15.0,
        "temperature_fahrenheit": 59.0,
        "humidity_percent": 40.0,
        "timestamp": 123456.0,
    }
    result = await dht22_input._raw_to_text(raw_data)
    assert result is not None
    assert "cool" in result.message


@pytest.mark.asyncio
async def test_raw_to_text_warm_conditions(dht22_input):
    """Test text conversion for warm conditions."""
    raw_data = {
        "temperature_celsius": 28.0,
        "temperature_fahrenheit": 82.4,
        "humidity_percent": 75.0,
        "timestamp": 123456.0,
    }
    result = await dht22_input._raw_to_text(raw_data)
    assert result is not None
    assert "warm" in result.message
    assert "humid" in result.message


@pytest.mark.asyncio
async def test_raw_to_text_dry_air(dht22_input):
    """Test text conversion for dry air conditions."""
    raw_data = {
        "temperature_celsius": 22.0,
        "temperature_fahrenheit": 71.6,
        "humidity_percent": 25.0,
        "timestamp": 123456.0,
    }
    result = await dht22_input._raw_to_text(raw_data)
    assert result is not None
    assert "dry" in result.message


@pytest.mark.asyncio
async def test_raw_to_text_none_input(dht22_input):
    """Test text conversion handles None input gracefully."""
    result = await dht22_input._raw_to_text(None)
    assert result is None


@pytest.mark.asyncio
async def test_raw_to_text_missing_keys(dht22_input):
    """Test text conversion handles missing data keys."""
    incomplete_data = {"temperature_celsius": 22.0}
    result = await dht22_input._raw_to_text(incomplete_data)
    assert result is None


@pytest.mark.asyncio
async def test_raw_to_text_buffer_management(dht22_input):
    """Test message buffer management."""
    raw_data = {
        "temperature_celsius": 22.0,
        "temperature_fahrenheit": 71.6,
        "humidity_percent": 50.0,
        "timestamp": 123456.0,
    }
    await dht22_input.raw_to_text(raw_data)
    assert len(dht22_input.messages) == 1
    assert dht22_input.messages[0].message


@pytest.mark.asyncio
async def test_raw_to_text_ignores_none(dht22_input):
    """Test that None input doesn't add to message buffer."""
    await dht22_input.raw_to_text(None)
    assert len(dht22_input.messages) == 0


def test_formatted_latest_buffer(dht22_input):
    """Test formatted output includes all necessary information."""
    test_message = Message(
        message="Current temperature is 22.0°C, humidity is 50.0%.", timestamp=123.456
    )
    dht22_input.messages = [test_message]
    result = dht22_input.formatted_latest_buffer()
    assert result is not None
    assert "Environment Sensor" in result
    assert "22.0°C" in result
    assert "50.0%" in result
    assert dht22_input.messages == []


def test_formatted_latest_buffer_empty(dht22_input):
    """Test formatted output returns None when buffer is empty."""
    assert dht22_input.formatted_latest_buffer() is None


def test_formatted_latest_buffer_clears_messages(dht22_input):
    """Test that formatted_latest_buffer clears the message list."""
    dht22_input.messages = [
        Message(message="test message 1", timestamp=123.0),
        Message(message="test message 2", timestamp=124.0),
    ]
    result = dht22_input.formatted_latest_buffer()
    assert result is not None
    assert dht22_input.messages == []

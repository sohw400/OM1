from unittest.mock import Mock, patch

import pytest

from providers.dht22_provider import DHT22Provider


@pytest.fixture
def mock_sensor_hardware():
    """Mock the Adafruit DHT library."""
    with patch("providers.dht22_provider.adafruit_dht") as mock_dht:
        with patch("providers.dht22_provider.board") as mock_board:
            mock_board.D4 = "GPIO4"
            mock_sensor = Mock()
            mock_dht.DHT22.return_value = mock_sensor
            yield mock_sensor


def test_init_mock_mode():
    """Test initialization in mock mode."""
    provider = DHT22Provider(pin=4, mock_mode=True)
    assert provider.mock_mode is True
    assert provider.running is True
    provider.stop()


def test_init_hardware_mode_no_library():
    """Test initialization falls back to mock when library unavailable."""
    with patch(
        "providers.dht22_provider.adafruit_dht", side_effect=ImportError("No module")
    ):
        provider = DHT22Provider(pin=4, mock_mode=False)
        assert provider.mock_mode is True
        provider.stop()


def test_mock_mode_generates_data():
    """Test that mock mode generates reasonable sensor data."""
    provider = DHT22Provider(pin=4, mock_mode=True)
    import time

    time.sleep(0.5)  # Allow initial read

    data = provider.data
    assert data is not None
    assert "temperature_celsius" in data
    assert "temperature_fahrenheit" in data
    assert "humidity_percent" in data
    assert "timestamp" in data

    # Check values are within reasonable ranges
    assert 15.0 <= data["temperature_celsius"] <= 30.0
    assert 40.0 <= data["humidity_percent"] <= 70.0

    provider.stop()


def test_temperature_conversion():
    """Test Celsius to Fahrenheit conversion."""
    provider = DHT22Provider(pin=4, mock_mode=True)
    import time

    time.sleep(0.5)

    data = provider.data
    temp_c = data["temperature_celsius"]
    temp_f = data["temperature_fahrenheit"]

    # Verify conversion formula
    expected_f = temp_c * 9 / 5 + 32
    assert abs(temp_f - expected_f) < 0.1

    provider.stop()


def test_data_structure():
    """Test that data dictionary has correct structure."""
    provider = DHT22Provider(pin=4, mock_mode=True)
    import time

    time.sleep(0.5)

    data = provider.data
    assert isinstance(data, dict)
    assert all(
        key in data
        for key in [
            "temperature_celsius",
            "temperature_fahrenheit",
            "humidity_percent",
            "timestamp",
        ]
    )

    provider.stop()


def test_provider_stops_cleanly():
    """Test that provider can be stopped without errors."""
    provider = DHT22Provider(pin=4, mock_mode=True)
    assert provider.running is True
    provider.stop()
    assert provider.running is False


def test_multiple_reads():
    """Test that provider can handle multiple reads."""
    provider = DHT22Provider(pin=4, mock_mode=True)
    import time

    time.sleep(0.5)
    data1 = provider.data

    time.sleep(2.5)  # DHT22 reads every 2 seconds
    data2 = provider.data

    assert data1 is not None
    assert data2 is not None
    assert data1["timestamp"] < data2["timestamp"]

    provider.stop()


def test_pin_configuration():
    """Test that different pins can be configured."""
    provider = DHT22Provider(pin=17, mock_mode=True)
    assert provider.pin == 17
    provider.stop()

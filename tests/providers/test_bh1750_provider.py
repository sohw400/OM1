from unittest.mock import Mock, patch

import pytest

from providers.bh1750_provider import BH1750Provider


@pytest.fixture
def mock_smbus():
    """Mock the smbus2 library."""
    with patch("providers.bh1750_provider.smbus2") as mock_lib:
        mock_bus = Mock()
        mock_lib.SMBus.return_value = mock_bus
        yield mock_bus


def test_init_mock_mode():
    """Test initialization in mock mode."""
    provider = BH1750Provider(address=0x23, bus=1, mock_mode=True)
    assert provider.mock_mode is True
    assert provider.running is True
    assert provider.address == 0x23
    assert provider.bus == 1
    provider.stop()


def test_init_hardware_mode_no_library():
    """Test initialization falls back to mock when library unavailable."""
    with patch("providers.bh1750_provider.smbus2", side_effect=ImportError("No module")):
        provider = BH1750Provider(address=0x23, bus=1, mock_mode=False)
        assert provider.mock_mode is True
        provider.stop()


def test_mock_mode_generates_data():
    """Test that mock mode generates reasonable sensor data."""
    provider = BH1750Provider(address=0x23, bus=1, mock_mode=True)
    import time

    time.sleep(0.5)  # Allow initial read

    data = provider.data
    assert data is not None
    assert "lux" in data
    assert "condition" in data
    assert "timestamp" in data

    # Check values are within reasonable ranges for indoor lighting
    assert 150.0 <= data["lux"] <= 400.0

    provider.stop()


def test_condition_mapping():
    """Test that lux values map to correct conditions."""
    provider = BH1750Provider(address=0x23, bus=1, mock_mode=True)
    import time

    time.sleep(0.5)

    # Test dark condition
    provider.lux = 5.0
    provider._update_data()
    assert provider.data["condition"] == "dark"

    # Test dim condition
    provider.lux = 50.0
    provider._update_data()
    assert provider.data["condition"] == "dim"

    # Test moderate condition
    provider.lux = 300.0
    provider._update_data()
    assert provider.data["condition"] == "moderate"

    # Test bright condition
    provider.lux = 750.0
    provider._update_data()
    assert provider.data["condition"] == "bright"

    # Test very bright condition
    provider.lux = 1500.0
    provider._update_data()
    assert provider.data["condition"] == "very bright"

    provider.stop()


def test_data_structure():
    """Test that data dictionary has correct structure."""
    provider = BH1750Provider(address=0x23, bus=1, mock_mode=True)
    import time

    time.sleep(0.5)

    data = provider.data
    assert isinstance(data, dict)
    assert all(key in data for key in ["lux", "condition", "timestamp"])
    assert isinstance(data["lux"], float)
    assert isinstance(data["condition"], str)
    assert isinstance(data["timestamp"], float)

    provider.stop()


def test_provider_stops_cleanly():
    """Test that provider can be stopped without errors."""
    provider = BH1750Provider(address=0x23, bus=1, mock_mode=True)
    assert provider.running is True
    provider.stop()
    assert provider.running is False


def test_multiple_reads():
    """Test that provider can handle multiple reads."""
    provider = BH1750Provider(address=0x23, bus=1, mock_mode=True)
    import time

    time.sleep(0.5)
    data1 = provider.data

    time.sleep(1.5)  # BH1750 reads every 1 second
    data2 = provider.data

    assert data1 is not None
    assert data2 is not None
    assert data1["timestamp"] < data2["timestamp"]

    provider.stop()


def test_address_configuration():
    """Test that different I2C addresses can be configured."""
    provider_default = BH1750Provider(address=0x23, bus=1, mock_mode=True)
    assert provider_default.address == 0x23
    provider_default.stop()

    provider_alt = BH1750Provider(address=0x5C, bus=1, mock_mode=True)
    assert provider_alt.address == 0x5C
    provider_alt.stop()


def test_bus_configuration():
    """Test that different I2C buses can be configured."""
    provider = BH1750Provider(address=0x23, bus=0, mock_mode=True)
    assert provider.bus == 0
    provider.stop()


def test_mock_mode_variation():
    """Test that mock mode generates varied readings."""
    provider = BH1750Provider(address=0x23, bus=1, mock_mode=True)
    import time

    time.sleep(0.5)
    readings = []
    for _ in range(5):
        data = provider.data
        if data:
            readings.append(data["lux"])
        time.sleep(1.2)

    # Check that we got varied readings (not all identical)
    assert len(set(readings)) > 1

    provider.stop()


def test_lux_value_non_negative():
    """Test that lux values are never negative."""
    provider = BH1750Provider(address=0x23, bus=1, mock_mode=True)
    import time

    time.sleep(0.5)
    for _ in range(10):
        data = provider.data
        if data:
            assert data["lux"] >= 0
        time.sleep(0.2)

    provider.stop()

from unittest.mock import Mock, patch

import pytest

from inputs.base import SensorConfig
from inputs.plugins.bh1750_light import BH1750Light, Message


@pytest.fixture
def mock_bh1750_provider():
    with patch("inputs.plugins.bh1750_light.BH1750Provider") as mock:
        mock_instance = Mock()
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def bh1750_input(mock_bh1750_provider):
    return BH1750Light(config=SensorConfig(address=0x23, bus=1, mock_mode=True))


def test_init(bh1750_input, mock_bh1750_provider):
    """Test BH1750 sensor initializes correctly."""
    assert bh1750_input.messages == []
    assert bh1750_input.descriptor_for_LLM == "Ambient Light"


def test_init_with_custom_config():
    """Test initialization with custom configuration."""
    with patch("inputs.plugins.bh1750_light.BH1750Provider") as mock:
        sensor = BH1750Light(
            config=SensorConfig(address=0x5C, bus=0, mock_mode=False)
        )
        mock.assert_called_once_with(address=0x5C, bus=0, mock_mode=False)


@pytest.mark.asyncio
async def test_poll_with_data(bh1750_input, mock_bh1750_provider):
    """Test polling returns sensor data when available."""
    test_data = {"lux": 320.0, "condition": "moderate", "timestamp": 123456.0}
    mock_bh1750_provider.data = test_data
    result = await bh1750_input._poll()
    assert result == test_data


@pytest.mark.asyncio
async def test_poll_no_data(bh1750_input, mock_bh1750_provider):
    """Test polling returns None when no data available."""
    mock_bh1750_provider.data = None
    result = await bh1750_input._poll()
    assert result is None


@pytest.mark.asyncio
async def test_raw_to_text_dark_condition(bh1750_input):
    """Test text conversion for dark conditions."""
    raw_data = {"lux": 5.0, "condition": "dark", "timestamp": 123456.0}
    result = await bh1750_input._raw_to_text(raw_data)
    assert result is not None
    assert "5 lux" in result.message
    assert "dark" in result.message.lower()
    assert "limited" in result.message.lower()


@pytest.mark.asyncio
async def test_raw_to_text_dim_condition(bh1750_input):
    """Test text conversion for dim lighting."""
    raw_data = {"lux": 75.0, "condition": "dim", "timestamp": 123456.0}
    result = await bh1750_input._raw_to_text(raw_data)
    assert result is not None
    assert "75 lux" in result.message
    assert "dim" in result.message.lower()


@pytest.mark.asyncio
async def test_raw_to_text_moderate_condition(bh1750_input):
    """Test text conversion for moderate lighting."""
    raw_data = {"lux": 320.0, "condition": "moderate", "timestamp": 123456.0}
    result = await bh1750_input._raw_to_text(raw_data)
    assert result is not None
    assert "320 lux" in result.message
    assert "comfortable" in result.message.lower()
    assert "indoor" in result.message.lower()


@pytest.mark.asyncio
async def test_raw_to_text_bright_condition(bh1750_input):
    """Test text conversion for bright conditions."""
    raw_data = {"lux": 750.0, "condition": "bright", "timestamp": 123456.0}
    result = await bh1750_input._raw_to_text(raw_data)
    assert result is not None
    assert "750 lux" in result.message
    assert "bright" in result.message.lower()


@pytest.mark.asyncio
async def test_raw_to_text_very_bright_condition(bh1750_input):
    """Test text conversion for very bright conditions."""
    raw_data = {"lux": 1500.0, "condition": "very bright", "timestamp": 123456.0}
    result = await bh1750_input._raw_to_text(raw_data)
    assert result is not None
    assert "1500 lux" in result.message
    assert "very bright" in result.message.lower() or "sunlight" in result.message.lower()


@pytest.mark.asyncio
async def test_raw_to_text_none_input(bh1750_input):
    """Test text conversion handles None input gracefully."""
    result = await bh1750_input._raw_to_text(None)
    assert result is None


@pytest.mark.asyncio
async def test_raw_to_text_missing_keys(bh1750_input):
    """Test text conversion handles missing data keys."""
    incomplete_data = {"lux": 250.0}
    result = await bh1750_input._raw_to_text(incomplete_data)
    assert result is None


@pytest.mark.asyncio
async def test_raw_to_text_buffer_management(bh1750_input):
    """Test message buffer management."""
    raw_data = {"lux": 320.0, "condition": "moderate", "timestamp": 123456.0}
    await bh1750_input.raw_to_text(raw_data)
    assert len(bh1750_input.messages) == 1
    assert bh1750_input.messages[0].message


@pytest.mark.asyncio
async def test_raw_to_text_ignores_none(bh1750_input):
    """Test that None input doesn't add to message buffer."""
    await bh1750_input.raw_to_text(None)
    assert len(bh1750_input.messages) == 0


def test_formatted_latest_buffer(bh1750_input):
    """Test formatted output includes all necessary information."""
    test_message = Message(
        message="The ambient light level is 320 lux. The lighting is comfortable.",
        timestamp=123.456,
    )
    bh1750_input.messages = [test_message]
    result = bh1750_input.formatted_latest_buffer()
    assert result is not None
    assert "Ambient Light" in result
    assert "320 lux" in result
    assert "comfortable" in result
    assert bh1750_input.messages == []


def test_formatted_latest_buffer_empty(bh1750_input):
    """Test formatted output returns None when buffer is empty."""
    assert bh1750_input.formatted_latest_buffer() is None


def test_formatted_latest_buffer_clears_messages(bh1750_input):
    """Test that formatted_latest_buffer clears the message list."""
    bh1750_input.messages = [
        Message(message="test message 1", timestamp=123.0),
        Message(message="test message 2", timestamp=124.0),
    ]
    result = bh1750_input.formatted_latest_buffer()
    assert result is not None
    assert bh1750_input.messages == []


def test_lux_value_formatting(bh1750_input):
    """Test that lux values are formatted without decimals."""
    import asyncio

    raw_data = {"lux": 320.7, "condition": "moderate", "timestamp": 123456.0}
    result = asyncio.run(bh1750_input._raw_to_text(raw_data))
    assert "321 lux" in result.message or "320 lux" in result.message

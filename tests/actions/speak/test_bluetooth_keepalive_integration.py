import sys
from unittest.mock import MagicMock, patch

from actions.base import ActionConfig

# Mock external dependencies
sys.modules["om1_speech"] = MagicMock()
sys.modules["om1_utils"] = MagicMock()
sys.modules["om1_utils.ws"] = MagicMock()


def test_connectors_have_bluetooth_keepalive():
    """Test that connectors integrate with Bluetooth keep-alive provider."""
    with (
        patch("providers.asr_provider.ASRProvider"),
        patch("providers.riva_tts_provider.RivaTTSProvider") as mock_riva_tts,
        patch(
            "providers.elevenlabs_tts_provider.ElevenLabsTTSProvider"
        ) as mock_eleven_tts,
    ):

        mock_riva_instance = MagicMock()
        mock_riva_tts.return_value = mock_riva_instance

        mock_eleven_instance = MagicMock()
        mock_eleven_tts.return_value = mock_eleven_instance

        from actions.speak.connector.elevenlabs_tts import SpeakElevenLabsTTSConnector
        from actions.speak.connector.riva_tts import SpeakRivaTTSConnector

        # Test Riva connector
        riva_config = ActionConfig()
        riva_config.api_key = "test_key"

        riva_connector = SpeakRivaTTSConnector(riva_config)
        assert hasattr(riva_connector, "bluetooth_keepalive")
        assert riva_connector.bluetooth_keepalive.enabled

        # Test ElevenLabs connector
        eleven_config = ActionConfig()
        eleven_config.api_key = "test_key"
        eleven_config.elevenlabs_api_key = "test_eleven_key"

        eleven_connector = SpeakElevenLabsTTSConnector(eleven_config)
        assert hasattr(eleven_connector, "bluetooth_keepalive")
        assert eleven_connector.bluetooth_keepalive.enabled


def test_audio_padding_functionality():
    """Test audio padding functionality."""
    from providers.bluetooth_keepalive_provider import BluetoothKeepAliveProvider

    provider = BluetoothKeepAliveProvider(padding_duration=0.2, enabled=True)

    original_text = "Hello world"
    padded_text = provider.add_audio_padding(original_text)

    assert "." in padded_text
    assert original_text in padded_text
    assert padded_text != original_text

    # Test disabled padding
    provider.enabled = False
    no_padding = provider.add_audio_padding(original_text)
    assert no_padding == original_text

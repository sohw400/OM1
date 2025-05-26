import threading
import time
import unittest
from unittest.mock import Mock, patch

from providers.bluetooth_keepalive_provider import BluetoothKeepAliveProvider


class TestBluetoothKeepAliveProvider(unittest.TestCase):
    """Test cases for BluetoothKeepAliveProvider."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        # Clear singleton instance for testing
        if hasattr(BluetoothKeepAliveProvider, "_instances"):
            BluetoothKeepAliveProvider._instances.clear()

        self.provider = BluetoothKeepAliveProvider(
            keepalive_interval=1.0,  # Short interval for testing
            padding_duration=0.1,
            enabled=True,
        )

    def tearDown(self):
        """Clean up after each test method."""
        if self.provider:
            self.provider.stop()

    def test_initialization(self):
        """Test provider initialization with default and custom parameters."""
        # Test custom initialization parameters from setUp
        self.assertEqual(self.provider._keepalive_interval, 1.0)
        self.assertEqual(self.provider._padding_duration, 0.1)
        self.assertTrue(self.provider.enabled)

        # Test that singleton returns same instance
        another_provider = BluetoothKeepAliveProvider()
        self.assertIs(self.provider, another_provider)

    def test_singleton_pattern(self):
        """Test that BluetoothKeepAliveProvider follows singleton pattern."""
        provider1 = BluetoothKeepAliveProvider()
        provider2 = BluetoothKeepAliveProvider()
        self.assertIs(provider1, provider2)

    def test_enable_disable(self):
        """Test enabling and disabling the provider."""
        self.assertTrue(self.provider.enabled)

        self.provider.enabled = False
        self.assertFalse(self.provider.enabled)

        self.provider.enabled = True
        self.assertTrue(self.provider.enabled)

    def test_audio_padding(self):
        """Test audio padding functionality."""
        # Test with enabled provider
        text = "Hello world"
        padded = self.provider.add_audio_padding(text)
        self.assertIn(".", padded)
        self.assertIn(text, padded)

        # Test with disabled provider
        self.provider.enabled = False
        no_padding = self.provider.add_audio_padding(text)
        self.assertEqual(no_padding, text)

        # Test with empty text
        self.provider.enabled = True
        empty_result = self.provider.add_audio_padding("")
        self.assertEqual(empty_result, "")

    def test_tts_provider_registration(self):
        """Test TTS provider registration."""
        mock_tts = Mock()

        # Test registration
        self.provider.register_tts_provider(mock_tts)
        self.assertIn(mock_tts, self.provider._tts_providers)

        # Test duplicate registration (should not add twice)
        self.provider.register_tts_provider(mock_tts)
        self.assertEqual(self.provider._tts_providers.count(mock_tts), 1)

    def test_audio_activity_notification(self):
        """Test audio activity notification updates timing."""
        initial_time = self.provider._last_audio_time
        time.sleep(0.1)  # Small delay

        self.provider.notify_audio_activity()
        updated_time = self.provider._last_audio_time

        self.assertGreater(updated_time, initial_time)

    def test_start_stop(self):
        """Test starting and stopping the provider."""
        # Test start
        self.provider.start()
        self.assertTrue(self.provider._running)
        self.assertIsNotNone(self.provider._keepalive_thread)
        self.assertTrue(self.provider._keepalive_thread.is_alive())

        # Test stop
        self.provider.stop()
        self.assertFalse(self.provider._running)

    @patch("time.time")
    def test_keepalive_generation(self, mock_time):
        """Test keep-alive audio generation logic."""
        mock_tts = Mock()
        mock_tts.add_pending_message = Mock()

        self.provider.register_tts_provider(mock_tts)

        # Mock time progression to trigger keep-alive
        mock_time.side_effect = [0, 2.0]  # Simulate 2 seconds passed

        self.provider._generate_keepalive_audio()

        # Verify TTS provider was called
        mock_tts.add_pending_message.assert_called_once()

    def test_keepalive_with_disabled_provider(self):
        """Test that disabled provider doesn't generate keep-alive audio."""
        mock_tts = Mock()
        mock_tts.add_pending_message = Mock()

        self.provider.register_tts_provider(mock_tts)
        self.provider.enabled = False

        self.provider._generate_keepalive_audio()

        # Verify TTS provider was not called when disabled
        mock_tts.add_pending_message.assert_not_called()

    def test_thread_safety(self):
        """Test thread safety of the provider."""

        def toggle_enabled():
            for _ in range(50):
                self.provider.enabled = not self.provider.enabled
                time.sleep(0.001)

        def add_provider():
            mock_tts = Mock()
            for _ in range(50):
                self.provider.register_tts_provider(mock_tts)
                time.sleep(0.001)

        threads = [
            threading.Thread(target=toggle_enabled),
            threading.Thread(target=add_provider),
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()


if __name__ == "__main__":
    unittest.main()

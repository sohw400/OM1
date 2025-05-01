import logging

from actions.base import ActionConfig, ActionConnector
from actions.speak.interface import SpeakInput
from providers.asr_provider import ASRProvider
from providers.elevenlabs_tts_provider import ElevenLabsTTSProvider

try:
    import hid
except ImportError:
    logging.warning(
        "HID library not found. Please install the HIDAPI library to use this plugin."
    )
    hid = None


class SpeakElevenLabsTTSConnector(ActionConnector[SpeakInput]):

    def __init__(self, config: ActionConfig):
        super().__init__(config)

        # Get microphone and speaker device IDs and names
        microphone_device_id = getattr(self.config, "microphone_device_id", None)
        speaker_device_id = getattr(self.config, "speaker_device_id", None)
        microphone_name = getattr(self.config, "microphone_name", None)
        speaker_name = getattr(self.config, "speaker_name", None)

        # OM API key
        api_key = getattr(self.config, "api_key", None)

        # Eleven Labs TTS configuration
        elevenlabs_api_key = getattr(self.config, "elevenlabs_api_key", None)
        voice_id = getattr(self.config, "voice_id", "JBFqnCBsd6RMkjVDRZzb")
        model_id = getattr(self.config, "model_id", "eleven_flash_v2_5")
        output_format = getattr(self.config, "output_format", "mp3_44100_128")

        # Initialize ASR and TTS providers
        self.asr = ASRProvider(
            ws_url="wss://api-asr.openmind.org",
            device_id=microphone_device_id,
            microphone_name=microphone_name,
        )
        self.tts = ElevenLabsTTSProvider(
            url="https://api.openmind.org/api/core/elevenlabs/tts",
            api_key=api_key,
            elevenlabs_api_key=elevenlabs_api_key,
            device_id=speaker_device_id,
            speaker_name=speaker_name,
            voice_id=voice_id,
            model_id=model_id,
            output_format=output_format,
        )
        self.tts.start()

        self.gamepad = None
        if hid is not None:
            for device in hid.enumerate():
                logging.debug(f"device {device['product_string']}")
                if "Xbox Wireless Controller" in device["product_string"]:
                    vendor_id = device["vendor_id"]
                    product_id = device["product_id"]
                    self.gamepad = hid.Device(vendor_id, product_id)
                    logging.info(
                        f"Connected {device['product_string']} {vendor_id} {product_id}"
                    )
                    break

        self.lt_speech_emitter = False
        self.rt_speech_emitter = False
        self.d_pad_speech_emitter = False

    async def connect(self, output_interface: SpeakInput) -> None:
        # Block ASR until TTS is done
        self.tts.register_tts_state_callback(self.asr.audio_stream.on_tts_state_change)
        # Add pending message to TTS
        self.tts.add_pending_message(output_interface.action)

    def tick(self) -> None:
        if self.gamepad:
            data = list(self.gamepad.read(64))

            lt_value = data[9]
            rt_value = data[11]
            d_pad_value = data[13]

            # Check if the left trigger is pressed
            if lt_value > 0 and not self.lt_speech_emitter:
                self.lt_speech_emitter = True
                self.tts.add_pending_message(
                    "Payment confirmed. Proceeding to fulfill the request."
                )

            if rt_value > 0 and not self.rt_speech_emitter:
                self.rt_speech_emitter = True
                self.tts.add_pending_message(
                    "Hi Irwin. One Caesar salad and a muffin, please."
                )

            if d_pad_value > 0 and not self.d_pad_speech_emitter:
                self.d_pad_speech_emitter = True
                self.tts.add_pending_message("Thank you. Have a nice day.")

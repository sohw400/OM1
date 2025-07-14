import asyncio
import json
import logging
import time
from queue import Empty, Queue
from typing import Dict, List, Optional

from inputs.base import SensorConfig
from inputs.base.loop import FuserInput
from providers.xf_asr_provider import XFASRProvider  # Import the XF provider
from providers.io_provider import IOProvider
from providers.sleep_ticker_provider import SleepTickerProvider

LANGUAGE_CODE_MAP: dict = {
    "english": "en-US",
    "chinese": "zh-CN",
    "german": "de-DE",
    "french": "fr-FR",
    "japanese": "ja-JP",
}


class XFASRInput(FuserInput[str]):
    """
    iFlytek Automatic Speech Recognition (ASR) input handler.

    This class manages the input stream from iFlytek ASR service, buffering messages
    and providing text conversion capabilities.
    """

    def __init__(self, config: SensorConfig = SensorConfig()):
        """
        Initialize XFASRInput instance.
        """
        super().__init__(config)

        # Buffer for storing the final output
        self.messages: List[str] = []

        # Set IO Provider
        self.descriptor_for_LLM = "Voice"
        self.io_provider = IOProvider()

        # Buffer for storing messages
        self.message_buffer: Queue[str] = Queue()
        
        # Track last message for punctuation updates
        self._last_message = None

        # Get configuration parameters
        api_key = getattr(self.config, "api_key", None)
        xfyun_app_id = getattr(self.config, "xfyun_app_id", "")
        xfyun_api_key = getattr(self.config, "xfyun_api_key", "")
        rate = getattr(self.config, "rate", 16000)
        chunk = getattr(self.config, "chunk", 1280)
        
        if xfyun_app_id == "":
            logging.error(
                "XFYun App ID not provided."
            )   

        if xfyun_api_key == "":
            logging.error(
                "XFYun API Key not provided."
            )   

        stream_base_url = getattr(
            self.config,
            "stream_base_url",
            f"wss://api.openmind.org/api/core/teleops/stream/audio?api_key={api_key}",
        )
        microphone_device_id = getattr(self.config, "microphone_device_id", None)
        microphone_name = getattr(self.config, "microphone_name", None)
        
        # Language configuration
        language = getattr(self.config, "language", "chinese").strip().lower()
        
        if language not in LANGUAGE_CODE_MAP:
            logging.error(
                f"Language {language} not supported. Current supported languages are : {list(LANGUAGE_CODE_MAP.keys())}. Defaulting to Chinese"
            )
            language = "chinese"
        
        language_code = LANGUAGE_CODE_MAP.get(language, "zh-CN")
        logging.info(f"Using language code {language_code} for iFlytek ASR")
        
        remote_input = getattr(self.config, "remote_input", False)

        # Initialize iFlytek ASR provider
        self.asr: XFASRProvider = XFASRProvider(
            app_id=xfyun_app_id,
            api_key=xfyun_api_key,
            rate=rate,
            chunk=chunk,
            stream_url=stream_base_url if remote_input else None,
            device_id=microphone_device_id,
            microphone_name=microphone_name,
            language_code=language_code,
            remote_input=remote_input,
        )
        
        # Start the provider and register callback
        self.asr.start()
        self.asr.register_message_callback(self._handle_asr_message)

        # Initialize sleep ticker provider
        self.global_sleep_ticker_provider = SleepTickerProvider()

    def _handle_asr_message(self, raw_message: str):
        """
        Process incoming ASR messages from iFlytek.

        Parameters
        ----------
        raw_message : str
            Raw message received from ASR service
        """
        try:
            json_message: Dict = json.loads(raw_message)
            
            # Handle connection status messages
            if json_message.get("type") == "connection":
                logging.info(f"ASR Connection: {json_message.get('message', '')}")
                return
            
            # Handle error messages
            if json_message.get("type") == "error":
                logging.error(f"ASR Error: {json_message.get('message', '')} (Code: {json_message.get('code', 'N/A')})")
                return
            
            # Handle translation results
            if json_message.get("type") == "translation":
                source = json_message.get("source", "")
                translation = json_message.get("translation", "")
                if translation and json_message.get("is_final", False):
                    # You can process translations differently if needed
                    logging.info(f"Translation: {source} -> {translation}")
                return
            
            # Handle transcription results
            if "asr_reply" in json_message:
                asr_reply = json_message["asr_reply"].strip()
                is_final = json_message.get("is_final", True)
                segment_id = json_message.get("segment_id", 0)
                update_previous = json_message.get("update_previous", False)
                
                # Handle updates to previous message (punctuation appending)
                if update_previous and self._last_message:
                    # Update the last message with punctuation
                    self._last_message = asr_reply
                    logging.info(f"Updated previous message with punctuation: {asr_reply}")
                    # Don't add to queue since we're updating the previous
                    return
                
                # Only process final results for the message buffer
                if is_final and len(asr_reply) > 1:  # At least 2 characters
                    self._last_message = asr_reply
                    self.message_buffer.put(asr_reply)
                    logging.info(f"Final ASR message [seg {segment_id}]: {asr_reply}")
                    
                    # Log additional info if available
                    if json_message.get("words"):
                        logging.debug(f"  Word count: {len(json_message['words'])}")
                    if json_message.get("role_id", 0) > 0:
                        logging.info(f"  Speaker: Role {json_message['role_id']}")
                elif not is_final:
                    # Log partial results for debugging
                    logging.debug(f"Partial ASR [seg {segment_id}]: {asr_reply}")
                    
        except json.JSONDecodeError as e:
            logging.error(f"Failed to decode ASR message: {raw_message}, error: {str(e)}")
        except Exception as e:
            logging.error(f"Error handling ASR message: {str(e)}")

    async def _poll(self) -> Optional[str]:
        """
        Poll for new messages in the buffer.

        Returns
        -------
        Optional[str]
            Message from the buffer if available, None otherwise
        """
        await asyncio.sleep(0.1)
        try:
            message = self.message_buffer.get_nowait()
            return message
        except Empty:
            return None

    async def _raw_to_text(self, raw_input: str) -> str:
        """
        Convert raw input to text format.

        Parameters
        ----------
        raw_input : str
            Raw input string to be converted

        Returns
        -------
        Optional[str]
            Converted text or None if conversion fails
        """
        return raw_input

    async def raw_to_text(self, raw_input: str):
        """
        Convert raw input to processed text and manage buffer.

        Parameters
        ----------
        raw_input : Optional[str]
            Raw input to be processed
        """
        pending_message = await self._raw_to_text(raw_input)
        if pending_message is None:
            if len(self.messages) != 0:
                # Skip sleep if there's already a message in the messages buffer
                self.global_sleep_ticker_provider.skip_sleep = True

        if pending_message is not None:
            if len(self.messages) == 0:
                self.messages.append(pending_message)
            else:
                self.messages[-1] = f"{self.messages[-1]} {pending_message}"

    def formatted_latest_buffer(self) -> Optional[str]:
        """
        Format and clear the latest buffer contents.

        Returns
        -------
        Optional[str]
            Formatted string of buffer contents or None if buffer is empty
        """
        if len(self.messages) == 0:
            return None

        result = f"""
INPUT: {self.descriptor_for_LLM}
// START
{self.messages[-1]}
// END
"""
        self.io_provider.add_input(
            self.descriptor_for_LLM, self.messages[-1], time.time()
        )
        self.messages = []
        return result
    
    def stop(self):
        """Stop the ASR provider"""
        if self.asr:
            self.asr.stop()

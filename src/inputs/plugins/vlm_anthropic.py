import asyncio
import logging
import time
from dataclasses import dataclass
from queue import Empty, Queue
from typing import List, Optional

from openai.types.chat import ChatCompletion

from inputs.base import SensorConfig
from inputs.base.loop import FuserInput
from providers.io_provider import IOProvider
from providers.vlm_anthropic_provider import VLMAnthropicProvider


@dataclass
class Message:
    """
    Container for timestamped messages.

    Parameters
    ----------
    timestamp : float
        Unix timestamp of the message
    message : str
        Content of the message
    """

    timestamp: float
    message: str


class VLMAnthropic(FuserInput[str]):
    """
    Vision Language Model input handler for Anthropic Claude.

    A class that processes image inputs and generates text descriptions using
    Anthropic's Claude vision language model. It maintains an internal buffer of
    processed messages and interfaces with the Claude API for image analysis.

    The class handles asynchronous processing of images, maintains message history,
    and provides formatted output of the latest processed messages.
    """

    def __init__(self, config: SensorConfig = SensorConfig()):
        """
        Initialize Anthropic Claude VLM input handler.

        Sets up the required providers and buffers for handling VLM processing.
        Initializes connection to the Claude API and registers message handlers.
        """
        super().__init__(config)

        # Track IO
        self.io_provider = IOProvider()

        # Buffer for storing the final output
        self.messages: List[Message] = []

        # Buffer for storing messages
        self.message_buffer: Queue[str] = Queue()

        # Initialize VLM provider
        api_key = getattr(self.config, "api_key", None)

        if api_key is None or api_key == "":
            raise ValueError("config file missing api_key")

        base_url = getattr(self.config, "base_url", "https://api.anthropic.com")
        model = getattr(self.config, "model", "claude-3-5-sonnet-20241022")
        stream_base_url = getattr(
            self.config,
            "stream_base_url",
            None,
        )
        camera_index = getattr(self.config, "camera_index", 0)

        self.vlm: VLMAnthropicProvider = VLMAnthropicProvider(
            base_url=base_url,
            api_key=api_key,
            model=model,
            stream_url=stream_base_url,
            camera_index=camera_index,
        )
        self.vlm.start()
        self.vlm.register_message_callback(self._handle_vlm_message)

        self.descriptor_for_LLM = "Vision"

    def _handle_vlm_message(self, raw_message: ChatCompletion):
        """
        Process incoming VLM messages from Claude.

        Parses messages from the Claude API and adds valid responses
        to the message buffer for further processing.

        Parameters
        ----------
        raw_message : ChatCompletion
            Response object received from the Claude API
        """
        content = raw_message.choices[0].message.content
        if content is not None:
            logging.info(f"VLM Anthropic Claude received message: {content}")
            self.message_buffer.put(content)
        else:
            logging.warning("VLM Anthropic Claude received message with None content")

    async def _poll(self) -> Optional[str]:
        """
        Poll for new messages from the Claude API.

        Checks the message buffer for new messages with a brief delay
        to prevent excessive CPU usage.

        Returns
        -------
        Optional[str]
            The next message from the buffer if available, None otherwise
        """
        await asyncio.sleep(0.5)
        try:
            message = self.message_buffer.get_nowait()
            return message
        except Empty:
            return None

    async def _raw_to_text(self, raw_input: str) -> Message:
        """
        Process raw input to generate a timestamped message.

        Creates a Message object from the raw input string, adding
        the current timestamp.

        Parameters
        ----------
        raw_input : str
            Raw input string to be processed

        Returns
        -------
        Message
            A timestamped message containing the processed input
        """
        return Message(timestamp=time.time(), message=raw_input)

    async def raw_to_text(self, raw_input: Optional[str]):
        """
        Convert raw input to text and update message buffer.

        Processes the raw input if present and adds the resulting
        message to the internal message buffer.

        Parameters
        ----------
        raw_input : Optional[str]
            Raw input to be processed, or None if no input is available
        """
        if raw_input is None:
            return

        pending_message = await self._raw_to_text(raw_input)

        if pending_message is not None:
            self.messages.append(pending_message)

    def formatted_latest_buffer(self) -> Optional[str]:
        """
        Format and clear the latest buffer contents.

        Retrieves the most recent message from the buffer, formats it
        with timestamp and class name, adds it to the IO provider,
        and clears the buffer.

        Returns
        -------
        Optional[str]
            Formatted string containing the latest message and metadata,
            or None if the buffer is empty

        """
        if len(self.messages) == 0:
            return None

        latest_message = self.messages[-1]

        result = f"""
INPUT: {self.descriptor_for_LLM}
// START
{latest_message.message}
// END
"""

        self.io_provider.add_input(
            self.__class__.__name__, latest_message.message, latest_message.timestamp
        )
        self.messages = []

        return result

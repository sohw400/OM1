import logging
import time
from typing import Callable, Optional

from om1_utils import ws
from om1_vlm import VideoStream

from .singleton import singleton


@singleton
class VLMAnthropicProvider:
    """
    VLM Provider that handles video streaming and Anthropic Claude API communication.

    This class implements a singleton pattern to manage video input streaming and API
    communication for vision language model services using Claude. It runs in a separate
    thread to handle continuous VLM processing.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "claude-3-5-sonnet-20241022",
        fps: int = 10,
        stream_url: Optional[str] = None,
        camera_index: int = 0,
    ):
        """
        Initialize the VLM Provider.

        Parameters
        ----------
        base_url : str
            The base URL for the Anthropic API.
        api_key : str
            The API key for the Anthropic API.
        model : str
            The Claude model to use. Defaults to claude-3-5-sonnet-20241022.
        fps : int
            The frames per second for the video stream.
        stream_url : str, optional
            The URL for the video stream. If not provided, defaults to None.
        camera_index : int
            The camera index for the video stream device. Defaults to 0.
        """
        self.running: bool = False
        self.api_key: str = api_key
        self.base_url: str = base_url
        self.model: str = model
        self.stream_ws_client: Optional[ws.Client] = (
            ws.Client(url=stream_url) if stream_url else None
        )
        self.video_stream: VideoStream = VideoStream(
            frame_callback=self._process_frame, fps=fps, device_index=camera_index  # type: ignore
        )
        self.message_callback: Optional[Callable] = None

    async def _process_frame(self, frame: str):
        """
        Process a video frame using the Anthropic Claude API.

        Parameters
        ----------
        frame : str
            The base64 encoded video frame to process.
        """
        import aiohttp

        processing_start = time.perf_counter()
        try:
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }

            payload = {
                "model": self.model,
                "max_tokens": 300,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "What is the most interesting aspect in this image? Provide a brief description.",
                            },
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": frame,
                                },
                            },
                        ],
                    }
                ],
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/v1/messages", headers=headers, json=payload
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        processing_latency = time.perf_counter() - processing_start
                        logging.debug(
                            f"Processing latency: {processing_latency:.3f} seconds"
                        )
                        logging.debug(f"Anthropic Claude VLM Response: {result}")

                        # Extract content from Claude's response format
                        if (
                            "content" in result
                            and len(result["content"]) > 0
                            and "text" in result["content"][0]
                        ):
                            content_text = result["content"][0]["text"]
                            # Create OpenAI-compatible response object for consistency
                            mock_response = type(
                                "ChatCompletion",
                                (),
                                {
                                    "choices": [
                                        type(
                                            "Choice",
                                            (),
                                            {
                                                "message": type(
                                                    "Message",
                                                    (),
                                                    {"content": content_text},
                                                )()
                                            },
                                        )()
                                    ]
                                },
                            )()
                            if self.message_callback:
                                self.message_callback(mock_response)
                    else:
                        error_text = await response.text()
                        logging.error(
                            f"Error from Anthropic API: {response.status} - {error_text}"
                        )
        except Exception as e:
            logging.error(f"Error processing frame: {e}")

    def register_message_callback(self, message_callback: Optional[Callable]):
        """
        Register a callback for processing Claude results.

        Parameters
        ----------
        callback : callable
            The callback function to process Claude results.
        """
        self.message_callback = message_callback

    def start(self):
        """
        Start the Anthropic Claude provider.

        Initializes and starts the video stream and processing thread
        if not already running.
        """
        if self.running:
            logging.warning("Anthropic Claude VLM provider is already running")
            return

        self.running = True
        self.video_stream.start()

        if self.stream_ws_client:
            self.stream_ws_client.start()
            self.video_stream.register_frame_callback(
                self.stream_ws_client.send_message
            )

        logging.info("Anthropic Claude VLM provider started")

    def stop(self):
        """
        Stop the Anthropic Claude provider.

        Stops the video stream and processing thread.
        """
        self.running = False
        self.video_stream.stop()

        if self.stream_ws_client:
            self.stream_ws_client.stop()

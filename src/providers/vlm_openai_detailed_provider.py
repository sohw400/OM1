import logging
import time
from typing import Callable, Optional

from om1_utils import ws
from om1_vlm import VideoStream
from openai import AsyncOpenAI

from .singleton import singleton


@singleton
class VLMOpenAIProviderDetailed:
    """
    VLM Provider that handles video streaming and OpenAI API communication.

    This class implements a singleton pattern to manage video input streaming and API
    communication for vlm services. It runs in a separate thread to handle
    continuous vlm processing.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        fps: int = 1,
        stream_url: Optional[str] = None,
        model: str = "gpt-4o-mini",  # Allow model configuration
    ):
        """
        Initialize the VLM Provider.

        Parameters
        ----------
        base_url : str
            The base URL for the OM API.
        api_key : str
            The API key for the OM API.
        fps : int
            The frames per second for the video stream.
        stream_url : str, optional
            The URL for the video stream. If not provided, defaults to None.
        model : str
            The model to use for vision processing (default: gpt-4o-mini)
        """
        self.running: bool = False
        self.model = model
        self.api_client: AsyncOpenAI = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.stream_ws_client: Optional[ws.Client] = (
            ws.Client(url=stream_url) if stream_url else None
        )
        self.video_stream: VideoStream = VideoStream(
            frame_callback=self._process_frame, fps=fps
        )
        self.message_callback: Optional[Callable] = None
        
        # Track processing state
        self.is_processing = False
        self.last_processed_time = 0
        self.min_processing_interval = 1.0  # Minimum seconds between API calls

    async def _process_frame(self, frame: str):
        """
        Process a video frame using the LLM API.

        Parameters
        ----------
        frame : str
            The base64 encoded video frame to process.
        """
        # Skip if already processing or too soon since last call
        current_time = time.time()
        if self.is_processing or (current_time - self.last_processed_time) < self.min_processing_interval:
            return
            
        self.is_processing = True
        self.last_processed_time = current_time
        
        processing_start = time.perf_counter()
        try:
            response = await self.api_client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a vision analysis assistant. Describe what you see in the image clearly and concisely."
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "What do you see in this image? Describe the main subjects, actions, and any notable details.",
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{frame}",
                                    "detail": "high",
                                },
                            },
                        ],
                    }
                ],
                max_tokens=300,
                temperature=0.7,
            )
            
            processing_latency = time.perf_counter() - processing_start
            logging.debug(f"Processing latency: {processing_latency:.3f} seconds")
            
            # Check if we got a valid response
            if response.choices and response.choices[0].message.content:
                logging.info(f"VLM Response: {response.choices[0].message.content}")
                if self.message_callback:
                    self.message_callback(response)
            else:
                logging.warning("Received empty response from VLM")
                
        except Exception as e:
            logging.error(f"Error processing frame: {e}")
            logging.error(f"Error type: {type(e).__name__}")
            if hasattr(e, 'response'):
                logging.error(f"API Response: {e.response}")
        finally:
            self.is_processing = False

    def register_message_callback(self, message_callback: Optional[Callable]):
        """
        Register a callback for processing VLM results.

        Parameters
        ----------
        callback : callable
            The callback function to process VLM results.
        """
        self.message_callback = message_callback

    def set_processing_interval(self, interval: float):
        """
        Set the minimum interval between frame processing.
        
        Parameters
        ----------
        interval : float
            Minimum seconds between API calls
        """
        self.min_processing_interval = max(0.1, interval)  # Minimum 0.1 seconds

    def start(self):
        """
        Start the VLM provider.

        Initializes the video stream and starts the processing thread.
        """
        if self.running:
            logging.warning("VLM provider is already running")
            return

        self.running = True
        self.video_stream.start()

        if self.stream_ws_client:
            self.stream_ws_client.start()
            self.video_stream.register_frame_callback(
                self.stream_ws_client.send_message
            )

        logging.info(f"OpenAI VLM provider started with model: {self.model}")
        logging.info(f"Processing interval: {self.min_processing_interval} seconds")

    def stop(self):
        """
        Stop the VLM provider.

        Stops the video stream and processing thread.
        """
        self.running = False
        self.video_stream.stop()

        if self.stream_ws_client:
            self.stream_ws_client.stop()
            
        logging.info("OpenAI VLM provider stopped")
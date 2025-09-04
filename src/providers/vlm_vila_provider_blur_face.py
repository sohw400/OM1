# om1_vlm/vila_vlm/vlm_vila_provider.py
import logging
from pathlib import Path
from typing import Callable, Optional

from om1_utils import ws
from om1_vlm import VideoStreamBlurFace

# import your local logging helpers (same folder as this file)
from .logging_info import (
    setup_logging_mp_main,  # main-process: create handlers + QueueListener
)
from .singleton import singleton


@singleton
class VLMVilaProviderBlurFace:
    """
    VLM Provider that owns:
      • a WebSocket client for VLM messages,
      • an optional second WebSocket client for mirroring raw frames,
      • a VideoStreamBlurFace pipeline (camera → optional face blur → base64 JPEG callbacks).

    Logging:
      • Initializes a QueueListener in the main process (console/file handlers).
      • Passes log_queue to VideoStreamBlurFace so child processes forward logs here.
    """

    def __init__(self, ws_url: str, fps: int = 30, stream_url: Optional[str] = None):
        """
        Parameters
        ----------
        ws_url : str
            WebSocket URL for VLM messages (frames are also sent here).
        fps : int, optional
            Target camera FPS, by default 30.
        stream_url : Optional[str], optional
            Optional second WebSocket endpoint to also mirror frames to, by default None.
        """
        self.running: bool = False

        # Main-process logging setup (console by default; file optional)
        self._log_listener, self._log_queue = setup_logging_mp_main(
            config_name="vila_vlm",
            log_level="INFO",
            log_to_file=False,  # set True if you want a logs/… file written too
            logging_config=None,  # or pass LoggingConfig("DEBUG", True)
        )

        # WebSocket(s)
        self.ws_client: ws.Client = ws.Client(url=ws_url)
        self.stream_ws_client: Optional[ws.Client] = (
            ws.Client(url=stream_url) if stream_url else None
        )

        # Resolve SCRFD engine path (enable blur only if present)
        engine_path = self._resolve_engine()
        blur_enabled = engine_path is not None
        if not blur_enabled:
            logging.info("Face anonymization disabled (SCRFD engine not found).")

        # Build the video stream (defaults for everything else)
        self.video_stream: VideoStreamBlurFace = VideoStreamBlurFace(
            frame_callbacks=self.ws_client.send_message,  # base64 JPEG per frame → VLM WS
            fps=fps,
            blur_enabled=blur_enabled,
            scrfd_engine=engine_path,
            scrfd_input="input.1",
            scrfd_size=640,
            # pass the queue so *child* processes route logs to this process
            log_queue=self._log_queue,
        )

    # ---------- public API ----------

    def register_frame_callback(
        self, video_callback: Optional[Callable[[str], None]]
    ) -> None:
        """
        Register a callback for processing video frames.

        Parameters
        ----------
        video_callback : callable
            The callback function to process video frames.
        """
        if video_callback:
            self.video_stream.register_frame_callback(video_callback)

    def register_message_callback(
        self, message_callback: Optional[Callable[[str], None]]
    ) -> None:
        """
        Register a callback for processing VLM results.

        Parameters
        ----------
        callback : callable
            The callback function to process VLM results.
        """
        if message_callback:
            self.ws_client.register_message_callback(message_callback)

    def start(self) -> None:
        """
        Start the VLM provider.

        Initializes and starts the websocket client, video stream, and processing thread
        if not already running.
        """
        if self.running:
            logging.warning("VLM provider is already running.")
            return

        self.running = True
        self.ws_client.start()
        self.video_stream.start()

        if self.stream_ws_client:
            self.stream_ws_client.start()
            # mirror frames to the second WS too
            self.video_stream.register_frame_callback(
                self.stream_ws_client.send_message
            )

        logging.info("Vila VLM provider started")

    def stop(self) -> None:
        """Stop everything and release resources (including the QueueListener)."""
        if not self.running:
            # still stop listener if we created it
            if self._log_listener:
                try:
                    self._log_listener.stop()
                except Exception:
                    pass
            return

        self.running = False

        # Stop video first to free the camera/GPU quickly.
        try:
            self.video_stream.stop()
            self.ws_client.stop()
            self._log_listener.stop()
        except Exception:
            pass

        if self.stream_ws_client:
            try:
                self.stream_ws_client.stop()
            except Exception:
                pass

        logging.info("VLMVilaProvider stopped.")

    # ---------- helpers ----------

    def _resolve_engine(self) -> Optional[str]:
        """
        Best-effort discovery of the SCRFD TensorRT engine.

        Search order:
          1) walk up from this file to find a directory literally named 'OM1'
             containing 'models/scrfd_2.5g_640.engine'
          2) fallback: first ancestor with a 'models/scrfd_2.5g_640.engine'
        """
        start = Path(__file__).resolve()

        for p in (start, *start.parents):
            if p.name == "OM1" and (p / "models" / "scrfd_2.5g_640.engine").is_file():
                return str((p / "models" / "scrfd_2.5g_640.engine").resolve())

        for p in (start, *start.parents):
            cand = p / "models" / "scrfd_2.5g_640.engine"
            if cand.is_file():
                return str(cand.resolve())

        return None

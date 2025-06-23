import asyncio
import datetime
import json
import logging
import time
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
from ultralytics import YOLO

from inputs.base import SensorConfig
from inputs.base.loop import FuserInput
from providers.io_provider import IOProvider

# Common resolutions to test (width, height), ordered high to low
RESOLUTIONS = [
    (3840, 2160),  # 4K
    (2560, 1440),  # QHD
    (1920, 1080),  # Full HD
    (1280, 720),  # HD
    (1024, 576),
    (800, 600),
    (640, 480),  # VGA fallback
]


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


def set_best_resolution(cap, resolutions):
    for width, height in resolutions:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        # Give it a moment to settle
        time.sleep(0.1)

        actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        if actual_width == width and actual_height == height:
            logging.info(f"✅ Resolution set to: {width}x{height}")
            return width, height

    logging.info("⚠️ Could not set preferred resolution. Using default.")
    return int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(
        cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    )


# if working on Mac, please disable continuity camera on your iphone
# Settings > General > AirPlay & Continuity, and turn off Continuity
def check_webcam(index_to_check):
    """
    Checks if a webcam is available and returns True if found, False otherwise.
    """
    cap = cv2.VideoCapture(index_to_check)
    if not cap.isOpened():
        logging.error(f"YOLO did not find cam: {index_to_check}")
        return 0, 0

    # Set the best available resolution
    width, height = set_best_resolution(cap, RESOLUTIONS)
    logging.info(f"YOLO found cam: {index_to_check} set to {width}{height}")
    return width, height


class VLM_Local_YOLO(FuserInput[str]):
    """ """

    def __init__(self, config: SensorConfig = SensorConfig()):
        """
        Initialize VLM input handler with empty message buffer.
        """
        super().__init__(config)

        self.camera_index = 0  # default to default webcam unless specified otherwsie
        if self.config.camera_index:
            self.camera_index = self.config.camera_index

        self.log_file = False
        self.log_file_opened = None

        if self.config.log_file:
            self.log_file = self.config.log_file

        # Track IO
        self.io_provider = IOProvider()

        # Messages buffer
        self.messages: list[Message] = []

        # Simple description of sensor output to help LLM understand its importance and utility
        self.descriptor_for_LLM = "Eyes"

        # Load model
        self.model = YOLO("yolov8n.pt")

        # Create timestamped log filename
        if self.log_file:
            start_time = datetime.datetime.now(datetime.UTC)
            log_filename = f"dump/yolo_{start_time.isoformat(timespec='seconds').replace(':', '-')}Z.jsonl"
            self.log_file_opened = open(log_filename, "a")
            logging.info(f"YOLO Logging to {log_filename}")

        self.width, self.height = check_webcam(self.camera_index)

        self.have_cam = False

        if self.width > 0:
            self.have_cam = True

        self.frame_index = 0

        # Start capturing video, if we have a webcam
        self.cap = None
        if self.have_cam:
            self.cap = cv2.VideoCapture(self.camera_index)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.cam_third = int(self.width / 3)
            logging.info(
                f"Webcam pixel dimensions for YOLO: {self.width}, {self.height}"
            )

    def get_top_detection(self, detections):
        """
        Returns the class label and bbox of the detection with the highest confidence.

        Parameters:
            detections (list): List of detection dictionaries, each with 'class', 'confidence', 'bbox'.

        Returns:
            tuple: (label, bbox) of the top detection, or (None, None) if list is empty.
        """
        if not detections:
            return None, None

        top = max(detections, key=lambda d: d["confidence"])
        return top["class"], top["bbox"]

    async def _poll(self) -> np.ndarray:
        """
        Poll for new image input.

        Currently generates random colored images for testing.
        In production, this would interface with camera or sensor.

        Returns
        -------
        np.ndarray
            Generated or captured image as a numpy array
        """
        await asyncio.sleep(0.3)

        if self.have_cam:
            ret, frame = self.cap.read()
            # logging.debug(f"VLM_YOLO_Local frame: {frame}")
            return frame

    async def _raw_to_text(self, raw_input: Optional[np.ndarray]) -> Optional[Message]:
        """
        Process raw image input to generate text description.

        Parameters
        ----------
        raw_input : np.ndarray
            Input numpy array image to process

        Returns
        -------
        Message
            Timestamped message containing description
        """

        self.frame_index += 1

        sentence = None
        timestamp = time.time()
        datetime_str = datetime.datetime.fromtimestamp(
            timestamp, datetime.UTC
        ).isoformat()

        results = self.model.predict(
            source=raw_input, save=False, stream=True, verbose=False
        )

        detections = []
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = map(float, box.xyxy[0])
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                label = self.model.names[cls]

                detections.append(
                    {
                        "class": label,
                        "confidence": round(conf, 4),
                        "bbox": [round(x1), round(y1), round(x2), round(y2)],
                    }
                )

        # Print to terminal
        logging.debug(
            f"\nFrame {self.frame_index} @ {datetime_str} — {len(detections)} objects:"
        )

        if self.log_file and self.log_file_opened:
            json_line = json.dumps(
                {
                    "frame": self.frame_index,
                    "timestamp": timestamp,
                    "datetime": datetime_str,
                    "detections": detections,
                }
            )
            self.log_file_opened.write(json_line + "\n")
            self.log_file_opened.flush()

        for det in detections:
            logging.debug(
                f"  {det['class']} ({det['confidence']:.2f}) -> {det['bbox']}"
            )

        if detections:
            thing, bbox = self.get_top_detection(detections)
            x1 = bbox[0]
            x2 = bbox[2]
            center_x = (x1 + x2) / 2  # center of the bbox

            direction = "in front of you"
            if center_x < self.cam_third:
                direction = "on your left"
            elif center_x > 2 * self.cam_third:
                direction = "on your right"

            sentence = f"You see a {thing} {direction}."

        if sentence is not None:
            return Message(timestamp=time.time(), message=sentence)

    async def raw_to_text(self, raw_input: np.ndarray):
        """
        Convert raw image to text and update message buffer.

        Parameters
        ----------
        raw_input : np.ndarray
            Raw image to be processed
        """
        pending_message = await self._raw_to_text(raw_input)

        if pending_message is not None:
            self.messages.append(pending_message)

    def formatted_latest_buffer(self) -> Optional[str]:
        """
        Format and clear the latest buffer contents.

        Formats the most recent message with timestamp and class name,
        adds it to the IO provider, then clears the buffer.

        Returns
        -------
        Optional[str]
            Formatted string of buffer contents or None if buffer is empty
        """
        if len(self.messages) == 0:
            return None

        latest_message = self.messages[-1]

        logging.info(f"VLM_YOLO_Local: {latest_message.message}")

        result = (
            f"\nINPUT: {self.descriptor_for_LLM}\n// START\n"
            f"{latest_message.message}\n// END\n"
        )

        self.io_provider.add_input(
            self.descriptor_for_LLM, latest_message.message, latest_message.timestamp
        )
        self.messages = []

        return result

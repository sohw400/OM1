# This file is used to test for the realsense camera without the VLM
import logging
import os
import time

import cv2
import numpy as np
import pyrealsense2 as rs

from .singleton import singleton


@singleton
class RealSenseVLMProvider:
    """
    RealSense VLM Provider that handles video streaming and websocket communication.

    This class implements a singleton pattern to manage video input streaming and websocket
    communication for VLM services. It runs in a separate thread to handle
    continuous VLM processing.
    """

    def __init__(self):
        """
        Initialize the RealSense VLM Provider.
        """
        os.makedirs("logs/spatial", exist_ok=True)

        self.pipeline = rs.pipeline()
        config = rs.config()

        pipeline_wrapper = rs.pipeline_wrapper(self.pipeline)
        pipeline_profile = config.resolve(pipeline_wrapper)
        device = pipeline_profile.get_device()

        self.found_rgb = False
        for s in device.sensors:
            if s.get_info(rs.camera_info.name) == "RGB Camera":
                self.found_rgb = True
                break
        if not self.found_rgb:
            logging.error("The provider requires Depth camera with Color sensor")
            return

        config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
        config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)

        self.pipeline.start(config)

        self.start()

    def start(self):
        if not self.found_rgb:
            logging.error("Cannot start RealSenseVLMProvider: RGB Camera not found")
            return

        try:
            while True:
                frames = self.pipeline.wait_for_frames()
                depth_frame = frames.get_depth_frame()
                color_frame = frames.get_color_frame()

                if not depth_frame or not color_frame:
                    continue

                depth_image = np.asanyarray(depth_frame.get_data())
                color_image = np.asanyarray(color_frame.get_data())

                depth_colormap = cv2.applyColorMap(
                    cv2.convertScaleAbs(depth_image, alpha=0.03), cv2.COLORMAP_JET
                )
                timestamp = int(time.time() * 1000)
                depth_path = f"logs/spatial/depth_{timestamp}.png"
                color_path = f"logs/spatial/color_{timestamp}.png"
                cv2.imwrite(depth_path, depth_colormap)
                cv2.imwrite(color_path, color_image)

        except Exception as e:
            logging.error(f"An error occurred: {e}")

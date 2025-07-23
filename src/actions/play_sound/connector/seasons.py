import logging
import subprocess
import time
import os
import sys

from actions.base import ActionConfig, ActionConnector
from actions.move.interface import MoveInput

DEFAULT_SOUNDS_DIR = ""
SOUND_FILES = {
    "spring": "spring.mp3",
    "summer": "summer.mp3",
    "fall":   "fall.mp4",
    "winter": "winter.mp4",
}


class SoundConnector(ActionConnector[MoveInput]):
    """
    A connector that plays one of four season sounds when prompted.

    When a Move input is received whose action is 'spring', 'summer',
    'fall', or 'winter', the connector plays the corresponding sound file.
    """

    def __init__(self, config: ActionConfig):
        super().__init__(config)

        # Allow overriding via config, else use default
        self.sounds_dir = getattr(self.config, "sounds_dir", DEFAULT_SOUNDS_DIR)
        if not os.path.isdir(self.sounds_dir):
            logging.error(
                f"Sounds directory '{self.sounds_dir}' not found; "
            )

    async def connect(self, output_interface: MoveInput) -> None:
        action = output_interface.action.lower()
        if action in SOUND_FILES:
            logging.info(f"Playing sound for season: {action}")
            self._play_sound(action)
        else:
            logging.info(f"No sound mapped for action '{action}'")

    def _play_sound(self, season: str) -> None:
        """
        Plays the sound file corresponding to the given season.
        Uses the system play command depending on mac or linux. 
        """
        filename = SOUND_FILES[season]
        path = os.path.join(self.sounds_dir, filename)

        if not os.path.isfile(path):
            logging.error(f"Sound file not found: {path}")
            return

        # Choose player based on OS
        if sys.platform == "darwin":
            player_cmd = ["afplay", path]
        elif sys.platform.startswith("linux"):
            player_cmd = ["aplay", path]
        else:
            logging.error("Unsupported Platform")

        try:
            subprocess.run(player_cmd, check=True, timeout=5)
            logging.info(f"Successfully played '{filename}'")
        except subprocess.CalledProcessError as e:
            logging.error(f"Error playing sound '{filename}': {e}")
        except subprocess.TimeoutExpired:
            logging.error(f"Playing sound '{filename}' timed out")

    def tick(self) -> None:
        time.sleep(0.1)

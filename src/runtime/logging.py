import logging
import os
import time


def setup_logging(config_name: str, debug: bool = False, log_to_file: bool = False):
    """
    Set up the logging configuration for the application.

    Parameters
    ----------
    config_name : str
        The name of the configuration file to use for logging.
    debug : bool, optional
        If True, set the logging level to DEBUG; otherwise, set it to INFO.
        Defaults to False.
    log_to_file : bool, optional
        If True, log messages will also be written to a file.
        Defaults to False.
    """
    level = logging.DEBUG if debug else logging.INFO

    logging.getLogger().handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    handlers = [console_handler]

    if log_to_file:

        os.makedirs("logs", exist_ok=True)

        file_handler = logging.FileHandler(
            f"logs/{config_name}_{time.strftime('%Y-%m-%d_%H-%M-%S')}.log",
            mode="a",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    logging.basicConfig(level=level, handlers=handlers)

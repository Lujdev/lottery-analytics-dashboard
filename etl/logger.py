import logging
from pathlib import Path

LOG_FILE = Path(__file__).parent.parent / "logs" / "etl.log"


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    fh = logging.FileHandler(LOG_FILE)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger

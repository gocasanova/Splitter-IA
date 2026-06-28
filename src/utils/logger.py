# Logging configuration
import logging
import sys
from pathlib import Path
from src.utils.config import BASE_DIR, LOG_LEVEL, LOG_FORMAT, CACHE_BASE_DIR, ensure_directory

def setup_logger(name: str) -> logging.Logger:
    """Set up logger with both console and file output."""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, LOG_LEVEL))
    logger.propagate = False

    if logger.handlers:
        return logger

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, LOG_LEVEL))
    formatter = logging.Formatter(LOG_FORMAT)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    try:
        log_dir = ensure_directory(CACHE_BASE_DIR / "logs", BASE_DIR / "cache" / "logs")
        file_handler = logging.FileHandler(log_dir / "app.log")
        file_handler.setLevel(getattr(logging, LOG_LEVEL))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError as exc:
        logger.warning("File logging disabled: %s", exc)

    return logger

"""
Logging configuration using loguru
"""
import sys
from loguru import logger
from config import get_settings

settings = get_settings()


def setup_logging():
    """Configure loguru for the application"""
    logger.remove()  # Remove default handler

    # Console handler - colored and readable
    logger.add(
        sys.stdout,
        level=settings.log_level,
        colorize=True,
        backtrace=True,
        diagnose=False,
    )

    # File handler - full details
    logger.add(
        "logs/bot_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation="1 day",
        retention="7 days",
        compression="zip",
        backtrace=True,
        diagnose=True,
    )

    logger.info("Logging configured")
    return logger

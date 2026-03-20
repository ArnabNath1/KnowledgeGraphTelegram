"""
Knowledge Graph Builder Bot - Main Entry Point
"""
from utils.logging_config import setup_logging
logger = setup_logging()

from bot.telegram_bot import KnowledgeGraphBot
from utils.health_check import run_health_check


def main():
    try:
        logger.info("🚀 Starting health check server...")
        run_health_check()
        
        logger.info("🚀 Initializing Knowledge Graph Builder Bot...")
        bot = KnowledgeGraphBot()
        # run_polling() is blocking and handles its own event loop
        bot.run()
    except Exception as e:
        logger.critical(f"Bot failed to start: {e}")


if __name__ == "__main__":
    main()

"""
SM_Automation Entry Point
"""
from asyncio.log import logger

from common.logger import LoggerManager
from pathlib import Path


def main() -> None:
    """
    Main Function
    """
    project_root = Path(__file__).resolve().parent.parent

    print("=" * 50)
    print("SM_Automation")
    print("=" * 50)
    print("Project Root : {project_root}")
    print("=" * 50)

    logger = LoggerManager().get_logger()

    logger.info("Application Started")

    logger.warning("Disk Usage 85%")

    logger.error("SSH Timeout")

if __name__ == "__main__":
    main()
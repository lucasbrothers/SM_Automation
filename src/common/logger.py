"""
SM_Automation Logger Framework

Author : RUCAS Brother
Description :
    Central Logging Framework for SM_Automation.

Features
--------
- Singleton Logger Manager
- Auto Log Directory Creation
- Project Root Detection
- Console/File Handler (Next Task)
"""

from __future__ import annotations

from pathlib import Path
from threading import Lock

import logging
from logging.handlers import RotatingFileHandler


class LoggerManager:
    """
    Singleton Logger Manager.

    This class is responsible for creating and managing
    the application's root logger.

    Only one instance can exist during application lifetime.
    """

    _instance: "LoggerManager | None" = None
    _lock: Lock = Lock()

    def __new__(cls) -> "LoggerManager":
        """
        Create singleton instance.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)

        return cls._instance

    def __init__(self) -> None:
        """
        Initialize logger manager.

        This method runs only once.
        """
        if getattr(self, "_initialized", False):
            return

        self.project_root = self._find_project_root()

        self.log_directory = self.project_root / "logs"

        self.log_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.log_file = self.log_directory / "sm_automation.log"

        self.logger = logging.getLogger("SM_Automation")

        self.logger.setLevel(logging.INFO)

        self._configure_logger()

        self._initialized = True

    @staticmethod
    def _find_project_root() -> Path:
        """
        Find project root directory.

        Returns
        -------
        Path
            Project root path.
        """
        return Path(__file__).resolve().parents[2]

    def _configure_logger(self) -> None:
        """
        Configure logger handlers.

        This method runs only once.
        """

        if self.logger.handlers:
            return

        formatter = logging.Formatter(
            fmt=(
                "%(asctime)s.%(msecs)03d | "
                "%(levelname)-8s | "
                "%(name)s | "
                "%(funcName)s | "
                "L%(lineno)d | "
                "%(message)s"
            ),
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        #
        # Console Handler
        #
        console_handler = logging.StreamHandler()

        console_handler.setLevel(logging.INFO)

        console_handler.setFormatter(formatter)

        #
        # File Handler
        #
        file_handler = RotatingFileHandler(
            filename=self.log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=30,
            encoding="utf-8",
        )

        file_handler.setLevel(logging.INFO)

        file_handler.setFormatter(formatter)

        self.logger.addHandler(console_handler)

        self.logger.addHandler(file_handler)

        self.logger.propagate = False

    def get_logger(self) -> logging.Logger:
        """
        Return application logger.
        """

        return self.logger
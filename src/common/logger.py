from __future__ import annotations

import ipaddress
import logging
import logging.handlers
import re
from dataclasses import dataclass
from pathlib import Path
from threading import Lock


class SensitiveDataFilter(logging.Filter):
    """Mask sensitive information from log messages."""

    _PATTERNS = (
        (
            re.compile(
                r"(?i)(password|passwd|pwd)\s*[:=]\s*[^\s,;]+"
            ),
            r"\1=***",
        ),
        (
            re.compile(
                r"(?i)(token|access_token|refresh_token)\s*[:=]\s*[^\s,;]+"
            ),
            r"\1=***",
        ),
        (
            re.compile(
                r"(?i)(secret|client_secret)\s*[:=]\s*[^\s,;]+"
            ),
            r"\1=***",
        ),
        (
            re.compile(
                r"(?i)(api[_-]?key)\s*[:=]\s*[^\s,;]+"
            ),
            r"\1=***",
        ),
        (
            re.compile(
                r"(?i)(private[_-]?key)\s*[:=]\s*[^\s,;]+"
            ),
            r"\1=***",
        ),
    )

    def filter(self, record: logging.LogRecord) -> bool:
        """Mask sensitive information in the log record."""
        message = record.getMessage()

        for pattern, replacement in self._PATTERNS:
            message = pattern.sub(replacement, message)

        record.msg = message
        record.args = ()

        return True

@dataclass
class LogContext:
    """Store execution context for application logging."""

    hostname: str = "-"
    ip: str = "-"
    os: str = "-"
    sr_number: str = "-"
    operator: str = "-"

    _MAX_LENGTHS = {
        "hostname": 255,
        "ip": 45,
        "os": 50,
        "sr_number": 100,
        "operator": 100,
    }

    def __post_init__(self) -> None:
        """Normalize and validate context values."""
        self.hostname = self._normalize(
            "hostname",
            self.hostname,
        )
        self.ip = self._normalize(
            "ip",
            self.ip,
        )
        self.os = self._normalize(
            "os",
            self.os,
        )
        self.sr_number = self._normalize(
            "sr_number",
            self.sr_number,
        )
        self.operator = self._normalize(
            "operator",
            self.operator,
        )

        self._validate_ip()

    @classmethod
    def _normalize(
        cls,
        field_name: str,
        value: str | None,
    ) -> str:
        """Normalize and validate a context value.

        Args:
            field_name: Context field name.
            value: Context value.

        Returns:
            str: Normalized context value.

        Raises:
            ValueError: If the value contains invalid characters
                or exceeds the maximum length.
        """
        if value is None:
            return "-"

        value = str(value).strip()

        if not value:
            return "-"

        if any(ord(char) < 32 for char in value):
            raise ValueError(
                f"Invalid control character in {field_name}."
            )

        max_length = cls._MAX_LENGTHS[field_name]

        if len(value) > max_length:
            raise ValueError(
                f"{field_name} exceeds the maximum length "
                f"of {max_length} characters."
            )

        return value

    def _validate_ip(self) -> None:
        """Validate the IP address when provided.

        Raises:
            ValueError: If the IP address is invalid.
        """
        if self.ip == "-":
            return

        try:
            ipaddress.ip_address(self.ip)
        except ValueError as exc:
            raise ValueError(
                f"Invalid IP address: {self.ip}"
            ) from exc

    def to_dict(self) -> dict[str, str]:
        """Convert the log context to a dictionary.

        Returns:
            dict[str, str]: Log context values.
        """
        return {
            "hostname": self.hostname,
            "ip": self.ip,
            "os": self.os,
            "sr_number": self.sr_number,
            "operator": self.operator,
        }


class ContextFormatter(logging.Formatter):
    """Format log records with optional execution context."""

    DEFAULT_CONTEXT = {
        "hostname": "-",
        "ip": "-",
        "os": "-",
        "sr_number": "-",
        "operator": "-",
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record with default context values."""
        for key, value in self.DEFAULT_CONTEXT.items():
            if not hasattr(record, key):
                setattr(record, key, value)

        return super().format(record)
class LoggerManager:
    """SM_Automation 중앙 Logger 관리자."""

    _instance: LoggerManager | None = None
    _lock = Lock()

    def __new__(cls) -> LoggerManager:
        """LoggerManager의 Singleton 인스턴스를 생성한다."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)

        return cls._instance

    def __init__(self) -> None:
        """Initialize the LoggerManager.

        The Singleton instance may be initialized multiple times,
        but the actual initialization is performed only once.
        """
        if getattr(self, "_initialized", False):
            return

        self._initialized = True
        self._configured = False

        self.project_root = self._find_project_root()
        self._create_log_directory()

        self.logger: logging.Logger | None = None
        self.log_file: Path | None = None


    def _find_project_root(self) -> Path:
        """SM_Automation 프로젝트 루트 디렉터리를 찾는다.

        Returns:
            Path: 프로젝트 루트 디렉터리 경로.

        Raises:
            RuntimeError: 프로젝트 루트를 찾지 못한 경우.
        """
        current_path = Path(__file__).resolve()

        for parent in current_path.parents:
            if parent.name == "SM_Automation":
                return parent

        raise RuntimeError("SM_Automation 프로젝트 루트 디렉터리를 찾을 수 없습니다.")

    def _create_log_directory(self) -> Path:
        if self.project_root is None:
            raise RuntimeError("프로젝트 루트 디렉터리가 설정되지 않았습니다.")

        log_directory = self.project_root / "logs"

        try:
            log_directory.mkdir(
                parents=True,
                exist_ok=True,
            )
        except OSError as exc:
            raise OSError(
                f"로그 디렉터리를 생성할 수 없습니다: {log_directory}"
            ) from exc

        self.log_directory = log_directory

        return log_directory

    def _create_formatter(self) -> logging.Formatter:
        """Create the standard formatter for application logs.

        Returns:
            logging.Formatter: Configured log formatter.
        """
        log_format = (
            "%(asctime)s.%(msecs)03d | "
            "%(levelname)-8s | "
            "%(name)s | "
            "%(funcName)s | "
            "L%(lineno)d | "
            "host=%(hostname)s | "
            "ip=%(ip)s | "
            "os=%(os)s | "
            "sr=%(sr_number)s | "
            "operator=%(operator)s | "
            "%(message)s"
        )

        date_format = "%Y-%m-%d %H:%M:%S"

        return ContextFormatter(
            fmt=log_format,
            datefmt=date_format,
        )

    def _create_console_handler(
        self,
        formatter: logging.Formatter,
    ) -> logging.StreamHandler:
        """Create a console logging handler.

        Args:
            formatter: Formatter used by the handler.

        Returns:
            logging.StreamHandler: Configured console handler.
        """
        console_handler = logging.StreamHandler()

        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(SensitiveDataFilter())

        return console_handler


    def _create_file_handler(
        self,
        formatter: logging.Formatter,
    ) -> logging.Handler:
        """Create a rotating file logging handler.

        Args:
            formatter: Formatter used by the handler.

        Returns:
            logging.Handler: Configured rotating file handler.

        Raises:
            RuntimeError: Log directory is not configured.
        """
        if self.log_directory is None:
            raise RuntimeError(
                "Log directory is not configured."
            )

        self.log_file = self.log_directory / "sm_automation.log"

        file_handler = logging.handlers.RotatingFileHandler(
            filename=self.log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=30,
            encoding="utf-8",
        )

        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(SensitiveDataFilter())

        return file_handler

    def _configure_logger(self) -> logging.Logger:
        """Configure the application logger.

        Returns:
            logging.Logger: Configured application logger.
        """
        logger = logging.getLogger("SM_Automation")

        if self._configured:
            self.logger = logger
            return logger

        logger.setLevel(logging.INFO)
        logger.propagate = False

        formatter = self._create_formatter()

        console_handler = self._create_console_handler(formatter)
        file_handler = self._create_file_handler(formatter)

        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

        self.logger = logger
        self._configured = True

        return logger

    def get_logger(
        self,
        name: str | None = None,
        context: LogContext | None = None,
    ) -> logging.Logger | logging.LoggerAdapter:
        """Return a configured application logger.

        Args:
            name: Optional logger name.
            context: Optional execution context.

        Returns:
            logging.Logger | logging.LoggerAdapter:
                Configured logger or logger adapter with context.
        """
        if self.logger is None:
            self._configure_logger()

        if name is None or name == "SM_Automation":
            logger_name = "SM_Automation"
        elif name.startswith("SM_Automation."):
            logger_name = name
        else:
            logger_name = f"SM_Automation.{name}"

        logger = logging.getLogger(logger_name)

        if context is None:
            return logger

        return self._create_context_logger(
            logger_name,
            context,
        )

    def _create_context_logger(
        self,
        name: str,
        context: LogContext,
    ) -> logging.LoggerAdapter:
        """Create a logger adapter with execution context.

        Args:
            name: Logger name.
            context: Execution context.

        Returns:
            logging.LoggerAdapter: Logger adapter with context.
        """
        logger = self.get_logger(name)

        return logging.LoggerAdapter(
            logger,
            extra=context.to_dict(),
        )


    def shutdown(self) -> None:
        """Shutdown the logger and release all handlers.

        This method removes and closes all handlers from the
        application logger.
        """
        logger = logging.getLogger("SM_Automation")

        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()

        self.logger = None
        self._configured = False     




def get_logger(
    name: str | None = None,
    context: LogContext | None = None,
) -> logging.Logger | logging.LoggerAdapter:
    """Return a configured application logger.

    Args:
        name: Optional logger name.
        context: Optional execution context.

    Returns:
        logging.Logger | logging.LoggerAdapter:
            Configured logger or logger adapter with context.
    """
    manager = LoggerManager()

    return manager.get_logger(
        name=name,
        context=context,
    )
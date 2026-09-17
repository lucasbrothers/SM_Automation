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
                r"(-----BEGIN [A-Z ]*PRIVATE KEY-----).*?"
                r"(-----END [A-Z ]*PRIVATE KEY-----)",
                re.DOTALL | re.IGNORECASE,
            ),
            r"\1***\2",
        ),
        (
            re.compile(
                r"(?i)(?<![\w-])([\"']?"
                r"(?:password|passwd|pwd|access_token|refresh_token|token|"
                r"client_secret|secret|api[_-]?key|private[_-]?key|authorization)"
                r"[\"']?)\s*[:=]\s*"
                r"(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|"
                r"(?:bearer|basic)\s+[^\s,;&|}\]]+|[^\s,;&|}\]]+)",
            ),
            r"\1=***",
        ),
        (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer ***"),
        (re.compile(r"(?i)\bbasic\s+[A-Za-z0-9+/=]+"), "Basic ***"),
    )

    @classmethod
    def mask(cls, message: str) -> str:
        """Redact supported credential assignments and authentication values."""
        for pattern, replacement in cls._PATTERNS:
            message = pattern.sub(replacement, message)
        return message

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact rendered text without reconstructing exception objects."""
        record.msg = self.mask(record.getMessage())
        record.args = ()
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = self.mask(record.exc_text)
        if record.stack_info:
            record.stack_info = self.mask(record.stack_info)
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

        if any(
            ord(char) < 32 or 127 <= ord(char) <= 159
            or char in "\u2028\u2029"
            for char in value
        ):
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

        formatted = super().format(record)

        formatted = SensitiveDataFilter.mask(formatted)

        formatted = formatted.replace("\r\n", "\\n")
        formatted = formatted.replace("\r", "\\r")
        formatted = formatted.replace("\n", "\\n")

        return "".join(
            f"\\x{ord(char):02x}" if ord(char) < 32 or 127 <= ord(char) <= 159
            else f"\\u{ord(char):04x}" if char in "\u2028\u2029"
            else char
            for char in formatted
        )


class LoggerManager:
    """Manage application logging through a single shared instance."""

    _instance: LoggerManager | None = None
    _lock = Lock()

    def __new__(cls) -> LoggerManager:
        """Return the singleton manager instance."""
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
        with self._lock:
            if getattr(self, "_initialized", False):
                return
            self.project_root = self._find_project_root()
            self._create_log_directory()
            self.logger: logging.Logger | None = None
            self.log_file: Path | None = None
            self._configured = False
            self._initialized = True


    def _find_project_root(self) -> Path:
        """Locate the project root independently of the checkout name."""
        return Path(__file__).resolve().parents[2]

    def _create_log_directory(self) -> Path:
        """Create the application's log directory."""
        if self.project_root is None:
            raise RuntimeError("Project root is not configured.")

        log_directory = self.project_root / "logs"

        try:
            log_directory.mkdir(
                parents=True,
                exist_ok=True,
            )
        except OSError as exc:
            raise OSError(
                f"Cannot create log directory: {log_directory}"
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
        with self._lock:
            logger = logging.getLogger("SM_Automation")
            if self._configured:
                return logger
            formatter = self._create_formatter()
            console_handler = self._create_console_handler(formatter)
            try:
                file_handler = self._create_file_handler(formatter)
            except Exception:
                console_handler.close()
                self.log_file = None
                raise
            logger.setLevel(logging.INFO)
            logger.propagate = False
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
        with self._lock:
            logger = logging.getLogger("SM_Automation")
            try:
                for handler in logger.handlers[:]:
                    logger.removeHandler(handler)
                    handler.close()
            finally:
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

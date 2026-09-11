import logging

import pytest

from common.logger import LogContext
from common.logger import LoggerManager
from common.logger import SensitiveDataFilter
from common.logger import get_logger


def test_logger_manager_is_singleton():
    """Verify that LoggerManager returns the same instance."""
    manager1 = LoggerManager()
    manager2 = LoggerManager()

    assert manager1 is manager2


def test_log_context_default_values():
    """Verify default values of LogContext."""
    context = LogContext()

    assert context.hostname == "-"
    assert context.ip == "-"
    assert context.os == "-"
    assert context.sr_number == "-"
    assert context.operator == "-"


def test_log_context_normalization():
    """Verify normalization of empty and whitespace values."""
    context = LogContext(
        hostname="  WEB01  ",
        ip=" 10.10.10.10 ",
        os=" Linux ",
        sr_number=" SR-001 ",
        operator=" D25950 ",
    )

    assert context.hostname == "WEB01"
    assert context.ip == "10.10.10.10"
    assert context.os == "Linux"
    assert context.sr_number == "SR-001"
    assert context.operator == "D25950"


def test_log_context_empty_values():
    """Verify empty values are converted to default values."""
    context = LogContext(
        hostname="",
        ip="",
        os=" ",
        sr_number="",
        operator=None,
    )

    assert context.hostname == "-"
    assert context.ip == "-"
    assert context.os == "-"
    assert context.sr_number == "-"
    assert context.operator == "-"


def test_log_context_valid_ipv4():
    """Verify valid IPv4 addresses."""
    context = LogContext(
        ip="192.168.1.100",
    )

    assert context.ip == "192.168.1.100"


def test_log_context_valid_ipv6():
    """Verify valid IPv6 addresses."""
    context = LogContext(
        ip="2001:db8::10",
    )

    assert context.ip == "2001:db8::10"


def test_log_context_invalid_ip():
    """Verify invalid IP addresses are rejected."""
    with pytest.raises(ValueError, match="Invalid IP address"):
        LogContext(
            ip="999.999.999.999",
        )


def test_log_context_control_character():
    """Verify control characters are rejected."""
    with pytest.raises(
        ValueError,
        match="Invalid control character",
    ):
        LogContext(
            hostname="WEB01\nFAKE_LOG",
        )


def test_log_context_maximum_length():
    """Verify maximum field length."""
    context = LogContext(
        hostname="A" * 255,
    )

    assert len(context.hostname) == 255


def test_log_context_exceeds_maximum_length():
    """Verify excessive field length is rejected."""
    with pytest.raises(
        ValueError,
        match="hostname exceeds the maximum length",
    ):
        LogContext(
            hostname="A" * 256,
        )


def test_log_context_to_dict():
    """Verify LogContext dictionary conversion."""
    context = LogContext(
        hostname="WEB01",
        ip="10.10.10.10",
        os="Linux",
        sr_number="SR-001",
        operator="D25950",
    )

    result = context.to_dict()

    assert result == {
        "hostname": "WEB01",
        "ip": "10.10.10.10",
        "os": "Linux",
        "sr_number": "SR-001",
        "operator": "D25950",
    }


@pytest.mark.parametrize(
    "message, expected",
    [
        (
            "password=Secret123",
            "password=***",
        ),
        (
            "passwd:Secret123",
            "passwd=***",
        ),
        (
            "pwd=Secret123",
            "pwd=***",
        ),
        (
            "access_token=abc123",
            "access_token=***",
        ),
        (
            "refresh_token=abc123",
            "refresh_token=***",
        ),
        (
            "client_secret=Secret123",
            "client_secret=***",
        ),
        (
            "api_key=abc123",
            "api_key=***",
        ),
        (
            "private_key=abc123",
            "private_key=***",
        ),
        (
            "Authorization: Bearer abc123",
            "Authorization=***",
        ),
        (
            "Bearer abc123",
            "Bearer ***",
        ),
        (
            "Basic dXNlcjpwYXNzd29yZA==",
            "Basic ***",
        ),
    ],
)
def test_sensitive_data_filter(
    message: str,
    expected: str,
):
    """Verify sensitive information is masked."""
    record = logging.LogRecord(
        name="SM_Automation.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )

    data_filter = SensitiveDataFilter()

    assert data_filter.filter(record) is True
    assert record.getMessage() == expected


def test_sensitive_data_filter_normal_message():
    """Verify normal messages are not modified."""
    message = "SSH connection established"

    record = logging.LogRecord(
        name="SM_Automation.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )

    data_filter = SensitiveDataFilter()

    data_filter.filter(record)

    assert record.getMessage() == message


def test_logger_without_context():
    """Verify logger works without execution context."""
    logger = get_logger("test")

    assert isinstance(logger, logging.Logger)

    logger.info("Logger without context test")


def test_logger_with_context():
    """Verify logger works with execution context."""
    context = LogContext(
        hostname="WEB01",
        ip="10.10.10.10",
        os="Linux",
        sr_number="SR-001",
        operator="D25950",
    )

    logger = get_logger(
        "test",
        context=context,
    )

    assert isinstance(
        logger,
        logging.LoggerAdapter,
    )

    logger.info("Logger with context test")


def test_logger_manager_application_handler_count():
    """Verify the application logger has the expected handlers."""
    manager = LoggerManager()

    logger = manager.get_logger("handler_test")

    assert logger is not None

    handler_types = {
        type(handler)
        for handler in manager.logger.handlers
    }

    assert logging.StreamHandler in handler_types
    assert logging.handlers.RotatingFileHandler in handler_types

def test_logger_shutdown_removes_application_handlers():
    """Verify shutdown removes application handlers."""
    manager = LoggerManager()

    logger = manager.get_logger("shutdown_test")

    assert logger is not None

    handler_types_before = {
        type(handler)
        for handler in manager.logger.handlers
    }

    assert logging.StreamHandler in handler_types_before
    assert logging.handlers.RotatingFileHandler in handler_types_before

    manager.shutdown()

    assert manager.logger is None
    assert manager._configured is False

    application_logger = logging.getLogger("SM_Automation")

    handler_types_after = {
        type(handler)
        for handler in application_logger.handlers
    }

    assert logging.StreamHandler not in handler_types_after
    assert logging.handlers.RotatingFileHandler not in handler_types_after

    assert application_logger.handlers == []

def test_logger_reconfigure_after_shutdown():
    """Verify the logger can be reconfigured after shutdown."""
    manager = LoggerManager()

    manager.get_logger("before_shutdown")

    manager.shutdown()

    logger = manager.get_logger("after_shutdown")

    assert logger is not None
    assert manager.logger is not None
    assert manager._configured is True

    handler_types = {
        type(handler)
        for handler in manager.logger.handlers
    }

    assert logging.StreamHandler in handler_types
    assert logging.handlers.RotatingFileHandler in handler_types

def test_logger_does_not_duplicate_application_handlers():
    """Verify repeated logger initialization does not duplicate handlers."""
    manager = LoggerManager()

    manager.get_logger("duplicate_test_1")
    manager.get_logger("duplicate_test_2")
    manager.get_logger("duplicate_test_3")

    handlers = manager.logger.handlers

    stream_handlers = [
        handler
        for handler in handlers
        if type(handler) is logging.StreamHandler
    ]

    file_handlers = [
        handler
        for handler in handlers
        if type(handler) is logging.handlers.RotatingFileHandler
    ]

    assert len(stream_handlers) == 1
    assert len(file_handlers) == 1

def test_logger_context_is_applied_to_log_record(caplog):
    """Verify execution context is applied to log records."""
    manager = LoggerManager()

    context = LogContext(
        hostname="server01",
        ip="192.168.10.20",
        os="RHEL8",
        sr_number="SR-20260911-001",
        operator="admin",
    )

    logger = manager.get_logger(
        "context_test",
        context=context,
    )

    with caplog.at_level(logging.INFO, logger="SM_Automation.context_test"):
        logger.info("Context logging test")

    assert len(caplog.records) >= 1

    record = next(
        record
        for record in caplog.records
        if record.message == "Context logging test"
    )

    assert record.hostname == "server01"
    assert record.ip == "192.168.10.20"
    assert record.os == "RHEL8"
    assert record.sr_number == "SR-20260911-001"
    assert record.operator == "admin"


def test_logger_without_context_uses_default_values(caplog):
    """Verify logs without context use default values."""
    manager = LoggerManager()

    logger = manager.get_logger("default_context_test")

    with caplog.at_level(
        logging.INFO,
        logger="SM_Automation.default_context_test",
    ):
        logger.info("Default context test")

    assert len(caplog.records) >= 1

    record = next(
        record
        for record in caplog.records
        if record.message == "Default context test"
    )

    assert getattr(record, "hostname", "-") == "-"
    assert getattr(record, "ip", "-") == "-"
    assert getattr(record, "os", "-") == "-"
    assert getattr(record, "sr_number", "-") == "-"
    assert getattr(record, "operator", "-") == "-"


def test_context_formatter_output():
    """Verify the formatter produces the expected log format."""
    manager = LoggerManager()

    formatter = manager._create_formatter()

    record = logging.LogRecord(
        name="SM_Automation.format_test",
        level=logging.INFO,
        pathname=__file__,
        lineno=123,
        msg="Formatter test message",
        args=(),
        exc_info=None,
    )

    record.hostname = "server01"
    record.ip = "192.168.10.20"
    record.os = "RHEL8"
    record.sr_number = "SR-20260911-001"
    record.operator = "admin"

    formatted = formatter.format(record)

    assert "INFO" in formatted
    assert "SM_Automation.format_test" in formatted
    assert "host=server01" in formatted
    assert "ip=192.168.10.20" in formatted
    assert "os=RHEL8" in formatted
    assert "sr=SR-20260911-001" in formatted
    assert "operator=admin" in formatted
    assert "Formatter test message" in formatted

def test_context_formatter_default_values():
    """Verify the formatter applies default context values."""
    manager = LoggerManager()

    formatter = manager._create_formatter()

    record = logging.LogRecord(
        name="SM_Automation.default_format_test",
        level=logging.INFO,
        pathname=__file__,
        lineno=456,
        msg="Default formatter test",
        args=(),
        exc_info=None,
    )

    formatted = formatter.format(record)

    assert "host=-" in formatted
    assert "ip=-" in formatted
    assert "os=-" in formatted
    assert "sr=-" in formatted
    assert "operator=-" in formatted
    assert "Default formatter test" in formatted

def test_context_formatter_timestamp_format():
    """Verify the formatter uses the expected timestamp format."""
    manager = LoggerManager()

    formatter = manager._create_formatter()

    record = logging.LogRecord(
        name="SM_Automation.timestamp_test",
        level=logging.INFO,
        pathname=__file__,
        lineno=789,
        msg="Timestamp test",
        args=(),
        exc_info=None,
    )

    formatted = formatter.format(record)

    timestamp = formatted.split(" | ", 1)[0]

    assert len(timestamp) == 23
    assert timestamp[4] == "-"
    assert timestamp[7] == "-"
    assert timestamp[10] == " "
    assert timestamp[13] == ":"
    assert timestamp[16] == ":"
    assert timestamp[19] == "."


def test_logger_writes_to_log_file(tmp_path):
    """Verify the logger writes messages to the configured log file."""
    manager = LoggerManager()

    manager.shutdown()

    manager.log_directory = tmp_path
    manager.log_file = None

    logger = manager.get_logger("file_output_test")

    logger.info("File output test message")

    for handler in manager.logger.handlers:
        handler.flush()

    assert manager.log_file is not None
    assert manager.log_file.exists()

    content = manager.log_file.read_text(encoding="utf-8")

    assert "File output test message" in content
    assert "SM_Automation.file_output_test" in content

def test_logger_writes_context_to_log_file(tmp_path):
    """Verify execution context is written to the log file."""
    manager = LoggerManager()

    manager.shutdown()

    manager.log_directory = tmp_path
    manager.log_file = None

    context = LogContext(
        hostname="server01",
        ip="192.168.10.20",
        os="RHEL8",
        sr_number="SR-20260911-001",
        operator="admin",
    )

    logger = manager.get_logger(
        "file_context_test",
        context=context,
    )

    logger.info("File context test message")

    for handler in manager.logger.handlers:
        handler.flush()

    assert manager.log_file is not None
    assert manager.log_file.exists()

    content = manager.log_file.read_text(encoding="utf-8")

    assert "File context test message" in content
    assert "host=server01" in content
    assert "ip=192.168.10.20" in content
    assert "os=RHEL8" in content
    assert "sr=SR-20260911-001" in content
    assert "operator=admin" in content

def test_sensitive_data_is_masked_in_log_file(tmp_path):
    """Verify sensitive data is masked before being written to the log file."""
    manager = LoggerManager()

    manager.shutdown()

    manager.log_directory = tmp_path
    manager.log_file = None

    logger = manager.get_logger("sensitive_file_test")

    logger.info(
        "Login password=SecretPassword123 "
        "token=abc123 "
        "api_key=key-12345"
    )

    for handler in manager.logger.handlers:
        handler.flush()

    assert manager.log_file is not None
    assert manager.log_file.exists()

    content = manager.log_file.read_text(encoding="utf-8")

    assert "password=***" in content
    assert "token=***" in content
    assert "api_key=***" in content

    assert "SecretPassword123" not in content
    assert "abc123" not in content
    assert "key-12345" not in content

def test_authorization_token_is_masked_in_log_file(tmp_path):
    """Verify authorization tokens are masked in the log file."""
    manager = LoggerManager()

    manager.shutdown()

    manager.log_directory = tmp_path
    manager.log_file = None

    logger = manager.get_logger("authorization_file_test")

    logger.info(
        "Authorization: Bearer abc123456789"
    )

    for handler in manager.logger.handlers:
        handler.flush()

    assert manager.log_file is not None
    assert manager.log_file.exists()

    content = manager.log_file.read_text(encoding="utf-8")

    assert "Authorization=***" in content
    assert "abc123456789" not in content
    assert "Bearer abc123456789" not in content

def test_logger_exception_includes_traceback(tmp_path):
    """Verify exception logs include the exception traceback."""
    manager = LoggerManager()

    manager.shutdown()

    manager.log_directory = tmp_path
    manager.log_file = None

    logger = manager.get_logger("exception_test")

    try:
        raise ValueError("Test exception message")
    except ValueError:
        logger.exception("Exception occurred")

    for handler in manager.logger.handlers:
        handler.flush()

    assert manager.log_file is not None
    assert manager.log_file.exists()

    content = manager.log_file.read_text(encoding="utf-8")

    assert "Exception occurred" in content
    assert "ValueError: Test exception message" in content
    assert "Traceback (most recent call last)" in content

def test_logger_exception_masks_sensitive_data(tmp_path):
    """Verify sensitive data is masked in exception logs."""
    manager = LoggerManager()

    manager.shutdown()

    manager.log_directory = tmp_path
    manager.log_file = None

    logger = manager.get_logger("exception_sensitive_test")

    try:
        raise ValueError(
            "Authentication failed password=SecretPassword123"
        )
    except ValueError:
        logger.exception("Operation failed")

    for handler in manager.logger.handlers:
        handler.flush()

    assert manager.log_file is not None
    assert manager.log_file.exists()

    content = manager.log_file.read_text(encoding="utf-8")

    assert "Operation failed" in content
    assert "password=***" in content
    assert "SecretPassword123" not in content

def test_logger_records_info_and_higher_levels(tmp_path):
    """Verify INFO and higher log levels are recorded."""
    manager = LoggerManager()

    manager.shutdown()

    manager.log_directory = tmp_path
    manager.log_file = None

    logger = manager.get_logger("log_level_test")

    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    logger.critical("Critical message")

    for handler in manager.logger.handlers:
        handler.flush()

    assert manager.log_file is not None
    assert manager.log_file.exists()

    content = manager.log_file.read_text(encoding="utf-8")

    assert "Info message" in content
    assert "Warning message" in content
    assert "Error message" in content
    assert "Critical message" in content

def test_logger_does_not_record_debug_level(tmp_path):
    """Verify DEBUG logs are not recorded at the INFO level."""
    manager = LoggerManager()

    manager.shutdown()

    manager.log_directory = tmp_path
    manager.log_file = None

    logger = manager.get_logger("debug_level_test")

    logger.debug("Debug message")
    logger.info("Info message")

    for handler in manager.logger.handlers:
        handler.flush()

    assert manager.log_file is not None
    assert manager.log_file.exists()

    content = manager.log_file.read_text(encoding="utf-8")

    assert "Debug message" not in content
    assert "Info message" in content

def test_logger_and_handler_levels():
    """Verify logger and application handler levels."""
    manager = LoggerManager()

    logger = manager.get_logger("level_configuration_test")

    assert logger.level == logging.NOTSET
    assert logger.getEffectiveLevel() == logging.INFO

    stream_handlers = [
        handler
        for handler in manager.logger.handlers
        if type(handler) is logging.StreamHandler
    ]

    file_handlers = [
        handler
        for handler in manager.logger.handlers
        if type(handler) is logging.handlers.RotatingFileHandler
    ]

    assert len(stream_handlers) == 1
    assert len(file_handlers) == 1

    assert stream_handlers[0].level == logging.INFO
    assert file_handlers[0].level == logging.INFO
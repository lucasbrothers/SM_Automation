import logging

import pytest

from common.logger import LogContext
from common.logger import LoggerManager
from common.logger import SensitiveDataFilter
from common.logger import get_logger


@pytest.fixture(autouse=True)
def isolated_logger(tmp_path, monkeypatch):
    """Isolate singleton state, handlers and log files for every test."""
    previous = LoggerManager._instance
    if previous is not None:
        previous.shutdown()
    monkeypatch.setattr(LoggerManager, "_instance", None)
    monkeypatch.setattr(LoggerManager, "_find_project_root", lambda self: tmp_path)
    manager = LoggerManager()
    yield manager
    manager.shutdown()


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

def test_log_format_field_order():
    """Verify the order of required fields in a formatted log record."""
    manager = LoggerManager()

    context = LogContext(
        hostname="server01",
        ip="192.168.0.10",
        os="Linux",
        sr_number="SR-12345",
        operator="admin",
    )

    logger = manager.get_logger(
        "format_order_test",
        context=context,
    )

    logger.info("format validation message")

    manager.shutdown()

    log_file = manager.log_directory / "sm_automation.log"
    content = log_file.read_text(encoding="utf-8")

    lines = [
        line
        for line in content.splitlines()
        if "format validation message" in line
    ]

    assert len(lines) == 1

    line = lines[0]

    expected_fields = [
        "| INFO",
        "| SM_Automation.format_order_test",
        "host=server01",
        "ip=192.168.0.10",
        "os=Linux",
        "sr=SR-12345",
        "operator=admin",
        "format validation message",
    ]

    positions = [
        line.find(field)
        for field in expected_fields
    ]

    assert all(position >= 0 for position in positions)
    assert positions == sorted(positions)

def test_log_default_context_values():
    """Verify default context values in a log file."""
    manager = LoggerManager()

    logger = manager.get_logger(
        "default_context_test",
    )

    logger.info("default context validation message")

    manager.shutdown()

    log_file = manager.log_directory / "sm_automation.log"
    content = log_file.read_text(encoding="utf-8")

    lines = [
        line
        for line in content.splitlines()
        if "default context validation message" in line
    ]

    assert len(lines) == 1

    line = lines[0]

    assert "host=-" in line
    assert "ip=-" in line
    assert "os=-" in line
    assert "sr=-" in line
    assert "operator=-" in line

def test_log_level_output_behavior():
    """Verify log output behavior for different log levels."""
    manager = LoggerManager()

    logger = manager.get_logger(
        "log_level_output_test",
    )

    logger.debug("debug level message")
    logger.info("info level message")
    logger.warning("warning level message")
    logger.error("error level message")

    manager.shutdown()

    log_file = manager.log_directory / "sm_automation.log"
    content = log_file.read_text(encoding="utf-8")

    assert "debug level message" not in content
    assert "info level message" in content
    assert "warning level message" in content
    assert "error level message" in content

def test_logger_recovery_after_shutdown():
    """Verify logger recovery after shutdown."""
    manager = LoggerManager()

    first_logger = manager.get_logger(
        "recovery_test",
    )

    try:
        raise RuntimeError("recovery test exception")
    except RuntimeError:
        first_logger.exception("First exception message")

    manager.shutdown()

    second_logger = manager.get_logger(
        "recovery_test",
    )

    second_logger.info("Second message after recovery")

    manager.shutdown()

    log_file = manager.log_directory / "sm_automation.log"
    content = log_file.read_text(encoding="utf-8")

    assert "First exception message" in content
    assert "recovery test exception" in content
    assert "Second message after recovery" in content

    application_logger = logging.getLogger("SM_Automation")

    stream_handlers = [
        handler
        for handler in application_logger.handlers
        if type(handler) is logging.StreamHandler
    ]

    file_handlers = [
        handler
        for handler in application_logger.handlers
        if type(handler) is logging.handlers.RotatingFileHandler
    ]

    assert len(stream_handlers) == 0
    assert len(file_handlers) == 0

def test_log_message_control_character_behavior():
    """Verify the current behavior of control characters in log messages."""
    manager = LoggerManager()

    logger = manager.get_logger(
        "message_control_test",
    )

    logger.info("message before newline\nmessage after newline")

    manager.shutdown()

    log_file = manager.log_directory / "sm_automation.log"
    content = log_file.read_text(encoding="utf-8")

    assert "message before newline" in content
    assert "message after newline" in content


@pytest.mark.parametrize("message, secrets", [
    ('{"password": "top secret", "token": "abc123"}', ("top secret", "abc123")),
    ("{'client_secret': 'top secret'}", ("top secret",)),
    ('password="top secret"', ("top secret",)),
    ('Authorization: Basic dXNlcjpwYXNz', ("dXNlcjpwYXNz",)),
    ('{"Authorization": "Bearer abc123"}', ("abc123",)),
    ('jdbc:db?password=hidden&token=abc123', ("hidden", "abc123")),
    ('-----BEGIN PRIVATE KEY-----\nprivatepayload\n-----END PRIVATE KEY-----',
     ("privatepayload",)),
])
def test_structured_credentials_are_masked(message, secrets):
    record = logging.makeLogRecord({"msg": message})
    SensitiveDataFilter().filter(record)
    for secret in secrets:
        assert secret not in record.getMessage()
    assert "***" in record.getMessage()


def test_exception_chain_and_custom_constructor_are_preserved(isolated_logger, capsys):
    class LoginError(Exception):
        def __init__(self, code, detail):
            super().__init__(code, detail)

    logger = isolated_logger.get_logger("exception_chain")
    try:
        try:
            raise ValueError('password="inner secret"')
        except ValueError as cause:
            raise LoginError(403, "Authorization: Basic encodedsecret") from cause
    except LoginError as exc:
        original_args = exc.args
        logger.exception("Login failed")
        assert exc.args == original_args
    content = isolated_logger.log_file.read_text(encoding="utf-8")
    console = capsys.readouterr().err
    for output in (content, console):
        assert "inner secret" not in output
        assert "encodedsecret" not in output
        assert "ValueError" in output
        assert "LoginError" in output
        assert "direct cause" in output
        assert len(output.splitlines()) == 1


@pytest.mark.parametrize("control", ["\n", "\r", "\t", "\x00", "\x1b", "\x85", "\u2028"])
def test_control_characters_cannot_inject_log_lines(isolated_logger, control):
    isolated_logger.get_logger("controls").info("before%safter", control)
    content = isolated_logger.log_file.read_text(encoding="utf-8")
    assert len(content.splitlines()) == 1
    assert control not in content.rstrip("\n")
    assert "before" in content and "after" in content


def test_concurrent_configuration_has_one_handler_pair(isolated_logger):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    barrier = Barrier(8)
    def write_message(index):
        barrier.wait(timeout=10)
        manager = LoggerManager()
        manager.get_logger("concurrent").info("worker-message-%s", index)
        return manager

    with ThreadPoolExecutor(max_workers=8) as executor:
        managers = list(executor.map(write_message, range(8)))
    assert all(manager is isolated_logger for manager in managers)
    assert len([h for h in isolated_logger.logger.handlers
                if type(h) in (logging.StreamHandler,
                               logging.handlers.RotatingFileHandler)]) == 2
    content = isolated_logger.log_file.read_text(encoding="utf-8")
    for index in range(8):
        assert content.count(f"worker-message-{index}") == 1


def test_concurrent_first_initialization_runs_once(isolated_logger, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    monkeypatch.setattr(LoggerManager, "_instance", None)
    original = LoggerManager._create_log_directory
    calls = []

    def create_directory(manager):
        calls.append(manager)
        return original(manager)

    monkeypatch.setattr(LoggerManager, "_create_log_directory", create_directory)
    barrier = Barrier(8)

    def initialize(_):
        barrier.wait(timeout=10)
        return LoggerManager()

    with ThreadPoolExecutor(max_workers=8) as executor:
        managers = list(executor.map(initialize, range(8)))
    assert len(calls) == 1
    assert all(manager is managers[0] for manager in managers)
    assert managers[0]._initialized


@pytest.mark.parametrize("control", ["\x7f", "\x85", "\u2028", "\u2029"])
def test_context_rejects_additional_control_characters(control):
    with pytest.raises(ValueError, match="Invalid control character"):
        LogContext(hostname=f"before{control}after")


def test_filter_masks_cached_exception_and_stack_text():
    record = logging.makeLogRecord({
        "msg": "password=%s",
        "args": ("messagesecret",),
        "exc_text": 'ValueError: {"token": "exceptionsecret"}',
        "stack_info": "stack password=stacksecret",
    })
    data_filter = SensitiveDataFilter()
    data_filter.filter(record)
    first = (record.msg, record.exc_text, record.stack_info)
    data_filter.filter(record)
    assert first == (record.msg, record.exc_text, record.stack_info)
    assert "messagesecret" not in record.msg
    assert "exceptionsecret" not in record.exc_text
    assert "stacksecret" not in record.stack_info


def test_initialization_failure_can_retry(isolated_logger, monkeypatch):
    monkeypatch.setattr(LoggerManager, "_instance", None)
    with monkeypatch.context() as patch:
        def fail(self):
            raise OSError("directory unavailable")
        patch.setattr(LoggerManager, "_create_log_directory", fail)
        with pytest.raises(OSError, match="directory unavailable"):
            LoggerManager()
    manager = LoggerManager()
    try:
        assert manager._initialized
        assert manager.log_directory.is_dir()
        manager.get_logger("retry").info("recovered")
    finally:
        manager.shutdown()


def test_file_handler_failure_can_retry(isolated_logger, monkeypatch):
    with monkeypatch.context() as patch:
        def fail(formatter):
            raise OSError("file unavailable")
        patch.setattr(isolated_logger, "_create_file_handler", fail)
        with pytest.raises(OSError, match="file unavailable"):
            isolated_logger.get_logger()
    assert not isolated_logger._configured
    assert not any(type(h) in (logging.StreamHandler,
                              logging.handlers.RotatingFileHandler)
                   for h in logging.getLogger("SM_Automation").handlers)
    isolated_logger.get_logger().info("retry succeeded")
    assert len([h for h in isolated_logger.logger.handlers
                if type(h) in (logging.StreamHandler,
                               logging.handlers.RotatingFileHandler)]) == 2


def test_rotation_preserves_utf8_and_limits_backups(isolated_logger):
    logger = isolated_logger.get_logger("rotation")
    handler = next(h for h in isolated_logger.logger.handlers
                   if isinstance(h, logging.handlers.RotatingFileHandler))
    assert handler.maxBytes == 10 * 1024 * 1024
    assert handler.backupCount == 30
    handler.maxBytes = 400
    handler.backupCount = 2
    for index in range(12):
        logger.info("\ud55c\uae00 log %s password=rotationsecret", index)
    isolated_logger.shutdown()
    files = list(isolated_logger.log_directory.glob("sm_automation.log*"))
    assert len(files) == 3
    for path in files:
        content = path.read_text(encoding="utf-8")
        assert "\ud55c\uae00 log" in content
        assert "rotationsecret" not in content
    assert "\ud55c\uae00 log 11" in isolated_logger.log_file.read_text(encoding="utf-8")

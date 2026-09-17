"""Load and validate application configuration without external dependencies."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    """Indicate an unreadable or invalid application configuration."""


@dataclass(frozen=True)
class AppConfig:
    """Store validated settings with resolved absolute paths."""

    environment: str
    log_level: str
    log_directory: Path
    server_file: Path
    ssh_timeout: int
    max_workers: int


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigError("Duplicate configuration key.")
        result[key] = value
    return result


def _section(data, name, allowed):
    section = data.get(name, {})
    if not isinstance(section, dict):
        raise ConfigError(f"{name} must be an object.")
    if section.keys() - allowed:
        raise ConfigError(f"Unsupported option in {name}.")
    return section


def _choice(value, name, allowed):
    if not isinstance(value, str) or value not in allowed:
        raise ConfigError(f"Invalid {name}.")
    return value


def _integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ConfigError(f"{name} must be an integer from {minimum} to {maximum}.")
    return value


def _path(value, name, base):
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{name} must be a nonempty path.")
    if any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value):
        raise ConfigError(f"Invalid control character in {name}.")
    try:
        path = Path(value)
        return (base / path).resolve()
    except (OSError, ValueError):
        raise ConfigError(f"Invalid path in {name}.") from None


def load_config(path: str | Path | None = None) -> AppConfig:
    """Read UTF-8 JSON; resolve relative values against the config directory.

    Missing files are errors. Missing supported options receive defaults.
    Configuration values are never included in error messages.
    """
    source = (Path(path) if path is not None else
              Path(__file__).resolve().parents[2] / "config" / "app.json")
    try:
        source = source.resolve()
        data = json.loads(source.read_text(encoding="utf-8"),
                          object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, ValueError) as exc:
        if isinstance(exc, ConfigError):
            raise
        raise ConfigError("Cannot read configuration as valid UTF-8 JSON.") from None
    if not isinstance(data, dict):
        raise ConfigError("Configuration must be an object.")
    if data.keys() - {"environment", "logging", "inventory", "ssh"}:
        raise ConfigError("Unsupported configuration section.")
    logs = _section(data, "logging", {"level", "directory"})
    inventory = _section(data, "inventory", {"server_file"})
    ssh = _section(data, "ssh", {"timeout", "max_workers"})
    return AppConfig(
        environment=_choice(data.get("environment", "development"), "environment",
                            {"development", "test", "production"}),
        log_level=_choice(logs.get("level", "INFO"), "logging.level",
                          {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}),
        log_directory=_path(logs.get("directory", "../logs"),
                            "logging.directory", source.parent),
        server_file=_path(inventory.get("server_file", "servers.txt"),
                          "inventory.server_file", source.parent),
        ssh_timeout=_integer(ssh.get("timeout", 30), "ssh.timeout", 1, 300),
        max_workers=_integer(ssh.get("max_workers", 10), "ssh.max_workers", 1, 100),
    )

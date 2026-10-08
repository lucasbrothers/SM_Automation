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
    data_directory: Path
    backup_directory: Path
    key_file: Path
    listen_host: str
    listen_port: int
    tls_cert: Path
    tls_key: Path
    token_file: Path
    ssh_user: str
    ssh_key_file: Path | None
    ssh_port: int
    privilege: str
    backup_timeout: int
    max_capture_mb: int
    ssh_profiles_file: Path


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


def _boolean(value, name):
    if type(value) is not bool:
        raise ConfigError(f"{name} must be a boolean.")
    return value


def _path(value, name, base):
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{name} must be a nonempty path.")
    if any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value):
        raise ConfigError(f"Invalid control character in {name}.")
    try:
        path = Path(value).expanduser()
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
    if data.keys() - {"environment", "logging", "inventory", "ssh", "storage", "server", "backup"}:
        raise ConfigError("Unsupported configuration section.")
    logs = _section(data, "logging", {"level", "directory"})
    inventory = _section(data, "inventory", {"server_file"})
    ssh = _section(data, "ssh", {"timeout", "max_workers", "user", "key_file", "port", "privilege", "profiles_file"})
    storage = _section(data, "storage", {"data_directory", "backup_directory", "key_file"})
    server = _section(data, "server", {"host", "port", "tls_cert", "tls_key", "token_file"})
    backup = _section(data, "backup", {"timeout", "max_capture_mb"})
    root = Path(__file__).resolve().parents[2]
    secrets = "~/.config/sm-automation"
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
        data_directory=_path(storage.get("data_directory", "./DATA"), "storage.data_directory", root),
        backup_directory=_path(storage.get("backup_directory", "./BACKUP"), "storage.backup_directory", root),
        key_file=_path(storage.get("key_file", secrets + "/master.key"), "storage.key_file", root),
        listen_host=server.get("host", "0.0.0.0"),
        listen_port=_integer(server.get("port", 7443), "server.port", 1024, 65535),
        tls_cert=_path(server.get("tls_cert", secrets + "/server.crt"), "server.tls_cert", root),
        tls_key=_path(server.get("tls_key", secrets + "/server.key"), "server.tls_key", root),
        token_file=_path(server.get("token_file", secrets + "/api.token"), "server.token_file", root),
        ssh_user=ssh.get("user", "D25950"),
        ssh_key_file=_path(ssh["key_file"], "ssh.key_file", root) if ssh.get("key_file") else None,
        ssh_port=_integer(ssh.get("port", 22), "ssh.port", 1, 65535),
        privilege=_choice(ssh.get("privilege", "sudo"), "ssh.privilege", {"sudo", "sudo-su", "direct", "su"}),
        backup_timeout=_integer(backup.get("timeout", 180), "backup.timeout", 10, 3600),
        max_capture_mb=_integer(backup.get("max_capture_mb", 64), "backup.max_capture_mb", 1, 512),
        ssh_profiles_file=_path(ssh.get("profiles_file", secrets + "/ssh-profiles.json"), "ssh.profiles_file", root),
    )

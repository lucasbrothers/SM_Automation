"""Exercise configuration validation and application startup."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from common.config import ConfigError, load_config


@pytest.fixture
def config_file(tmp_path):
    path = tmp_path / "app.json"
    path.write_text("{}", encoding="utf-8")
    return path


def test_defaults(config_file):
    config = load_config(config_file)
    assert config.environment == "development"
    assert config.log_level == "INFO"
    assert config.log_directory == config_file.parent.parent / "logs"
    assert config.server_file == config_file.parent / "servers.txt"
    assert config.ssh_timeout == 30
    assert config.max_workers == 10


def test_explicit_settings_and_path_base(config_file, tmp_path, monkeypatch):
    config_file.write_text(json.dumps({
        "environment": "production",
        "logging": {"level": "DEBUG", "directory": "output"},
        "inventory": {"server_file": str(tmp_path / "hosts.txt")},
        "ssh": {"timeout": 60, "max_workers": 20},
    }), encoding="utf-8")
    monkeypatch.chdir(tmp_path.parent)
    config = load_config(config_file)
    assert config.environment == "production"
    assert config.log_level == "DEBUG"
    assert config.log_directory == tmp_path / "output"
    assert config.server_file == tmp_path / "hosts.txt"
    assert (config.ssh_timeout, config.max_workers) == (60, 20)
    assert not config.log_directory.exists()


@pytest.mark.parametrize("data", [
    [], {"unknown": 1}, {"logging": []}, {"ssh": None},
    {"logging": {"levle": "INFO"}}, {"ssh": {"password": "secret"}},
    {"environment": "invalid"}, {"logging": {"level": 10}},
    {"logging": {"level": "TRACE"}}, {"logging": {"directory": ""}},
    {"inventory": {"server_file": "a\u0000b"}},
    {"ssh": {"timeout": True}}, {"ssh": {"timeout": 0}},
    {"ssh": {"timeout": 301}}, {"ssh": {"timeout": 1.5}},
    {"ssh": {"max_workers": "10"}}, {"ssh": {"max_workers": 101}},
])
def test_invalid_settings(config_file, data):
    config_file.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(config_file)


@pytest.mark.parametrize("content", [b"{broken secret", b"\xff", b'{"ssh":{},"ssh":{}}'])
def test_invalid_files(config_file, content):
    config_file.write_bytes(content)
    with pytest.raises(ConfigError) as error:
        load_config(config_file)
    assert "secret" not in str(error.value)


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "missing.json")


def test_shipped_config():
    config = load_config()
    assert config.log_level == "INFO"
    assert config.server_file.name == "servers.txt"


def run_application(config_file):
    main = Path(__file__).resolve().parents[1] / "src" / "main.py"
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, str(main), "--config", str(config_file)],
                          capture_output=True, text=True, env=environment, timeout=15)


def test_startup_writes_configured_log(config_file):
    config_file.write_text('{"logging":{"directory":"output"}}', encoding="utf-8")
    result = run_application(config_file)
    assert result.returncode == 0, result.stderr
    output = config_file.parent / "output" / "sm_automation.log"
    assert "Application initialized" in output.read_text(encoding="utf-8")


def test_startup_rejects_config_before_logging(config_file):
    config_file.write_text('{"logging":{"directory":"output","level":"bad"}}',
                           encoding="utf-8")
    result = run_application(config_file)
    assert result.returncode == 2
    assert "Configuration error" in result.stderr
    assert not (config_file.parent / "output").exists()


def test_startup_reports_unwritable_log_target(config_file):
    target = config_file.parent / "occupied"
    target.write_text("existing file", encoding="utf-8")
    config_file.write_text('{"logging":{"directory":"occupied"}}', encoding="utf-8")
    result = run_application(config_file)
    assert result.returncode == 1
    assert "logging initialization failed" in result.stderr
    assert target.read_text(encoding="utf-8") == "existing file"

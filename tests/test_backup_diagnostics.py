from types import SimpleNamespace
from unittest.mock import Mock

from backup import collector
from engine.remote import CommandResult


def test_backup_errors_are_visible_without_losing_full_encrypted_diagnostics(monkeypatch):
    monkeypatch.setattr(collector, "commands", lambda family: {})
    monkeypatch.setattr(collector, "capture", lambda *args, **kwargs: CommandResult(
        b"partial output", "Missing optional path: /etc/netplan\nPermission denied: /etc/shadow\n", 1))
    store = Mock()
    store.path.return_value = "/BACKUP/example"
    result = collector.backup_server(None, SimpleNamespace(hostname="lab", ip="127.0.0.1", os="Linux"),
                                    SimpleNamespace(privilege="direct", backup_timeout=30, max_capture_mb=1), store, "run")
    artifact = result["artifacts"][0]
    assert artifact["status"] == "partial"
    assert artifact["warnings"] == ["Missing optional path: /etc/netplan"]
    assert artifact["errors"] == ["Permission denied: /etc/shadow"]
    metadata = next(call.args[1] for call in store.write_json.call_args_list if "metadata" in call.args[0])
    assert "Permission denied: /etc/shadow" in metadata["stderr"]


def test_long_error_summary_marks_limit_and_retains_metadata(monkeypatch):
    stderr = "\n".join(["x" * 1100] * 51)
    monkeypatch.setattr(collector, "commands", lambda family: {})
    monkeypatch.setattr(collector, "capture", lambda *args, **kwargs: CommandResult(b"", stderr, 1))
    store = Mock(); store.path.return_value = "/BACKUP/example"
    result = collector.backup_server(None, SimpleNamespace(hostname="lab", ip="127.0.0.1", os="Linux"),
                                    SimpleNamespace(privilege="direct", backup_timeout=30, max_capture_mb=1), store, "run")
    artifact = result["artifacts"][0]
    assert artifact["errors_truncated"] and len(artifact["errors"]) == 50
    assert all(len(line) == 1000 for line in artifact["errors"])
    metadata = next(call.args[1] for call in store.write_json.call_args_list if "metadata" in call.args[0])
    assert metadata["stderr"] == stderr

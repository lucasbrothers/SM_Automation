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


def test_missing_login_home_is_warning_but_real_permission_denial_stays_partial(monkeypatch):
    monkeypatch.setattr(collector,'commands',lambda family:{})
    store=Mock();store.path.return_value='/BACKUP/fixture'
    server=SimpleNamespace(hostname='lab',ip='127.0.0.1',os='Linux')
    config=SimpleNamespace(privilege='direct',backup_timeout=30,max_capture_mb=1)
    warning='Could not chdir to home directory /home/login: No such file or directory'
    runner=lambda command:CommandResult(b'fixture',warning,0)
    assert collector.backup_server(None,server,config,store,'run',runner=runner)['status']=='completed'
    runner=lambda command:CommandResult(b'fixture',warning+'\nPermission denied',1)
    assert collector.backup_server(None,server,config,store,'run',runner=runner)['status']=='partial'


def test_windows_backup_profiles_suppress_progress_without_hiding_real_errors():
    import base64
    from backup.profiles import windows_files,commands
    for invocation in [windows_files(2),*commands('windows').values()]:
        script=base64.b64decode(invocation.rsplit(' ',1)[1]).decode('utf-16-le')
        assert "$ProgressPreference='SilentlyContinue'" in script
        assert "$ErrorActionPreference='Stop'" in script
        assert '[Console]::Error.WriteLine' in script


def test_clixml_progress_is_not_an_error_and_plain_mixed_or_invalid_errors_remain():
    from engine.remote import powershell_diagnostics
    header='#< CLIXML\n'
    progress='<Objs xmlns="http://schemas.microsoft.com/powershell/2004/04"><Obj S="progress"><S>Preparing modules</S></Obj></Objs>'
    assert not powershell_diagnostics(header+progress).strip()
    assert powershell_diagnostics(header+progress+'\nAccess denied').strip()=='Access denied'
    mixed=header+progress.replace('</Objs>','<S S="Error">Access denied</S></Objs>')
    assert 'Access denied' in powershell_diagnostics(mixed) and '#< CLIXML' in powershell_diagnostics(mixed)
    invalid=header+'<Objs><Obj S="progress">broken'
    assert powershell_diagnostics(invalid)==invalid
    dangerous=header+'<!DOCTYPE Objs><Objs><Obj S="progress" /></Objs>'
    assert powershell_diagnostics(dangerous)==dangerous

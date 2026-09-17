import importlib.util
import json
from pathlib import Path
import sys

import pytest

from engine.ssh import SSHCommandError


ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def apply_cli(tmp_path, monkeypatch):
    module = load_script("security_apply")
    inventory = tmp_path / "servers.csv"
    inventory.write_text("hostname,ip,os\nTEST,192.0.2.1,Linux\n", encoding="utf-8")
    plan = tmp_path / "plan.json"
    report = tmp_path / "report.json"
    record = {"hostname": "TEST", "ip": "192.0.2.1", "scope": "sshd_settings",
              "status": "action_required", "actions": [
                  {"type": "set_sshd_option", "parameter": "permitrootlogin", "current": "yes", "recommended": "no"},
                  {"type": "set_sshd_option", "parameter": "pubkeyauthentication", "current": "no", "recommended": "yes"},
              ]}
    args = ["security_apply", "--inventory", str(inventory), "--plan-file", str(plan),
            "--report-file", str(report), "--key-file", "unused-test-key"]
    monkeypatch.delenv("SM_AUTOMATION_SSH_PASSWORD", raising=False)
    def run(records=None, apply=False):
        plan.write_text(json.dumps([record] if records is None else records), encoding="utf-8")
        monkeypatch.setattr(sys, "argv", args + (["--apply"] if apply else []))
        return module.main()
    return module, run, report, record


def test_apply_prevalidates_all_records_before_connect(apply_cli, monkeypatch):
    module, run, report, record = apply_cli
    def forbidden(*args, **kwargs):
        pytest.fail("No connection may be opened for an invalid plan")
    monkeypatch.setattr(module, "SSHClient", forbidden)
    assert run([record, {**record, "ip": "192.0.2.2"}], apply=True) == 2
    assert not report.exists()


def test_dry_run_never_connects(apply_cli, monkeypatch):
    module, run, report, _ = apply_cli
    monkeypatch.setattr(module, "SSHClient", lambda *a, **k: pytest.fail("dry run connected"))
    assert run() == 0
    assert not report.exists()


def test_failed_batch_does_not_count_unattempted_actions_as_passed(apply_cli, monkeypatch, capsys):
    module, run, report, _ = apply_cli
    def failure(*args):
        raise SSHCommandError("simulated rollback")
    monkeypatch.setattr(module, "apply_sshd_settings", failure)
    assert run(apply=True) == 1
    assert "0 action(s) passed, 2 failed" in capsys.readouterr().out
    assert json.loads(report.read_text())[0]["status"] == "failed"


def test_compliance_cli_returns_nonzero_for_unimplemented_controls(tmp_path, monkeypatch, capsys):
    module = load_script("security_compliance")
    audit = tmp_path / "audit.json"
    audit.write_text('[{"status": "passed"}]', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["security_compliance", "--audit-report", str(audit),
                                    "--policy-file", str(ROOT / "config/security-policy-windows2022.json")])
    assert module.main() == 1
    assert "NOT_EVALUATED" in capsys.readouterr().out

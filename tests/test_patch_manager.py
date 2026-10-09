"""Test patch inputs and changed-plan rejection without invoking a package manager."""
import pytest
from patch import manager


@pytest.mark.parametrize("name", ["-y", "net-tools;id", "$(id)", "pkg=", "pkg=1\n2"])
def test_rejects_shell_options_and_invalid_specs(name):
    with pytest.raises(ValueError):
        manager.validate_options({"action": "plan", "packages": [name]})


def test_versions_and_architecture_are_allowed():
    assert manager.validate_options({"action": "plan", "packages": ["libssl3:amd64=3.0.1-1~ubuntu"]})["packages"]


def test_invalid_apply_id():
    with pytest.raises(ValueError):
        manager.validate_options({"action": "apply", "plan_id": "not-a-plan"})


def test_changed_plan_never_installs(monkeypatch):
    monkeypatch.setattr(manager, "package_manager", lambda client: "apt")
    monkeypatch.setattr(manager, "simulate", lambda *args: ([{"name": "changed"}], ""))
    monkeypatch.setattr(manager, "execute", lambda *args, **kwargs: pytest.fail("Install must not run"))
    with pytest.raises(ValueError, match="state changed"):
        manager.apply_plan(None, {"pins": ["net-tools=1"], "operations": []}, "direct")


def test_simulation_removal_rejected(monkeypatch):
    monkeypatch.setattr(manager, "execute", lambda *args: "Remv important-package [1]")
    with pytest.raises(ValueError, match="removals"):
        manager.simulate(None, ["net-tools=1"], "direct")


@pytest.mark.parametrize("planned,current", [("apt", "dnf"), ("dnf", "apt"), ("unknown", "apt")])
def test_changed_manager_never_simulates_or_installs(monkeypatch, planned, current):
    monkeypatch.setattr(manager, "package_manager", lambda client: current)
    monkeypatch.setattr(manager, "simulate", lambda *args: pytest.fail("Simulation must not run"))
    monkeypatch.setattr(manager, "execute", lambda *args, **kwargs: pytest.fail("Install must not run"))
    with pytest.raises(ValueError, match="manager changed"):
        manager.apply_plan(None, {"manager": planned}, "direct")

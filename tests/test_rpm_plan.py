"""Exercise dependency resolution boundaries without a Red Hat target."""
import sys
from types import ModuleType, SimpleNamespace
import pytest
from patch.rpm_plan import SCRIPT


def resolver(monkeypatch, unrelated_removal=False, no_changes=False):
    def package(name, version, repo):
        return SimpleNamespace(name=name, arch="x86_64", epoch=0, version=version, release="1",
                               evr=version + "-1", reponame=repo, chksum=(2, b"checksum") if repo != "@System" else None)
    old = package("pkg", "1", "@System"); new = package("pkg", "2", "repo")
    class Query:
        def __init__(self, values):
            self.values = values
        def installed(self):
            return Query([old])
        def available(self):
            return Query([] if no_changes else [new])
        def filter(self, **criteria):
            return Query([p for p in self.values if all(getattr(p, key) == value for key, value in criteria.items())])
        def upgrades(self):
            return self
        def latest(self):
            return self
        def __iter__(self):
            return iter(self.values)
    class Base:
        def __init__(self):
            self.conf = SimpleNamespace(read=lambda: None, substitutions={})
            self.repos = SimpleNamespace(iter_enabled=lambda: [])
            self.sack = SimpleNamespace(query=lambda: Query([old, new]))
            self.transaction = None
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read_all_repos(self):
            pass
        def fill_sack_from_repos_in_cache(self, **kwargs):
            assert self.conf.cacheonly is True
        def package_upgrade(self, pkg):
            assert pkg is new
        def resolve(self, allow_erasing):
            assert not allow_erasing
            if not no_changes:
                self.transaction = SimpleNamespace(install_set=[new], remove_set=[package("other", "1", "@System") if unrelated_removal else old])
        def do_transaction(self):
            pytest.fail("Planning must never apply a transaction")
        def download_packages(self, *args):
            pytest.fail("Planning must never download packages")
    dnf = ModuleType("dnf"); dnf.__path__ = []; dnf.Base = Base
    dnf.rpm = ModuleType("dnf.rpm"); dnf.rpm.detect_releasever = lambda _: "9"
    rpm = ModuleType("rpm"); rpm.labelCompare = lambda left, right: (left > right) - (left < right)
    monkeypatch.setitem(sys.modules, "dnf", dnf)
    monkeypatch.setitem(sys.modules, "dnf.rpm", dnf.rpm)
    monkeypatch.setitem(sys.modules, "rpm", rpm)
    scope = {}; exec(SCRIPT, scope)
    return scope["resolve"]


def test_rhel_plan_pins_versions_and_records_dependency_operations(monkeypatch):
    plan = resolver(monkeypatch)(["pkg:x86_64"])
    assert plan["pins"] == ["pkg:x86_64=2-1"]
    assert [item["action"] for item in plan["operations"]] == ["install", "replace_old"]
    assert not plan["apply_supported"]


def test_rhel_plan_rejects_unrelated_removal(monkeypatch):
    with pytest.raises(ValueError, match="removal"):
        resolver(monkeypatch, unrelated_removal=True)(["pkg"])


def test_empty_dnf_transaction_is_a_no_change_plan(monkeypatch):
    plan = resolver(monkeypatch, no_changes=True)(["pkg"])
    assert plan["operations"] == []
    assert plan["pins"] == ["pkg:x86_64=1-1"]

"""Check native DNF API in an isolated empty RPM root on local WSL only."""
import ast
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    if sys.platform != "linux" or os.geteuid() != 0 or "microsoft" not in Path("/proc/sys/kernel/osrelease").read_text().lower():
        raise RuntimeError("This check requires local WSL root and system Python DNF bindings")
    import dnf
    import dnf.rpm
    source = Path(__file__).resolve().parents[1] / "src/patch/rpm_plan.py"
    tree = ast.parse(source.read_text())
    script = next(ast.literal_eval(node.value) for node in tree.body
                  if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "SCRIPT" for target in node.targets))
    with tempfile.TemporaryDirectory(prefix="sm-native-dnf-", dir="/opt") as directory:
        path = Path(directory)
        root = path / "root"; root.mkdir()
        repos = path / "repos"; repos.mkdir()
        for name in ("cache", "persist", "logs"):
            (path / name).mkdir()
        subprocess.run(["rpm", "--root", str(root), "--initdb"], check=True)
        config = path / "dnf.conf"
        config.write_text(f"[main]\ninstallroot={root}\nreposdir={repos}\ncachedir={path}/cache\npersistdir={path}/persist\nlogdir={path}/logs\nplugins=0\n")
        original_base, original_release = dnf.Base, dnf.rpm.detect_releasever
        class IsolatedBase(original_base):
            def __init__(self):
                super().__init__()
                self.conf.config_file_path = str(config)
        dnf.Base = IsolatedBase
        dnf.rpm.detect_releasever = lambda _: "9"
        try:
            scope = {}; exec(script, scope)
            plan = scope["resolve"]([])
            assert plan["manager"] == "dnf" and plan["operations"] == []
            assert plan["pins"] == [] and plan["apply_supported"]
            applied = scope["resolve"]([], apply_plan=plan)
            assert applied["applied"] == 0
            try:
                scope["resolve"](["nonexistent-sm-fixture:x86_64"])
            except ValueError as exc:
                assert "Select one installed version" in str(exc)
            else:
                raise AssertionError("Missing RPM selection was accepted")
            print("PASS: native DNF configuration, cached sack, empty transaction plan/apply and missing-package rejection")
            print("All RPM state was isolated under a temporary /opt root; no packages installed through RPM")
        finally:
            dnf.Base, dnf.rpm.detect_releasever = original_base, original_release


if __name__ == "__main__":
    main()

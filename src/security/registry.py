from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_POLICY_FILES = {
    ("rhel", "8"): "security-policy-rhel8.json",
    ("rhel", "9"): "security-policy-rhel9.json",
    ("aix", "7.1"): "security-policy-aix7.1.json",
    ("windows", "2022"): "security-policy-windows2022.json",
}


class PolicyRegistryError(ValueError):
    """Raised when an OS/version policy cannot be selected or loaded."""


def policy_path_for(
    os_name: str,
    version: str,
    config_dir: str | Path,
) -> Path:
    """Resolve the approved policy file for one OS and version."""
    key = (os_name.strip().lower(), version.strip().lower())
    filename = _POLICY_FILES.get(key)
    if filename is None:
        supported = ", ".join(f"{name} {release}" for name, release in _POLICY_FILES)
        raise PolicyRegistryError(f"Unsupported OS/version: {os_name} {version}. Supported: {supported}")
    return Path(config_dir).resolve() / filename


def load_policy(path: str | Path) -> dict[str, Any]:
    """Load one policy JSON object from disk."""
    policy_path = Path(path)
    try:
        data = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise PolicyRegistryError(f"Cannot load policy file: {policy_path}") from exc
    if not isinstance(data, dict):
        raise PolicyRegistryError("Policy file must contain a JSON object.")
    return data

"""Reject stale SSH policy observations, including no-change plans."""


def verify_observations(expected, actual):
    for key in ("sshd_settings", "sshd_config_mode", "root_accounts"):
        if key not in expected or key not in actual:
            raise ValueError("Incomplete SSH observations; create a new plan")
        before, after = expected[key], actual[key]
        if key == "root_accounts":
            before, after = sorted(before), sorted(after)
        if before != after:
            raise ValueError("SSH observations changed since planning; create a new plan")

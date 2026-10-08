"""Present Linux audit observations without changing target policies."""


def audit_rows(rows):
    output = []
    for host in rows:
        name = host["hostname"]
        if host["status"] != "completed":
            output.append([name, "Collection", host.get("error", host["status"]), "Unavailable"])
            continue
        result = host["result"]
        roots = result.get("root_accounts", [])
        output.append([name, "UID 0 accounts", ", ".join(roots), "OK" if roots == ["root"] or roots == ("root",) else "Review"])
        settings = result.get("sshd_settings", {})
        for key, preferred in [("permitrootlogin", {"no", "prohibit-password", "without-password"}), ("passwordauthentication", {"no"}), ("pubkeyauthentication", {"yes"})]:
            value = settings.get(key, "Not collected")
            output.append([name, key, value, "OK" if value in preferred else "Review"])
        mode = result.get("sshd_config_mode", "Not collected")
        output.append([name, "SSH config mode / owner", mode, "Observed"])
    return output

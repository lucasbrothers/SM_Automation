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


def plan_rows(rows):
    """Show actionable changes and blocking reasons without raw job JSON."""
    output = []
    for host in rows:
        name = host["hostname"]
        result = host.get("result", {})
        plan = result.get("plan", {})
        if host.get("status") != "completed":
            output.append([name, "Collection", "", "", host.get("error", host.get("status", "Unavailable"))])
            continue
        actions = plan.get("actions", [])
        if not actions:
            output.append([name, "SSH policy", "Already satisfied" if plan.get("status") == "no_changes" else "Unavailable", "No change", plan.get("status", "Unavailable")])
        for action in actions:
            output.append([name, action["parameter"], action.get("current", ""), action.get("recommended", ""), plan.get("status", "Unavailable")])
        for reason in plan.get("reasons", []):
            output.append([name, "Reason", "", "", reason])
        adapter = result.get("adapter", {})
        if adapter:
            output.append([name, "Configuration support", "", "", adapter.get("reason", "Unavailable")])
    return output

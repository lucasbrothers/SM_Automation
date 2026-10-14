"""Application login accounts; passwords are salted hashes, never plaintext."""
import hashlib
import hmac
import os
import re
import time
import threading
_cache = {}
_cache_lock = threading.Lock()
_cache_key = os.urandom(32)

def password_hash(password, salt):
    return hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()

def save_account(store, username, password, role=None):
    if not isinstance(username, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", username):
        raise ValueError("ID must use 1–64 letters, digits, dots, underscores or hyphens")
    if not isinstance(password, str) or len(password) > 1024:
        raise ValueError("Enter a password up to 1024 characters")
    accounts = store.read_json("gui-accounts.json.enc", {})
    if not password and username not in accounts: raise ValueError("New accounts require a password")
    selected_role = role if role is not None else accounts.get(username, {}).get("role", "admin")
    if selected_role not in {"admin", "operator", "viewer"}: raise ValueError("Unknown account role")
    if username in accounts and accounts[username].get("role", "admin") == "admin" and selected_role != "admin":
        if not any(name != username and account.get("role", "admin") == "admin" for name, account in accounts.items()):
            raise ValueError("Keep at least one administrator")
    salt = os.urandom(16).hex()
    accounts[username] = ({"salt": salt, "hash": password_hash(password, salt), "role": selected_role} if password else {**accounts[username], "role": selected_role})
    store.write_json("gui-accounts.json.enc", accounts)
    return {"id": username}

def authenticate(store, username, password):
    if not isinstance(username, str) or not isinstance(password, str) or len(username) > 64 or len(password) > 1024:
        return False
    account = store.read_json("gui-accounts.json.enc", {}).get(username)
    salt = account["salt"] if account else "00" * 16
    stamp=hmac.new(_cache_key,(str(store.root)+"\0"+username+"\0"+str(account)+"\0"+password).encode(),hashlib.sha256).digest()
    with _cache_lock:
        if _cache.get(stamp,0)>time.monotonic():return True
    value = password_hash(password, salt)
    valid=bool(account) and hmac.compare_digest(value, account["hash"])
    if valid:
        with _cache_lock:
            if len(_cache)>=128:_cache.pop(next(iter(_cache)))
            _cache[stamp]=time.monotonic()+60
    return valid


def role_for(store, username):
    account = store.read_json("gui-accounts.json.enc", {}).get(username)
    if not account: raise ValueError("Account no longer exists")
    role = account.get("role", "admin")
    if role not in {"admin", "operator", "viewer"}: raise ValueError("Invalid account role")
    return role


def authorize(role, method, params):
    if role == "admin": return
    read = {"session.info", "ci.list", "equipment.book.list", "status", "inventory.list", "ssh.profiles", "job.list", "job.get", "job.result", "command.saved.list", "file.list", "file.stat", "file.pending", "file.download", "schedule.list"}
    if role in {"operator", "viewer"} and method.startswith("file."):
        from pathlib import Path
        root = Path("/srv/sm-automation/shared").resolve()
        for field in ("path", "target"):
            if field in params:
                value = params[field]
                if not isinstance(value, str) or not value.startswith("/") or not Path(value).resolve().is_relative_to(root):
                    raise ValueError("Permission denied: use /srv/sm-automation/shared")
    if role in {"operator", "viewer"} and method in read: return
    if role == "operator":
        if method in {"command.saved.save", "command.saved.delete", "file.mkdir", "file.upload", "file.commit", "file.abort", "job.cancel"}: return
        if method == "job.start":
            if params.get("kind") in {"connections", "monitoring", "ci_inventory"}: return
            if params.get("kind") == "accounts" and params.get("options", {}).get("action", "list") == "list": return
    raise ValueError("Permission denied: " + method + " requires a higher role")

"""Application login accounts; passwords are salted hashes, never plaintext."""
import hashlib
import hmac
import os
import re

def password_hash(password, salt):
    return hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()

def save_account(store, username, password):
    if not isinstance(username, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", username):
        raise ValueError("ID must use 1–64 letters, digits, dots, underscores or hyphens")
    if not isinstance(password, str) or not password or len(password) > 1024:
        raise ValueError("Enter a password up to 1024 characters")
    accounts = store.read_json("gui-accounts.json.enc", {})
    salt = os.urandom(16).hex()
    accounts[username] = {"salt": salt, "hash": password_hash(password, salt)}
    store.write_json("gui-accounts.json.enc", accounts)
    return {"id": username}

def authenticate(store, username, password):
    if not isinstance(username, str) or not isinstance(password, str) or len(username) > 64 or len(password) > 1024:
        return False
    account = store.read_json("gui-accounts.json.enc", {}).get(username)
    salt = account["salt"] if account else "00" * 16
    value = password_hash(password, salt)
    return bool(account) and hmac.compare_digest(value, account["hash"])

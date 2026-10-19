"""Separate password-free loopback UI from optional phone access."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from pathlib import Path

SETTINGS = Path(__file__).resolve().parent / "access.json"
MODES = {"This PC only": "local", "My Wi-Fi": "lan", "Temporary phone link": "public"}


def load() -> dict:
    if not SETTINGS.is_file():
        return {"mode": "local", "username": "", "salt": "", "hash": ""}
    data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    if data.get("mode") not in MODES.values():
        raise ValueError("Invalid phone access settings")
    if any(not isinstance(data.get(key), str) for key in ("username", "salt", "hash")):
        raise ValueError("Invalid phone access settings")
    return data


def save(label: str, username: str, password: str) -> str:
    if label not in MODES:
        raise ValueError("Choose a phone access mode")
    username = (username or "").strip()
    password = password or ""
    if len(username) > 64 or any(ord(c) < 32 for c in username):
        raise ValueError("Username is invalid")
    data = {"mode": MODES[label], "username": "", "salt": "", "hash": ""}
    if data["mode"] != "local" and password:
        data["username"] = username or "ggf"
        data["salt"] = secrets.token_hex(16)
        data["hash"] = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(data["salt"]), 600_000).hex()
    SETTINGS.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return "Saved. Restart RUN.bat to apply phone access changes."


def verify(username: str, password: str, data: dict) -> bool:
    if not data["hash"]:
        return True
    if not username or not password:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(data["salt"]), 600_000).hex()
    return hmac.compare_digest(username, data["username"]) and hmac.compare_digest(digest, data["hash"])

"""Session login for the device control panel."""

from __future__ import annotations

import secrets
from functools import wraps
from pathlib import Path

from flask import jsonify, redirect, request, session, url_for

from ..config import DATA_DIR, TUNABLES

SECRET_PATH = DATA_DIR / "web_secret.txt"


def session_secret() -> str:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not SECRET_PATH.exists():
        SECRET_PATH.write_text(secrets.token_hex(32))
    return SECRET_PATH.read_text().strip()


def verify_credentials(username: str, password: str) -> bool:
    return (
        username == TUNABLES.web_username
        and password == TUNABLES.web_password
    )


def is_authenticated() -> bool:
    return bool(session.get("authenticated"))


def login_user(username: str) -> None:
    session["authenticated"] = True
    session["username"] = username


def logout_user() -> None:
    session.clear()


def require_login(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if is_authenticated():
            return view(*args, **kwargs)
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "login_required"}), 401
        return redirect(url_for("login_page", next=request.path))

    return wrapped

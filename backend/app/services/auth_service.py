"""Player accounts: username + password, opaque session tokens.

Standard library only:
- Passwords are hashed with scrypt and a per-user random salt; never stored or logged.
- A session token is random; only its SHA-256 hash is stored, so a leaked
  database does not leak usable tokens.

Known limits (acceptable for a hackathon demo, not for production):
no rate limiting on login, no password reset, no email verification.
Serve over HTTPS when deployed.
"""

import hashlib
import hmac
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.app.errors import ApiError
from backend.app.schemas import AuthResponse, User
from backend.app.storage.db import Database, now_iso

_SCRYPT = dict(n=2**14, r=8, p=1, dklen=32)
# The hosted game runs this code in the browser (Pyodide), whose hashlib has neither scrypt nor
# pbkdf2_hmac. There, passwords use PBKDF2-HMAC-SHA256 written below with hashlib.sha256 (standard
# algorithm, RFC 8018), tagged "pbkdf2$" so a hash always verifies with the method that made it.
# That database never leaves the player's browser.
_PBKDF2_ITERATIONS = 20_000
_PBKDF2_TAG = "pbkdf2$"


def _pbkdf2_sha256(password: bytes, salt: bytes, iterations: int, dklen: int = 32) -> bytes:
    key = hashlib.sha256(password).digest() if len(password) > 64 else password
    key = key.ljust(64, b"\0")
    inner, outer = hashlib.sha256(bytes(x ^ 0x36 for x in key)), hashlib.sha256(bytes(x ^ 0x5C for x in key))

    def prf(msg: bytes) -> bytes:
        i = inner.copy()
        i.update(msg)
        o = outer.copy()
        o.update(i.digest())
        return o.digest()

    u = prf(salt + b"\x00\x00\x00\x01")
    acc = int.from_bytes(u, "big")
    for _ in range(iterations - 1):
        u = prf(u)
        acc ^= int.from_bytes(u, "big")
    return acc.to_bytes(32, "big")[:dklen]


def _hash_password(password: str, salt: bytes, stored: Optional[str] = None) -> str:
    use_pbkdf2 = stored.startswith(_PBKDF2_TAG) if stored else not hasattr(hashlib, "scrypt")
    if use_pbkdf2:
        return _PBKDF2_TAG + _pbkdf2_sha256(password.encode("utf-8"), salt, _PBKDF2_ITERATIONS).hex()
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, **_SCRYPT).hex()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthService:
    def __init__(self, db: Database, session_ttl_hours: int = 24 * 7) -> None:
        self.db = db
        self.ttl = timedelta(hours=session_ttl_hours)

    # -- accounts ------------------------------------------------------------

    def register(self, username: str, password: str) -> AuthResponse:
        username = username.strip().lower()
        salt = secrets.token_bytes(16)
        user = User(id=uuid.uuid4().hex, username=username, created_at=now_iso())
        try:
            self.db.execute(
                "INSERT INTO users (id, username, password_hash, salt, created_at) VALUES (?, ?, ?, ?, ?)",
                (user.id, user.username, _hash_password(password, salt), salt.hex(), user.created_at),
            )
        except sqlite3.IntegrityError:
            raise ApiError(409, "username_taken", "That username is already taken.", field="username")
        return self._open_session(user)

    def login(self, username: str, password: str) -> AuthResponse:
        username = username.strip().lower()
        row = self.db.query_one("SELECT * FROM users WHERE username = ?", (username,))
        # Hash even when the user is unknown so both cases take the same time.
        salt = bytes.fromhex(row["salt"]) if row else b"\x00" * 16
        candidate = _hash_password(password, salt, row["password_hash"] if row else None)
        if row is None or not hmac.compare_digest(candidate, row["password_hash"]):
            raise ApiError(401, "invalid_credentials", "Wrong username or password.")
        return self._open_session(User(id=row["id"], username=row["username"], created_at=row["created_at"]))

    # -- sessions ------------------------------------------------------------

    def _open_session(self, user: User) -> AuthResponse:
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now(timezone.utc) + self.ttl).isoformat(timespec="seconds")
        self.db.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (_hash_token(token), user.id, now_iso(), expires_at),
        )
        return AuthResponse(token=token, expires_at=expires_at, user=user)

    def user_for_token(self, token: str) -> Optional[User]:
        row = self.db.query_one(
            "SELECT u.id, u.username, u.created_at, s.expires_at "
            "FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?",
            (_hash_token(token),),
        )
        if row is None:
            return None
        if datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc):
            self.logout(token)
            return None
        return User(id=row["id"], username=row["username"], created_at=row["created_at"])

    def logout(self, token: str) -> None:
        self.db.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash_token(token),))

"""SQLite-backed user and session store for the web UI."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class User:
    id: str
    email: str
    role: str
    created_at: datetime

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "role": self.role,
            "created_at": self.created_at.isoformat(),
        }


class UserStore:
    def __init__(self, persist_dir: Path) -> None:
        self._db_path = persist_dir / "users.sqlite3"
        self._lock = threading.Lock()

    def _ensure_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")

    @staticmethod
    def _normalize_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def _hash_password(password: str, salt: bytes | None = None) -> str:
        salt = salt or os.urandom(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
        return f"pbkdf2_sha256${salt.hex()}${digest.hex()}"

    @staticmethod
    def _verify_password(password: str, stored: str) -> bool:
        try:
            algorithm, salt_hex, digest_hex = stored.split("$", 2)
            if algorithm != "pbkdf2_sha256":
                return False
            expected = UserStore._hash_password(password, bytes.fromhex(salt_hex))
            return hmac.compare_digest(expected, stored)
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _row_to_user(row: sqlite3.Row) -> User:
        return User(
            id=row["id"],
            email=row["email"],
            role=row["role"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def create_user(self, email: str, password: str, role: str = "user") -> User:
        email = self._normalize_email(email)
        if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            raise ValueError("invalid_email")
        if len(password) < 8:
            raise ValueError("weak_password")
        if role not in {"user", "admin"}:
            raise ValueError("invalid_role")

        self._ensure_db()
        created_at = datetime.now(timezone.utc).isoformat()
        user_id = str(uuid.uuid4())
        with self._lock, sqlite3.connect(self._db_path) as con:
            try:
                con.execute(
                    """
                    INSERT INTO users (id, email, password_hash, role, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (user_id, email, self._hash_password(password), role, created_at),
                )
            except sqlite3.IntegrityError:
                raise ValueError("email_exists")
        return User(user_id, email, role, datetime.fromisoformat(created_at))

    def authenticate(self, email: str, password: str) -> User | None:
        email = self._normalize_email(email)
        self._ensure_db()
        with sqlite3.connect(self._db_path) as con:
            con.row_factory = sqlite3.Row
            row = con.execute(
                "SELECT * FROM users WHERE email = ?",
                (email,),
            ).fetchone()
        if row is None or not self._verify_password(password, row["password_hash"]):
            return None
        return self._row_to_user(row)

    def create_session(self, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        self._ensure_db()
        with self._lock, sqlite3.connect(self._db_path) as con:
            con.execute(
                """
                INSERT INTO sessions (token_hash, user_id, created_at)
                VALUES (?, ?, ?)
                """,
                (
                    self._hash_token(token),
                    user_id,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        return token

    def get_user_by_token(self, token: str) -> User | None:
        if not token:
            return None
        self._ensure_db()
        with sqlite3.connect(self._db_path) as con:
            con.row_factory = sqlite3.Row
            row = con.execute(
                """
                SELECT users.*
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_hash = ?
                """,
                (self._hash_token(token),),
            ).fetchone()
        return self._row_to_user(row) if row is not None else None

    def revoke_session(self, token: str) -> None:
        if not token:
            return
        self._ensure_db()
        with self._lock, sqlite3.connect(self._db_path) as con:
            con.execute("DELETE FROM sessions WHERE token_hash = ?", (self._hash_token(token),))

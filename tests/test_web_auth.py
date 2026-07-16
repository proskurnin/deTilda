from __future__ import annotations

import pytest

from web.auth import UserStore


def test_user_store_registers_and_authenticates_user(tmp_path) -> None:
    store = UserStore(tmp_path)

    user = store.create_user("Owner@Example.com", "strong-pass-123")
    token = store.create_session(user.id)

    assert user.email == "owner@example.com"
    assert user.role == "user"
    assert store.authenticate("owner@example.com", "strong-pass-123") == user
    assert store.authenticate("owner@example.com", "wrong") is None
    assert store.get_user_by_token(token) == user


def test_user_store_rejects_duplicate_email(tmp_path) -> None:
    store = UserStore(tmp_path)
    store.create_user("owner@example.com", "strong-pass-123")

    with pytest.raises(ValueError, match="email_exists"):
        store.create_user("OWNER@example.com", "strong-pass-123")


def test_user_store_revoke_session(tmp_path) -> None:
    store = UserStore(tmp_path)
    user = store.create_user("owner@example.com", "strong-pass-123")
    token = store.create_session(user.id)

    store.revoke_session(token)

    assert store.get_user_by_token(token) is None

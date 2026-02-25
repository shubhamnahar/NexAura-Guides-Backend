import os
import pytest

# Mock environment variables before importing app.auth
os.environ["SECRET_KEY"] = "test_secret_key"
os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost:5432/db"

from app.auth import get_password_hash, verify_password, _prepare_password

def test_password_hashing():
    password = "my_very_long_password_that_is_more_than_72_characters_long_012345678901234567890123456789"
    hashed = get_password_hash(password)

    assert verify_password(password, hashed) is True
    assert verify_password("wrong_password", hashed) is False

def test_password_truncation_bypass():
    # If SHA-256 pre-hashing is working, passwords differing after 72 chars should still be distinct
    pass1 = "a" * 72 + "b"
    pass2 = "a" * 72 + "c"

    hashed1 = get_password_hash(pass1)
    assert verify_password(pass2, hashed1) is False
    assert verify_password(pass1, hashed1) is True

def test_prepare_password():
    password = "test"
    prepared = _prepare_password(password)
    # SHA-256 of "test"
    import hashlib
    expected = hashlib.sha256(password.encode()).hexdigest()
    assert prepared == expected

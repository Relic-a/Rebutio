import pytest
from backend.app.services.privacy.encryption import DataEncryptor


def test_encryption_roundtrip_string():
    enc = DataEncryptor()
    text = "User speech transcript with sensitive thoughts"
    encrypted = enc.encrypt_str(text)
    assert encrypted.startswith("v1:")
    assert encrypted != text

    decrypted = enc.decrypt_str(encrypted)
    assert decrypted == text


def test_encryption_roundtrip_json():
    enc = DataEncryptor()
    data = {
        "phonemes": [{"phone": "th", "start_ms": 100, "end_ms": 200}],
        "summary": "Clear speaker",
        "score": 85,
    }
    encrypted = enc.encrypt_json(data)
    assert encrypted.startswith("v1:")

    decrypted = enc.decrypt_json(encrypted)
    assert decrypted == data


def test_encryption_handles_none_and_corrupt():
    enc = DataEncryptor()
    assert enc.encrypt_str(None) is None
    assert enc.decrypt_str(None) is None
    assert enc.decrypt_str("corrupted-payload") == "corrupted-payload"
    assert enc.decrypt_json("v1:invalid:payload") is None

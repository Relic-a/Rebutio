import base64
import hashlib
import json
import os
from typing import Any, Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from backend.app.config import settings
from backend.app.observability.logging import get_logger

logger = get_logger("rebutio.encryption")


class DataEncryptor:
    def __init__(self, key_str: Optional[str] = None):
        raw_key = key_str or settings.REBUTIO_DATA_ENCRYPTION_KEY
        self._key = self._derive_32byte_key(raw_key)
        self._aesgcm = AESGCM(self._key)

    @staticmethod
    def _derive_32byte_key(key_input: str) -> bytes:
        if not key_input:
            key_input = "default-dev-encryption-key-rebutio-32b"
        try:
            # Try hex
            if len(key_input) == 64:
                return bytes.fromhex(key_input)
        except Exception:
            pass
        try:
            # Try base64
            decoded = base64.urlsafe_b64decode(key_input.encode())
            if len(decoded) == 32:
                return decoded
        except Exception:
            pass
        # Fallback: sha256 hash
        return hashlib.sha256(key_input.encode("utf-8")).digest()

    def encrypt_str(self, plaintext: Optional[str], payload_type: str = "string") -> Optional[str]:
        if plaintext is None:
            return None
        if not isinstance(plaintext, str):
            plaintext = str(plaintext)
        
        try:
            nonce = os.urandom(12)
            ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
            
            nonce_b64 = base64.urlsafe_b64encode(nonce).decode("ascii")
            ct_b64 = base64.urlsafe_b64encode(ciphertext).decode("ascii")
            return f"v1:{nonce_b64}:{ct_b64}"
        except Exception as e:
            logger.error(
                "encryption.failed",
                operation="encrypt",
                payload_type=payload_type,
                exception_type=e.__class__.__name__,
            )
            return None

    def decrypt_str(self, encrypted_payload: Optional[str], payload_type: str = "string") -> Optional[str]:
        if not encrypted_payload:
            return None
        
        if not encrypted_payload.startswith("v1:"):
            # Plaintext or unknown version fallback
            return encrypted_payload

        parts = encrypted_payload.split(":")
        if len(parts) != 3:
            logger.error(
                "encryption.failed",
                operation="decrypt",
                payload_type=payload_type,
                reason="malformed_payload_format",
            )
            return None

        _, nonce_b64, ct_b64 = parts
        try:
            nonce = base64.urlsafe_b64decode(nonce_b64.encode("ascii"))
            ciphertext = base64.urlsafe_b64decode(ct_b64.encode("ascii"))
            decrypted = self._aesgcm.decrypt(nonce, ciphertext, None)
            return decrypted.decode("utf-8")
        except Exception as e:
            logger.error(
                "encryption.failed",
                operation="decrypt",
                payload_type=payload_type,
                exception_type=e.__class__.__name__,
            )
            return None

    def encrypt_json(self, data: Any, payload_type: str = "json") -> Optional[str]:
        if data is None:
            return None
        try:
            serialized = json.dumps(data)
            return self.encrypt_str(serialized, payload_type=payload_type)
        except Exception as e:
            logger.error(
                "encryption.failed",
                operation="encrypt_json",
                payload_type=payload_type,
                exception_type=e.__class__.__name__,
            )
            return None

    def decrypt_json(self, encrypted_payload: Optional[str], payload_type: str = "json") -> Any:
        decrypted_str = self.decrypt_str(encrypted_payload, payload_type=payload_type)
        if decrypted_str is None:
            return None
        try:
            return json.loads(decrypted_str)
        except Exception as e:
            logger.error(
                "encryption.failed",
                operation="decrypt_json",
                payload_type=payload_type,
                exception_type=e.__class__.__name__,
            )
            return None


# Global singleton instance
encryptor = DataEncryptor()

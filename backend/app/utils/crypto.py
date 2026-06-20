"""AES-256-GCM encryption for face embeddings at rest."""
import os

import numpy as np
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def _derive_key(secret: str) -> bytes:
    """Derive 32-byte key from SECRET_KEY via HKDF-SHA256."""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"wl-face-emb",
    )
    return hkdf.derive(secret.encode())


def encrypt_embedding(embedding: np.ndarray, secret: str) -> bytes:
    """Encrypt float32[512] embedding. Returns nonce(12) + ciphertext(2048) + tag(16) = 2076 bytes."""
    key = _derive_key(secret)
    raw = embedding.astype(np.float32).tobytes()  # 2048 bytes
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ct_and_tag = aesgcm.encrypt(nonce, raw, None)  # AESGCM.encrypt returns ct+tag
    return nonce + ct_and_tag


def decrypt_embedding(data: bytes, secret: str) -> np.ndarray:
    """Decrypt stored bytes back to float32[512] numpy array."""
    key = _derive_key(secret)
    nonce = data[:12]
    ct_and_tag = data[12:]
    aesgcm = AESGCM(key)
    raw = aesgcm.decrypt(nonce, ct_and_tag, None)
    return np.frombuffer(raw, dtype=np.float32)

"""Validation + at-rest encryption for Case/Client/Debtor attachments.

Only PDF and XLSX are accepted. What actually lands in storage (local disk
in dev, R2 in production) is gzip-compressed then Fernet-encrypted — never
the original bytes. Viewing/downloading goes through a small proxy view
that reads the encrypted blob and decrypts it in memory before handing it
back; nothing decrypted ever touches disk or the storage bucket.

This trades one real risk for another: lose ATTACHMENT_ENCRYPTION_KEY and
every attachment ever uploaded becomes permanently unreadable — there is
no recovery path, encrypted bytes without the key are just noise. Back the
key up the same deliberate way as the database itself (see Settings ->
Backup & Export): the moment this key is generated, save a copy of it
somewhere durable that isn't just this one Railway variable.
"""
import gzip
import os

from django.core.exceptions import ImproperlyConfigured

ALLOWED_EXTENSIONS = {'.pdf', '.xlsx'}

# Enough of each format's real signature to catch "renamed .exe to .pdf"
# without being a full parser. xlsx is a zip container (PK\x03\x04); real
# xlsx files may also start with PK\x05\x06 (empty archive) or PK\x07\x08
# (spanned), so all three are accepted.
_SIGNATURES = {
    '.pdf': (b'%PDF',),
    '.xlsx': (b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08'),
}

CONTENT_TYPES = {
    '.pdf': 'application/pdf',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
}


def validate_attachment_file(f):
    """None if f is an acceptable upload; otherwise a user-facing error
    string. Reads only a small header off the front of the file and
    rewinds — safe to call before the file is otherwise consumed."""
    name = getattr(f, 'name', '') or ''
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ', '.join(sorted(e.lstrip('.').upper() for e in ALLOWED_EXTENSIONS))
        shown = ext.lstrip('.').upper() if ext else 'unknown'
        return f'"{shown}" files are not allowed. Allowed formats: {allowed}.'

    head = f.read(8)
    f.seek(0)
    if not any(head.startswith(sig) for sig in _SIGNATURES[ext]):
        return (f'This file doesn\'t look like a real {ext.lstrip(".").upper()} '
                f'file (its content doesn\'t match a {ext.lstrip(".").upper()} '
                f'header) — it may have just been renamed.')
    return None


def _fernet():
    from cryptography.fernet import Fernet
    from django.conf import settings

    key = getattr(settings, 'ATTACHMENT_ENCRYPTION_KEY', '') or ''
    if not key:
        raise ImproperlyConfigured(
            'ATTACHMENT_ENCRYPTION_KEY is not set — cannot encrypt or decrypt '
            'attachments. Generate one with: '
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_bytes(data: bytes) -> bytes:
    return _fernet().encrypt(gzip.compress(data))


def decrypt_bytes(data: bytes) -> bytes:
    return gzip.decompress(_fernet().decrypt(data))

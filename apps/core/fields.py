"""Encrypted model field for sensitive values (PAN, bank account numbers).

Uses Fernet (AES-128-CBC + HMAC). The key comes from FIELD_ENCRYPTION_KEY; in development it is
derived from SECRET_KEY. Rotate by adding a new key to the front of FIELD_ENCRYPTION_KEYS.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.db import models


def _fernet():
    keys = getattr(settings, "FIELD_ENCRYPTION_KEYS", None) or []
    if not keys:
        digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        keys = [base64.urlsafe_b64encode(digest).decode()]
    return MultiFernet([Fernet(k) for k in keys])


class EncryptedTextField(models.TextField):
    def from_db_value(self, value, expression, connection):
        if value in (None, ""):
            return value
        try:
            return _fernet().decrypt(value.encode()).decode()
        except InvalidToken:
            return None

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value in (None, ""):
            return value
        return _fernet().encrypt(str(value).encode()).decode()

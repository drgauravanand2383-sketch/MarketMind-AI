"""Secure secret loading.

`AuthSettings.secret_key` (`app.config.models`) is a `pydantic.SecretStr`
— its value never appears in a `repr()`, a log line, or an accidental
`str()` of the settings object. `load_jwt_secret` is the single place in
this entire framework `.get_secret_value()` is ever called on it; every
other module that needs the raw secret receives it already-unwrapped,
constructed once at bootstrap (`app.bootstrap.build_jwt_signer`) — never
re-reads `AuthSettings` or re-unwraps the secret itself.
"""

from __future__ import annotations

from app.config.models import AuthSettings

__all__ = ["load_jwt_secret"]


def load_jwt_secret(settings: AuthSettings) -> str:
    return settings.secret_key.get_secret_value()

"""Server-side single-user session auth.

Login credentials come from the dashboard env (/opt/data/.env):
  DASHBOARD_USERNAME / DASHBOARD_PASSWORD
Sessions are in-memory tokens issued as an httpOnly cookie after a correct
login, validated by middleware on /api/* (except /api/login). A restart to
the container invalidates all sessions, which is acceptable for this
single-user private-NAS dashboard.
"""
import hmac
import secrets
import time

try:
    from . import config
except ImportError:  # direct script run
    import config  # noqa: F401

_SESSIONS = {}          # token -> expiry epoch
_SESSION_TTL = 7 * 24 * 3600   # 7 days
COOKIE = "sdb_session"


def _creds():
    try:
        return config.settings.DASHBOARD_USERNAME, config.settings.DASHBOARD_PASSWORD
    except AttributeError:
        return "", ""


def enabled():
    """True only when the owner has configured credentials in .env."""
    u, p = _creds()
    return bool(u and p)


def verify_login(username, password):
    """Constant-time compare against env credentials."""
    if not enabled():
        return False
    u, p = _creds()
    return bool(hmac.compare_digest(username or "", u) and
                hmac.compare_digest(password or "", p))


def _now():
    return time.time()


def create_session(max_age=_SESSION_TTL):
    """Issue a fresh token; returns (token, lifetime_seconds)."""
    token = secrets.token_urlsafe(32)
    _SESSIONS[token] = _now() + max_age
    return token, max_age


def validate(token):
    if not token:
        return False
    exp = _SESSIONS.get(token)
    if not exp:
        return False
    if exp < _now():
        _SESSIONS.pop(token, None)
        return False
    return True


def revoke(token):
    if token:
        _SESSIONS.pop(token, None)
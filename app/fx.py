"""Real-time USD->KRW exchange rate module.

Source: .env EXCHANGE_RATE_API_URL (or FX_BASE_URL); default open.er-api.com/v6/latest/USD.
In-memory TTL cache (1h). Persist to fx_rates on success.
Fallback chain: cached -> fx_rates DB latest -> safe default.
"""
import json
import os
import threading
import time

import requests

try:
    from . import db
except ImportError:  # direct script run
    import db

# Safe fallback (only when cache/db/network all fail)
FALLBACK_RATE = 1350.0
_TTL_SECONDS = 3600
_DEFAULT_URL = "https://open.er-api.com/v6/latest/USD"

_cache = {"rate": None, "ts": 0.0}
_lock = threading.Lock()


def _strip_env(v):
    return (v or "").strip().strip("[]").strip("'\"")


def _load_url():
    for k in ("EXCHANGE_RATE_API_URL", "FX_BASE_URL"):
        u = _strip_env(os.getenv(k))
        if u:
            return u
    return _DEFAULT_URL


def _to_float(v):
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _parse_rate(payload):
    if isinstance(payload, list):
        for it in payload:
            if isinstance(it, dict):
                r = _parse_rate(it)
                if r:
                    return r
        return None
    if not isinstance(payload, dict):
        return None
    rates = payload.get("rates")
    if isinstance(rates, dict):
        krw = rates.get("KRW")
        if krw is not None:
            r = _to_float(krw)
            if r:
                return r
    for k in ("basePrice", "price", "value", "lastPrice", "dealBaseRate", "oprc", "currentPrice"):
        v = payload.get(k)
        if v is not None and not isinstance(v, (dict, list)):
            r = _to_float(v)
            if r:
                return r
    return None


def _persist(rate):
    try:
        now_s = time.strftime("%Y-%m-%d %H:%M:%S")
        conn = db.get_connection()
        try:
            conn.execute(
                "INSERT INTO fx_rates(pair, rate, source, fetched_at) VALUES (?,,?,,?,,?)",
                ("USDKRW", float(rate), "realtime", now_s)
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def get_usd_krw(force_refresh=False):
    now = time.time()
    with _lock:
        if not force_refresh and _cache["rate"] is not None and (now - _cache["ts"] < _TTL_SECONDS):
            return _cache["rate"]

    url = _load_url()
    rate = None
    try:
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        rate = _parse_rate(r.json())
    except Exception:
        rate = None

    if rate is not None:
        with _lock:
            _cache["rate"] = rate
            _cache["ts"] = now
        _persist(rate)
        return rate

    with _lock:
        if _cache["rate"] is not None:
            return _cache["rate"]

    try:
        conn = db.get_connection()
        try:
            row = conn.execute(
                "SELECT rate FROM fx_rates WHERE pair='USDKRW' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if row and row["rate"]:
                return float(row["rate"])
        finally:
            conn.close()
    except Exception:
        pass
    return FALLBACK_RATE


def get_fx_summary():
    r = get_usd_krw()
    ts = _cache["ts"]
    return {
        "rate": r,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else None,
    }


if __name__ == "__main__":
    r = get_usd_krw(force_refresh=True)
    print(json.dumps({"rate": r, "summary": get_fx_summary()}, ensure_ascii=False, indent=2))
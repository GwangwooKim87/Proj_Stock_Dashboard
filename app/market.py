"""주요 증시 지수 실시간 조회 모듈 (네이버 금융 폴링 API, 무료·키 없음).

fx.py와 동일한 패턴: 인메모리 TTL 캐시(1h) + 실패 시 마지막 캐시로 폴백.
"""
import json
import threading
import time

import requests

_TTL_SECONDS = 3600
_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.naver.com"}
_DOMESTIC_URL = "https://polling.finance.naver.com/api/realtime/domestic/index/KOSPI,KOSDAQ"
_WORLD_URL = "https://polling.finance.naver.com/api/realtime/worldstock/index/.IXIC,.INX,.DJI,.SOX"

# 나스닥 선물은 네이버 폴링 API에서 안정적인 코드를 확인하지 못해 보류 (2026-09-05).
_LABELS = {
    "KOSPI": "코스피", "KOSDAQ": "코스닥",
    ".IXIC": "나스닥", ".INX": "S&P500", ".DJI": "다우존스", ".SOX": "필라델피아반도체",
}
_ORDER = ["KOSPI", "KOSDAQ", ".IXIC", ".INX", ".DJI", ".SOX"]

_cache = {"data": None, "ts": 0.0}
_lock = threading.Lock()


def _to_float(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _parse(items):
    out = {}
    for it in items:
        code = it.get("itemCode") or it.get("reutersCode")
        if not code or code not in _LABELS:
            continue
        price = _to_float(it.get("closePrice"))
        change = _to_float(it.get("compareToPreviousClosePrice"))
        rate = _to_float(it.get("fluctuationsRatio"))
        if price is None:
            continue
        out[code] = {
            "code": code, "name": _LABELS[code],
            "price": price, "change": change or 0.0, "rate": rate or 0.0,
        }
    return out


def _fetch_all():
    merged = {}
    r1 = requests.get(_DOMESTIC_URL, headers=_HEADERS, timeout=6)
    r1.raise_for_status()
    merged.update(_parse(r1.json().get("datas", [])))
    r2 = requests.get(_WORLD_URL, headers=_HEADERS, timeout=6)
    r2.raise_for_status()
    merged.update(_parse(r2.json().get("datas", [])))
    return [merged[c] for c in _ORDER if c in merged]


def get_market_indices(force_refresh=False):
    now = time.time()
    with _lock:
        if not force_refresh and _cache["data"] and (now - _cache["ts"] < _TTL_SECONDS):
            return _cache["data"], _cache["ts"]

    try:
        data = _fetch_all()
    except Exception:
        data = None

    if data:
        with _lock:
            _cache["data"] = data
            _cache["ts"] = now
        return data, now

    with _lock:
        return _cache["data"] or [], _cache["ts"]


def get_market_summary(force_refresh=False):
    data, ts = get_market_indices(force_refresh=force_refresh)
    return {
        "indices": data,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else None,
    }


if __name__ == "__main__":
    print(json.dumps(get_market_summary(force_refresh=True), ensure_ascii=False, indent=2))

"""Broker live integrations (Kiwoom domestic ISTA + Toss overseas).

Adapted directly from the user-provided reference examples:
  Kiwoom: POST /oauth2/token, GET /uapi/domestic-stock/v1/trading/inquire-balance (TR TTTC8434R)
  Toss: /oauth/token, GET /v1/accounts/{seq}/balances/overseas
Tokens are cached (1-day) in /data/cache/token_cache.json to avoid re-issuing.

Docs agree the JSON body; Kiwoom token replies key is `access_token` (per ref) — we read several aliases.
"""
import os, time, json
import requests
from dotenv import load_dotenv

load_dotenv("/opt/data/.env")

# ---------------- env helpers (tolernant: accept either alias) ----------------
def _env(*names, default=""):
    for n in names:
        v = os.getenv(n)
        if v:
            return v.strip().strip("'\"")
    return default


_DATA_ROOT = "/opt/data"
if os.path.exists("/data") and os.access("/data", os.W_OK):
    _DATA_ROOT = "/data"

CACHE_DIR = os.getenv("CACHE_DIR") or os.path.join(_DATA_ROOT, "cache")
CACHE_FILE = os.path.join(CACHE_DIR, "token_cache.json")
_TTL_SECONDS = 24 * 3600  # 1일


def _load_cache():
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(cache):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass


def _cached_token(key, getter):
    """Return a cached unexpired token, else fetch + cache."""
    now = time.time()
    cache = _load_cache()
    hit = cache.get(key)
    if hit and (now - hit.get("ts", 0) < _TTL_SECONDS):
        return hit["token"]
    token = getter()
    if token:
        cache[key] = {"token": token, "ts": now}
        _save_cache(cache)
    return token


class Throttler:
    def __init__(self, rps=5.0):
        self._min = 1.0 / rps if rps > 0 else  0
        self._last = 0.0
    def wait(self):
        now = time.monotonic()
        dt = now - self._last
        if dt < self._min:
            time.sleep(self._min - dt)
        self._last = time.monotonic()


# ==================== Kiwoom ====================
KIWOOM_REAL = "https://api.kiwoom.com"
KIWOOM_MOCK = "https://mockapi.kiwoom.com"

def _kiwoom_base():
    cfg = _env("KIWOOM_SERVER", default="real").lower()
    return KIWOOM_MOCK if cfg == "demo" else KIWOOM_REAL

KIWOOM_BASE_URL = _env("KIWOOM_BASE_URL", default=_kiwoom_base())
KIWOOM_APP_KEY = _env("KIWOOM_APP_KEY", "APP_KEY")
KIWOOM_APP_SECRET = _env("KIWOOM_APP_SECRET", "APP_SECRET")
KIWOOM_ACCOUNT_NO = _env("KIWOOM_ACCOUNT_NO")  # 정상 8자리 — 필수 (잔고 조회용)
KIWOOM_ACCOUNT_PRDT_CD = "01"


def _kiwoom_token_getter():
    url = KIWOOM_BASE_URL.rstrip("/") + "/oauth2/token"
    payload = {"grant_type": "client_credentials", "appkey": KIWOOM_APP_KEY, "secretkey": KIWOOM_APP_SECRET}
    headers = {"Content-Type": "application/json"}
    r = requests.post(url, json=payload, headers=headers, timeout=10)
    r.raise_for_status()
    return r.json().get("token") or r.json().get("access_token")


def kiwoom_token():
    if not KIWOOM_APP_KEY or not KIWOOM_APP_SECRET:

        return None
    return _cached_token("kiwoom", _kiwoom_token_getter)


def kiwoom_holdings():
    """보유 종목 + 계좌 요약 (POST /api/dostk/acnt, api-id kt00018)."""
    tok = kiwoom_token()
    if not tok or not KIWOOM_ACCOUNT_NO:
        return [], {}
    url = KIWOOM_BASE_URL.rstrip("/") + "/api/dostk/acnt"
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "Authorization": "Bearer " + tok,
        "api-id": "kt00018",
    }
    body = {"acctNo": KIWOOM_ACCOUNT_NO, "qry_tp": "2", "dmst_stex_tp": "KRX"}
    r = requests.post(url, json=body, headers=headers, timeout=10)
    r.raise_for_status()
    data = r.json()
    holdings = data.get("acnt_evlt_remn_indv_tot") or data.get("output1") or []
    summary = {
        "tot_evlt_amt": data.get("tot_evlt_amt"),
        "tot_pur_amt": data.get("tot_pur_amt"),
        "tot_evlt_pl": data.get("tot_evlt_pl"),
        "tot_prft_rt": data.get("tot_prft_rt"),
        "prsm_dpst_aset_amt": data.get("prsm_dpst_aset_amt"),
    }
    return holdings, summary


def kiwoom_list_accounts():
    holdings, _ = kiwoom_holdings()
    if not holdings and not KIWOOM_ACCOUNT_NO:
        return []
    return [{"account_no": KIWOOM_ACCOUNT_NO, "label": "키움 ISA", "currency_base": "KRW"}]


# ==================== Toss ====================
TOSS_BASE_URL = _env("TOSS_BASE_URL", "TOSSINVEST_BASE_URL", default="https://openapi.tossinvest.com")
TOSS_CLIENT_ID = _env("TOSS_CLIENT_ID", "TOSSINVEST_CLIENT_ID")
TOSS_CLIENT_SECRET = _env("TOSS_CLIENT_SECRET", "TOSSINVEST_CLIENT_SECRET")
TOSS_ACCOUNT_SEQ = _env("TOSS_ACCOUNT_SEQ", "TOSSINVEST_ACCOUNT_SEQ")


def _toss_token_getter():
    url = TOSS_BASE_URL.rstrip("/") + "/oauth2/token"
    payload = {"grant_type": "client_credentials", "client_id": TOSS_CLIENT_ID, "client_secret": TOSS_CLIENT_SECRET}
    r = requests.post(url, data=payload, timeout=10)  # form-encoded (no json Content-Type)
    r.raise_for_status()
    return r.json().get("token") or r.json().get("access_token")


def toss_token():
    if not TOSS_CLIENT_ID or not TOSS_CLIENT_SECRET:

        return None
    return _cached_token("toss", _toss_token_getter)


def _toss_seq():
    """계좌 일련번호: .env TOSS_ACCOUNT_SEQ 이 있으면 그 값, 아니면 계좌목록 API 첫 번째."""
    env = _env("TOSS_ACCOUNT_SEQ", "TOSSINVEST_ACCOUNT_SEQ")
    if env:
        return env
    accs = _toss_accounts_api()
    if accs:
        a = accs[0]
        return str(a.get("accountSeq") or a.get("account_seq") or a.get("seq") or a.get("accountNo") or "")
    return ""


def toss_overseas_balance():
    """해외/국내 보유 종목 + 계좌 요약 (GET /api/v1/holdings)."""
    tok = toss_token()
    seq = _toss_seq()
    if not tok or not seq:
        return {}
    url = TOSS_BASE_URL.rstrip("/") + "/api/v1/holdings"
    headers = {"Authorization": "Bearer " + tok, "X-Tossinvest-Account": seq}
    r = requests.get(url, headers=headers, timeout=10)
    r.raise_for_status()
    return r.json().get("result") or {}


_TOSS_ACCTS_CACHE = {"ts": 0, "data": None}


def _toss_accounts_api():
    """GET /api/v1/accounts — 내 계좌 목록 자동 조회 (5분 캐시, rate limit 회피)."""
    now = time.time()
    if _TOSS_ACCTS_CACHE["data"] is not None and (now - _TOSS_ACCTS_CACHE["ts"] < 300):
        return _TOSS_ACCTS_CACHE["data"]
    tok = toss_token()
    if not tok:
        return [] 
    url = TOSS_BASE_URL.rstrip("/") + "/api/v1/accounts"
    headers = {"Authorization": "Bearer " + tok, "Content-Type": "application/json"}
    r = requests.get(url, headers=headers, timeout=10)
    r.raise_for_status()
    data = r.json()
    accs = data.get("result") or data.get("accounts") or data.get("data") or []
    if isinstance(accs, dict):
        accs = accs.get("result") or accs.get("accounts") or accs.get("list") or []
    _TOSS_ACCTS_CACHE["data"] = accs
    _TOSS_ACCTS_CACHE["ts"] = now
    return accs


def toss_list_accounts():
    accs = _toss_accounts_api()
    rows = []
    for a in accs:
        seq = str(a.get("accountSeq") or a.get("account_seq") or a.get("seq") or a.get("accountNo") or "")
        if not seq:
            continue
        rows.append({"account_no": seq, "label": a.get("name") or "토스", "currency_base": "USD"})
    return rows


def collect_all():
    accs = []
    for i, a in enumerate(kiwoom_list_accounts()):
        a["broker"] = "kiwoom"
        a["display_order"] = i
        accs.append(a)
    base = len(accs)
    for i, a in enumerate(toss_list_accounts()):
        a["broker"] = "toss"
        a["display_order"] = base + i
        accs.append(a)
    return accs


def _to_num(v, default=0.0):
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "").replace("+", "")
    try:
        return float(s)
    except ValueError:
        return default


def collect_portfolio():
    """통합 보유 종목: 키움(KRW) + 토스. 행: symbol/name/qty/avg/cur/currency/broker + 평가손익/수익률."""
    portfolio = []

    # 키움
    kh, ks = kiwoom_holdings()
    for it in kh:
        portfolio.append({
            "symbol": it.get("stk_cd"), "name": it.get("stk_nm"),
            "qty": _to_num(it.get("rmnd_qty")), "avg_price": _to_num(it.get("pur_pric")),
            "cur_price": _to_num(it.get("cur_prc")), "currency": "KRW", "broker": "kiwoom",
            "p_pnl": _to_num(it.get("evltv_prft")), "p_pnl_rate": _to_num(it.get("prft_rt")),
        })

    # 토스
    tb = toss_overseas_balance()
    for it in (tb.get("items") or []):
        pl = it.get("profitLoss") or {}
        portfolio.append({
            "symbol": it.get("symbol"), "name": it.get("name"),
            "qty": _to_num(it.get("quantity")), "avg_price": _to_num(it.get("averagePurchasePrice")),
            "cur_price": _to_num(it.get("lastPrice")),
            "currency": (it.get("currency") or "USD"), "broker": "toss",
            "p_pnl": _to_num(pl.get("amount")),
            "p_pnl_rate": _to_num(pl.get("rate")),
        })

    return portfolio

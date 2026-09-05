"""FastAPI entrypoint: healthcheck + account auto-collection + index."""
import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

from . import db, brokers, snapshots, fx, auth, config, market


app = FastAPI(title="Stock Dashboard", version="0.1.0")


class LoginBody(BaseModel):
    username: str = ""
    password: str = ""
    remember: bool = False


@app.on_event("startup")
def _startup():
    db.init_db()
    # 계좌자동수집(순서)은 /api/accounts 호출 시 수행한다.


# ===== Serve-side session auth guard on /api/* (except /api/login) =====
@app.middleware("http")
async def _auth_guard(request: Request, call_next):
    path = request.url.path
    is_api = path.startswith("/api/")
    if is_api and path != "/api/login":
        token = request.cookies.get(auth.COOKIE)
        if not auth.validate(token):
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
    return await call_next(request)


@app.post("/api/login")
def login(body: LoginBody):
    if not config.settings.DASHBOARD_USERNAME or not config.settings.DASHBOARD_PASSWORD:
        return JSONResponse({"detail": "auth not configured"}, status_code=503)
    if not auth.verify_login(body.username, body.password):
        return JSONResponse({"detail": "invalid credentials"}, status_code=401)
    token, _ = auth.create_session()
    resp = JSONResponse({"ok": True, "session": True})
    # 항상 세션쿠키(영구X): 브라우저(탭) 종료 시 로그인 화면으로 복귀.
    # Remember Me 와 무관하게 지속 쿠키는 만들지 않는다.
    resp.set_cookie(auth.COOKIE, token, httponly=True, samesite="lax")
    return resp


@app.post("/api/logout")
def logout(request: Request):
    auth.revoke(request.cookies.get(auth.COOKIE))
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE)
    return resp


@app.get("/api/auth/me")
def auth_me(request: Request):
    # Reached only when the middleware validated the cookie -> authenticated.
    return {"authenticated": True}


@app.get("/health")
def health():
    return {"status": "ok", "db": db.DB_PATH}


@app.get("/api/accounts")
def list_accounts():
    accs = brokers.collect_all()
    return JSONResponse({"accounts": accs})


@app.get("/api/portfolio")
def portfolio():
    items = brokers.collect_portfolio()
    # DB 적재: 키움/토스 계좌별 holdings upsert
    ki = [x for x in items if x["broker"] == "kiwoom"]
    to = [x for x in items if x["broker"] == "toss"]
    saved = []
    if ki and brokers.KIWOOM_ACCOUNT_NO:
        saved.append(db.save_holdings(brokers.KIWOOM_ACCOUNT_NO, "kiwoom", ki))
    if to:
        seq = brokers._toss_seq()
        if seq:
            saved.append(db.save_holdings(seq, "toss", to))
    return JSONResponse({"holdings": items, "count": len(items), "saved": len(saved)})


@app.get("/api/portfolio/history")
def portfolio_history(range: str = "all"):
    """day_snapshots 시계열 조회 (7d|30d|90d|all). 차트 바인딩용 간결 JSON."""
    return JSONResponse(snapshots.get_portfolio_history(range_key=range))


@app.get("/api/quotes/summary")
def quotes_summary():
    """quotes 최신 종목별 등락 현황."""
    return JSONResponse(snapshots.get_quotes_summary())


@app.get("/api/fx/rate")
def fx_rate(refresh: bool = False):
    """실시간 USD→KRW 환율 (TTL 1h, 폴백 포함). refresh=true 시 캐시 무시하고 강제 갱신."""
    return JSONResponse(fx.get_fx_summary(force_refresh=refresh))


@app.get("/api/market/indices")
def market_indices(refresh: bool = False):
    """주요 증시 지수(코스피/코스닥/나스닥/S&P500/다우존스/필라델피아반도체). TTL 1h, 폴백 포함."""
    return JSONResponse(market.get_market_summary(force_refresh=refresh))


@app.get("/")
def index():
    here = os.path.dirname(os.path.abspath(__file__))
    return FileResponse(os.path.join(here, "static", "index.html"))
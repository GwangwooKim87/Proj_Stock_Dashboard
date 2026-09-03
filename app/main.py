"""FastAPI entrypoint: healthcheck + account auto-collection + index."""
import os
from fastapi import FastAPI
from fastapi.responses import JSONResponse, FileResponse

from . import db, brokers


app = FastAPI(title="Stock Dashboard", version="0.1.0")


@app.on_event("startup")
def _startup():
    db.init_db()
    # 계좌 자동수집(순서)은 /api/accounts 호출 시 수행한다.


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


@app.get("/")
def index():
    here = os.path.dirname(os.path.abspath(__file__))
    return FileResponse(os.path.join(here, "static", "index.html"))
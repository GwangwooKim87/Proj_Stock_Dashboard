"""일별 포트폴리오 스냅샷 + 당일 시세 캐시 수집 로직.

증권사 연동 브로커(brokers.collect_portfolio) 결과를 받아
  - day_snapshots: 오늘 날짜 기준 UPSERT (총평가액/원금/손익/수익률 + 종목별 JSON)
  - quotes     : 종목별 시세 캐시 UPSERT (현재가/전일종가/등락률)
로 저장한다. 장마감 스케줄러와 수동 CLI 양쪽에서 재사용한다.
"""
import json
import os
import time
from datetime import date as _date

try:
    from . import db, brokers, fx
except ImportError:  # 스크립트 직접 실행 시 (python -m snapshots)
    import db, brokers, fx  # noqa: F401


def get_fx_rate():
    """USD→KRW 환율 (실시간 fx 모듈 폴백 체인: 캐시→DB→기본값)."""
    return fx.get_usd_krw()


def _to_krw(amount, currency, fx):
    return float(amount or 0.0) * (fx if (currency or "KRW") != "KRW" else 1.0)


def collect_day_snapshot(snapshot_date=None):
    """포폴리오 조회 → KRW 환산 총액/손익 계산 → day_snapshots 행 dict 반환."""
    snapshot_date = snapshot_date or _date.today().isoformat()
    fx = get_fx_rate()
    items = brokers.collect_portfolio()

    total_eval = 0.0
    total_invested = 0.0
    total_pnl = 0.0
    holdings = []

    for it in items:
        currency = it.get("currency") or "KRW"
        qty = float(it.get("qty") or 0.0)
        cur = float(it.get("cur_price") or 0.0)
        avg = float(it.get("avg_price") or 0.0)
        eval_krw = _to_krw(qty * cur, currency, fx)
        inv_krw = _to_krw(qty * avg, currency, fx)
        pnl_krw = _to_krw(it.get("p_pnl", 0.0), currency, fx)

        total_eval += eval_krw
        total_invested += inv_krw
        total_pnl += pnl_krw

        # 종목별 수익률: 브로커별 단위(퍼센트/비율) 불일치를 피하려 KRW 손익/원금으로 직접 계산
        rate = (pnl_krw / inv_krw * 100.0) if inv_krw else (None if pnl_krw == 0 else 0.0)

        holdings.append({
            "symbol": it.get("symbol"), "name": it.get("name"),
            "qty": qty, "avg_price": avg, "cur_price": cur,
            "currency": currency, "broker": it.get("broker"),
            "eval_krw": round(eval_krw, 2), "invested_krw": round(inv_krw, 2),
            "profit_krw": round(pnl_krw, 2), "profit_rate": round(rate, 2)
            if rate is not None else None,
        })

    profit_rate = (total_pnl / total_invested * 100.0) if total_invested else 0.0

    return {
        "snapshot_date": snapshot_date,
        "total_evaluation_amount": round(total_eval, 2),
        "total_investment_amount": round(total_invested, 2),
        "total_profit_loss": round(total_pnl, 2),
        "profit_rate": round(profit_rate, 2),
        "holdings_json": json.dumps(holdings, ensure_ascii=False),
        "fx_rate": fx,
    }


def save_day_snapshot(snap):
    """snapshot_date 기준 UPSERT. 있으면 갱신, 없으면 삽입."""
    conn = db.get_connection()
    try:
        conn.execute("""
            INSERT INTO day_snapshots
                (snapshot_date, total_evaluation_amount, total_investment_amount,
                 total_profit_loss, profit_rate, holdings_json, created_at)
            VALUES (?,?,?,?,?,?, datetime('now'))
            ON CONFLICT(snapshot_date) DO UPDATE SET
                total_evaluation_amount=excluded.total_evaluation_amount,
                total_investment_amount=excluded.total_investment_amount,
                total_profit_loss=excluded.total_profit_loss,
                profit_rate=excluded.profit_rate,
                holdings_json=excluded.holdings_json,
                created_at=excluded.created_at
        """, (snap["snapshot_date"], snap["total_evaluation_amount"],
              snap["total_investment_amount"], snap["total_profit_loss"],
              snap["profit_rate"], snap["holdings_json"]))
        conn.commit()
    finally:
        conn.close()


def save_quotes(items):
    """종목별 시세 캐시 UPSERT (symbol PK). items 는 collect_portfolio() 행."""
    conn = db.get_connection()
    try:
        for it in items:
            symbol = it.get("symbol")
            if not symbol:
                continue
            conn.execute("""
                INSERT INTO quotes (symbol, current_price, prev_close_price, change_rate, updated_at)
                VALUES (?,?,?,?, datetime('now'))
                ON CONFLICT(symbol) DO UPDATE SET
                    current_price=excluded.current_price,
                    prev_close_price=excluded.prev_close_price,
                    change_rate=excluded.change_rate,
                    updated_at=excluded.updated_at
            """, (symbol, float(it.get("cur_price") or 0.0),
                  _flt(it.get("prev_close")), _flt(it.get("change_rate"))))
        conn.commit()
    finally:
        conn.close()


def run_collect(snapshot_date=None):
    """전체 실행: 시세 캐시 + 일일 스냅샷 저장 후 요약 dict 반환 (수동/크론 공용)."""
    snapshot_date = snapshot_date or _date.today().isoformat()
    items = brokers.collect_portfolio()
    if items:
        save_quotes(items)
    snap = collect_day_snapshot(snapshot_date)
    save_day_snapshot(snap)
    return {
        "snapshot_date": snapshot_date,
        "holdings_count": len(items),
        "total_evaluation_amount": snap["total_evaluation_amount"],
        "total_investment_amount": snap["total_investment_amount"],
        "total_profit_loss": snap["total_profit_loss"],
        "profit_rate": snap["profit_rate"],
        "fx_rate": snap["fx_rate"],
        "status": "ok",
    }


def _flt(v):
    """float 또는 None."""
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


# ==================== 시계열 조회 (차트 바인딩) ====================
_RANGE_DAYS = {"7d": 7, "30d": 30, "90d": 90}


def get_portfolio_history(range_key="all"):
    """day_snapshots 를 날짜 오름차순으로 조회 → 차트용 간결 구조 반환.

    range_key: 7d | 30d | 90d | all (기본 all). 데이터 없으면 빈 배열 + 200 대상 구조.
    """
    days = _RANGE_DAYS.get(str(range_key))
    conn = db.get_connection()
    try:
        if days:
            cutoff = _date.today().fromordinal(_date.today().toordinal() - days).isoformat()
            rows = conn.execute(
                "SELECT snapshot_date, total_evaluation_amount, total_profit_loss, profit_rate "
                "FROM day_snapshots WHERE snapshot_date >= ? ORDER BY snapshot_date ASC",
                (cutoff,)).fetchall()
        else:
            rows = conn.execute(
                "SELECT snapshot_date, total_evaluation_amount, total_profit_loss, profit_rate "
                "FROM day_snapshots ORDER BY snapshot_date ASC").fetchall()
    finally:
        conn.close()

    return {
        "range": str(range_key),
        "count": len(rows),
        "dates": [r["snapshot_date"] for r in rows],
        "total_values": [r["total_evaluation_amount"] or 0 for r in rows],
        "total_profit_loss": [r["total_profit_loss"] or 0 for r in rows],
        "profit_rates": [r["profit_rate"] or 0 for r in rows],
    }


def get_quotes_summary():
    """quotes 의 최신 종목별 등락 현황 (symbol PK 특성상 최신 레코드)."""
    conn = db.get_connection()
    try:
        rows = conn.execute(
            "SELECT symbol, current_price, prev_close_price, change_rate, updated_at "
            "FROM quotes ORDER BY symbol ASC").fetchall()
    finally:
        conn.close()

    items = []
    for r in rows:
        items.append({
            "symbol": r["symbol"],
            "current_price": r["current_price"],
            "prev_close_price": r["prev_close_price"],
            "change_rate": r["change_rate"],
            "updated_at": r["updated_at"],
        })
    return {"count": len(items), "quotes": items}


if __name__ == "__main__":
    t0 = time.time()
    result = run_collect()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"elapsed: {time.time() - t0:.1f}s")
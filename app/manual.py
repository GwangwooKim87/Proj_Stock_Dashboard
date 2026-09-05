"""수동 관리 자산(IRP 등) CRUD.

키움 개발자 API로 잔고 조회가 불가능한 계좌(IRP 등)를 위해 사용자가 직접
종목/수량/매입단가를 등록·관리한다. 현재가는 별도로 저장하지 않고 quotes
캐시(symbol PK)를 브로커 보유종목과 공유한다 — snapshots.fetch_and_update_quotes()
가 같은 배치에서 manual_holdings의 ticker도 함께 조회·갱신한다.
"""
try:
    from . import db
except ImportError:  # 스크립트 직접 실행 시
    import db  # noqa: F401


def list_holdings(account_name=None):
    conn = db.get_connection()
    try:
        if account_name:
            rows = conn.execute(
                "SELECT * FROM manual_holdings WHERE account_name=? ORDER BY id ASC",
                (account_name,)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM manual_holdings ORDER BY account_name ASC, id ASC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _clean(data):
    ticker = (data.get("ticker") or "").strip()
    if not ticker:
        raise ValueError("ticker required")
    qty = float(data.get("quantity") or 0)
    buy = float(data.get("buy_price") or 0)
    if qty < 0 or buy < 0:
        raise ValueError("quantity/buy_price must be >= 0")
    return {
        "account_name": (data.get("account_name") or "키움 IRP").strip() or "키움 IRP",
        "ticker": ticker,
        "name": (data.get("name") or "").strip(),
        "quantity": qty,
        "buy_price": buy,
        "currency": (data.get("currency") or "KRW").strip().upper() or "KRW",
    }


def create_holding(data):
    c = _clean(data)
    conn = db.get_connection()
    try:
        cur = conn.execute("""
            INSERT INTO manual_holdings(account_name, ticker, name, quantity, buy_price, currency, updated_at)
            VALUES (?,?,?,?,?,?, datetime('now'))
        """, (c["account_name"], c["ticker"], c["name"], c["quantity"], c["buy_price"], c["currency"]))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_holding(holding_id, data):
    c = _clean(data)
    conn = db.get_connection()
    try:
        conn.execute("""
            UPDATE manual_holdings SET
                account_name=?, ticker=?, name=?, quantity=?, buy_price=?, currency=?,
                updated_at=datetime('now')
            WHERE id=?
        """, (c["account_name"], c["ticker"], c["name"], c["quantity"], c["buy_price"], c["currency"], holding_id))
        conn.commit()
    finally:
        conn.close()


def delete_holding(holding_id):
    conn = db.get_connection()
    try:
        conn.execute("DELETE FROM manual_holdings WHERE id=?", (holding_id,))
        conn.commit()
    finally:
        conn.close()


def list_holdings_for_portfolio():
    """collect_portfolio() 와 동일한 item 형태로 변환 (broker='manual', account=계좌명).

    현재가는 quotes 캐시에서 조회한다. 캐시에 아직 없으면(최초 등록 직후,
    또는 토스 시세 매칭 실패) 매입단가를 잠정 현재가로 사용해 0평가를 방지한다
    — 실제 시세는 새로고침/일일 크론이 fetch_and_update_quotes()를 돌릴 때 채워진다.
    """
    holdings = list_holdings()
    if not holdings:
        return []
    conn = db.get_connection()
    try:
        symbols = list({h["ticker"] for h in holdings})
        placeholders = ",".join("?" * len(symbols))
        rows = conn.execute(
            f"SELECT symbol, current_price FROM quotes WHERE symbol IN ({placeholders})",
            symbols).fetchall()
        price_map = {r["symbol"]: r["current_price"] for r in rows}
    finally:
        conn.close()

    items = []
    for h in holdings:
        qty = float(h["quantity"] or 0)
        avg = float(h["buy_price"] or 0)
        cached = price_map.get(h["ticker"])
        cur = float(cached) if cached is not None else avg
        pnl = (cur - avg) * qty
        rate = ((cur - avg) / avg * 100.0) if avg else None
        items.append({
            "symbol": h["ticker"], "name": h["name"] or h["ticker"],
            "qty": qty, "avg_price": avg, "cur_price": cur,
            "currency": h["currency"] or "KRW", "broker": "manual",
            "account": h["account_name"],
            "p_pnl": round(pnl, 2), "p_pnl_rate": round(rate, 2) if rate is not None else None,
            "prev_close": None, "change_rate": None,
        })
    return items

"""DB init: apply schema.sql, expose a get_connection()."""
import os, sqlite3, time

_DATA_ROOT = "/opt/data"
if os.path.exists("/data") and os.access("/data", os.W_OK):
    _DATA_ROOT = "/data"

DB_PATH = os.getenv("DB_PATH") or os.path.join(_DATA_ROOT, "dashboard.db")


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(force=False):
    conn = get_connection()
    try:
        conn.executescript(_schema_sql())
        conn.commit()
    finally:
        conn.close()
    return DB_PATH


def _schema_sql():
    here = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(here, "schema.sql")
    with open(p, encoding="utf-8") as f:
        return f.read()


def save_holdings(account_no, broker, holdings):
    """holdings 를 계좌별 upsert (현재가/평가 업데이트). account_no 로 식별."""
    conn = get_connection()
    try:
        cur = conn.execute("SELECT id FROM accounts WHERE account_no=? AND broker=?", (account_no, broker))
        row = cur.fetchone()
        if row:
            account_id = row["id"]
        else:
            cur = conn.execute(
                "INSERT INTO accounts(broker, account_no, label, currency_base) VALUES (?,?,?,?)",
                (broker, account_no, f"{broker}-{account_no}", "KRW" if broker=="kiwoom" else "USD"))
            account_id = cur.lastrowid
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        for it in holdings:
            conn.execute("""
                INSERT INTO holdings(account_id, symbol, name, qty, avg_price, cur_price, currency, updated_at)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(account_id, symbol) DO UPDATE SET
                    name=excluded.name, qty=excluded.qty, avg_price=excluded.avg_price,
                    cur_price=excluded.cur_price, currency=excluded.currency, updated_at=excluded.updated_at
            """, (account_id, it.get("symbol"), it.get("name"), it.get("qty"),
                  it.get("avg_price"), it.get("cur_price"), it.get("currency"), now))
        conn.commit()
        return account_id
    finally:
        conn.close()


if __name__ == "__main__":
    print("DB at:", init_db())
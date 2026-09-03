-- 개인 주식 자산 통합 대시보드 — SQLite 스키마 (DDL)
-- 저사양 NAS용: 단일 파일 dashboard.db, 외래키/인덱스로 시계열 질의 경량화
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- 1. 증권사 계좌 (계좌 번호/순서는 증권사 계좌 조회 API 로 자동 수집,
--   display_order 를  기준으로 대시보드 정렬)
CREATE TABLE IF NOT EXISTS accounts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    broker       TEXT NOT NULL CHECK (broker IN ('kiwoom', 'toss')),
    label        TEXT,                               -- 예: '키움 ISA', '토스 해외'
    account_no   TEXT NOT NULL,                       -- 키움 계좌번호 / 토스 계좌일련번호
    currency_base TEXT NOT NULL DEFAULT 'KRW',         -- 기준통화
    display_order INTEGER NOT NULL DEFAULT 0,      -- 계좌 표시 순서 (증권사 반환 순서 자동 기입)
    enabled      INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_accounts_broker ON accounts(broker);
CREATE INDEX IF NOT EXISTS idx_accounts_order  ON accounts(display_order);

-- 2. 계좌별 보유 종목 현황 (수량/평단가/현재가/평가손익)
CREATE TABLE IF NOT EXISTS holdings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id   INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    symbol       TEXT NOT NULL,                        -- 종목코드/틱커
    name         TEXT,                                -- 종목명
    qty          REAL NOT NULL DEFAULT 0,            -- 보유수량
    avg_price    REAL NOT NULL DEFAULT 0,          -- 평단가 (종목 통화)
    cur_price    REAL NOT NULL DEFAULT 0,          -- 현재가 (종목 통화)
    currency     TEXT NOT NULL DEFAULT 'KRW',          -- 종목 결제통화 (KRW/USD)
    updated_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(account_id, symbol),
    FOREIGN KEY(account_id) REFERENCES accounts(id)
);
CREATE INDEX IF NOT EXISTS idx_holdings_account ON holdings(account_id);
CREATE INDEX IF NOT EXISTS idx_holdings_symbol  ON holdings(symbol);

-- 3. 종목 시세 시계열 (15분 스냅샷)
CREATE TABLE IF NOT EXISTS quotes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    broker      TEXT,                       -- kiwoom/toss (통합일 경우 통합계좌?)
    symbol      TEXT NOT NULL,
    price       REAL NOT NULL,
    currency    TEXT NOT NULL DEFAULT 'KRW',
    price_krw   REAL,                       -- KRW 환산가 (해외주식/환율 적용)
    base_krw    REAL,                       -- 적용 기준환율 (USD당 KRW)
    fetched_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_quotes_sym_time ON quotes(symbol, fetched_at);

-- 4. 일자별 확정 자산 스냅샷 (국내 15:30 / 미국 익일 06:00 마감 시점)
CREATE TABLE IF NOT EXISTS day_snapshots (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id     INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    snap_date      TEXT NOT NULL,                     -- 'YYYY-MM-DD'
    total_value    REAL NOT NULL DEFAULT 0,        -- 총평가액 (KRW)
    invested       REAL NOT NULL DEFAULT 0,        -- 투자원금 (KRW)
    realized_pnl   REAL NOT NULL DEFAULT 0,       -- 실현손익
    unrealized_pnl REAL NOT NULL DEFAULT 0,       -- 미실현손익 (평가손익)
    krw_exposure   REAL NOT NULL DEFAULT 0,       -- 원화 노출액
    usd_exposure   REAL NOT NULL DEFAULT 0,       -- 외화(USD) 노출액
    captured_at     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(account_id, snap_date)
);
CREATE INDEX IF NOT EXISTS idx_snap_account_date ON day_snapshots(account_id, snap_date);

-- 5. 종목 뉴스 (네이버 금융 필터링 소스, 본문 대신 제목+2줄 요약만)
CREATE TABLE IF NOT EXISTS news_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol       TEXT NOT NULL,
    source       TEXT DEFAULT 'naver',
    title        TEXT NOT NULL,
    summary      TEXT,                    -- 핵심 2줄 요약 (AI/추출)
    url          TEXT,
    published_at TEXT,
    fetched_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_news_sym_time ON news_items(symbol, published_at);

-- 6. 모닝 피드 산출물 (DeepSeek v4 Flash 출력)
CREATE TABLE IF NOT EXISTS morning_feed (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    feed_date  TEXT NOT NULL,            -- 'YYYY-MM-DD'
    symbol     TEXT,
    title      TEXT,
    summary    TEXT,
    impact     TEXT,
    source_url TEXT,
    raw_prompt_len INTEGER DEFAULT 0,  -- 토큰 예산 추적용
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(feed_date, symbol)
);
CREATE INDEX IF NOT EXISTS idx_feed_date ON morning_feed(feed_date);

-- 7. 환율 시세 (USD→KRW 기준환율, 실시간 매매기준율 / 전일 마감 폴백)
CREATE TABLE IF NOT EXISTS fx_rates (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    pair       TEXT NOT NULL DEFAULT 'USDKRW',
    rate       REAL NOT NULL,
    source     TEXT DEFAULT 'naver-fx',        -- or 'ecos-mid' 등
    fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_fx_time ON fx_rates(fetched_at);
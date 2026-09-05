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

-- 3. 종목 시세 캐시 (당일 장중 임시 캐시, symbol 단위 최신가)
CREATE TABLE IF NOT EXISTS quotes (
    symbol           TEXT PRIMARY KEY,           -- 종목코드/틱커
    current_price    REAL NOT NULL,              -- 현재가
    prev_close_price REAL,                       -- 전일종가
    change_rate      REAL,                       -- 등락률(%)
    updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 4. 일자별 확정 포트폴리오 스냅샷 (당일 장마감 시점, 날짜 단위 upsert)
CREATE TABLE IF NOT EXISTS day_snapshots (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date          TEXT NOT NULL UNIQUE, -- 'YYYY-MM-DD'
    total_evaluation_amount REAL NOT NULL DEFAULT 0, -- 총 평가액 (KRW)
    total_investment_amount REAL NOT NULL DEFAULT 0, -- 총 투자원금 (KRW)
    total_profit_loss       REAL NOT NULL DEFAULT 0, -- 총 손익 (KRW)
    profit_rate             REAL NOT NULL DEFAULT 0, -- 수익률(%)
    holdings_json           TEXT,                    -- 보유 종목별 종가/수익률/수량 JSON
    created_at              TEXT NOT NULL DEFAULT (datetime('now'))
);

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

-- 8. 수동 관리 자산 (키움 IRP 등 API로 잔고 조회 불가능한 계좌의 종목을 직접 입력)
--   현재가는 별도 보관하지 않고 quotes 캐시(brokers.get_quote 경유)를 공유한다.
CREATE TABLE IF NOT EXISTS manual_holdings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    account_name TEXT NOT NULL DEFAULT '키움 IRP',  -- 계좌 구분 (향후 다른 수동계좌도 이 필드로 확장)
    ticker       TEXT NOT NULL,                     -- 종목코드(국내 6자리) 또는 해외 티커
    name         TEXT,
    quantity     REAL NOT NULL DEFAULT 0,
    buy_price    REAL NOT NULL DEFAULT 0,            -- 평균 매입단가 (종목 통화)
    currency     TEXT NOT NULL DEFAULT 'KRW',
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_manual_account ON manual_holdings(account_name);
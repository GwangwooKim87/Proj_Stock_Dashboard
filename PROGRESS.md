# Stock Dashboard — PROGRESS (세션간 핸드오프) · 최종 갱신 2026-09-04

## ✅ 완료·검증됨 (실통신)
- **토스/키움 실연동**: 토큰·잔고·보유 조회 → 12종목(키움3+토스9) 평가손익/수익률 통합. 토스 401 토큰 자동재발급, 5분 rate-limit 캐시.
 실행: `cd app && ../.venv/bin/python -m snapshots`
- **DB(SQLite)**: accounts/holdings(+quotes/day_snapshots) 적재·upsert. DB: /opt/data/dashboard.db (live: /data/dashboard.db)

## ✅ 시계열 DB 스키마 + 수집 로직
- 스키마 재설계: `quotes`(symbol PK, current_price/prev_close_price/change_rate/updated_at),
  `day_snapshots`(snapshot_date UNIQUE, total_evaluation_amount/investment_amount/profit_loss/profit_rate/holdings_json/created_at.

- `db._migrate_tables()`: 기존 구스키마 감지 시 DROP 후 재생성(멱등. 컨테이너에 db.py 누락 시 500(`no such column: current_price) → db.py 포함해 docker cp 필수.

- `app/snapshots.py`: collect_portfolio → KRW 환산(USD→KRW — `app/fx.py` 실시간 모듈: 캐시→DB→기본값 폴백) 총액/손익 → day_snapshots UPSERT + quotes UPSERT.

- 전역 하드코딩 `1350` 제거: snapshots.py `get_fx_rate()` → fx 모듈 위임. 고정 상수는 fx.py `FALLBACK_RATE` 단일 잔존(안전 폴백.
 index.html은 `/api/fx/rate` fetch (Promise.all 병렬` → `FX_RATE` → 도넛에 사용, FX_RATE 유효 시만 렌더).

- 종목별 수익률은 브로커 단위 불일치(퍼센트/비율) 피하려 KRW 손익/원금으로 직접 계산.

## ✅ 시계열 조회 REST API + 프론트 추이선
- `GET /api/portfolio/history?range={7d|30d|90d|all}`: day_snapshots 날짜 오름차순, 차트용 간결 JSON
  `{range,count,dates[],total_values[],total_profit_loss[],profit_rates[]}`. 무효 range→전체. 빈 데이터→200+빈 배열. (snapshots.get_portfolio_history. 
- `GET /api/quotes/summary`: quotes 최신 종목별 등락 `{count,quotes[]}`. (snapshots.get_quotes_summary.)
- 대시보드 상단 '총자산 시계열 추이' Area 차트(ECharts) + 기간 필터(7일/30일/전체) → history fetch → setOption 갱신. 툴팁(날짜/총평가액/변동률), Y축 원화(만/억). 테마 기존 도넛과 통일(#4ade80,#1a1d24).


## ✅ 종목별 비중 FX 환산
- 도넛 ①(종목별 평가금액 비중)에 USD→KRW(FX=1350) 환산 적용 — 원화vs외화 도넛(②)와 동일 기준통일. FX 상수 도넛 공통화.



## 🔧 배포 상태 (live docker, 종료 시점)
- 컨테이너 **stock-dash** Up, `0.0.0.0:8080`. 볼륨 `stock_dash_data:/data`(DB 여기.
 배포: `docker cp <file> stock-dash:/app/app/<path>` + `docker restart stock-dash`(docker-compose 미지원. 
- 반영된 파일: db.py, main.py, snapshots.py, schema.sql, static/index.html. (db.py 누락 주의, 마이그레이션)
- 접속: `http://<NAS_IP>:8080` (컨테이너 내부 127.0.0.1:8080에서만 접근. 호스트에서 curl/wget 불가—검증은 `docker exec stock-dash python` 사용. 




## ✅ 일일 스냅샷 수집 크론
- **잡 ID `d97014bf74ee`** (name: stock-dashboard-daily-snapshot), no_agent 스크립트.

- 스케줄: 매일 **06:30 UTC = 한국 15:30**(장마감 직후). `docker exec -w /app/app stock-dash python -m snapshots` 수집 + 컨테이너 내부 검증.

- 스크립트: `~/.hermes/scripts/day_snapshot.sh`(양쪽 .hermes/scripts/에 배치. 호스트에서 127.0.0.1 접근 금지→검증은 docker exec 내부로. 
- 전송: Slack(C0BUM3859C2) + Telegram(8721078321). 실행 확인: status ok(12종목), 검증 history 정상.

## ✅ Git 상태 (종료 시점)
- GitHub: **main = `cd086a5`**, **develop = `98c2625`** (PR #8 squash 머지. main 보호: 리뷰1건 → 머지 시 `--admin`. `--delete-branch` 로 feature/market-quotes 원격 삭제.)
- 원격 브랜치: main + develop 2개만.
- PR 이력: #1 스키마+수집 → #2 REST API+추이선 → #4 릴리즈(→main) → #5 도넛환산 → #6 실시간환율 → #7 릴리즈(→main) → #8 당일변동(시세)수집.



## ✅ 실시간 환율 연동 (app/fx.py, 2026-09-04 세션)
- 신규 `app/fx.py` 실시간 USD→KRW 환율 모듈:
  - 소스: .env `EXCHANGE_RATE_API_URL`(없으면 FX_BASE_URL, 기본 open.er-api.com/v6/latest/USD — 무료·키 없음.

  - 인메모리 TTL 1h 캐시, 성공 시 fx_rates DB persist, 오류 시 폴백 체인(최근 캐시→DB→FALLBACK_RATE=1350 안전폴백`. 
  - `get_usd_krw()`/`get_fx_summary()`.
- `GET /api/fx/rate`: 실시간 환율+updated_at 반환 (TTL 캐시·폴백 포함. 
- 전역 하드코딩 `1350` 제거: snapshots.get_fx_rate() → fx 위임, index.html `const FX=1350`→`/api/fx/rate` fetch(Promise.all 병렬`, FX_RATE, 유효 시만 도넛 렌더`. 고정 1350은 fx.py FALLBACK_RATE 단일 잔존. 검증: 실시간 ~1356.7(open.er-api), /api/fx/rate 200 로컬·live, JS node --check, 라이브 index.html 1350 제거 확인.


## ✅ 당일 변동 보강 완료 (PR #8, 2026-09-04)
- `app/brokers.py`: `toss_prices(symbols)`(GET /api/v1/prices 다건 현재가, 국내 KRX+해외 US 통합), `toss_prev_close(symbol)`(GET /api/v1/candles 1d 전일종가 closePrice), `get_quote(symbols, with_prev_close)`(현재가+전일종가+통화, 미매칭 심볼 skip). 키움 ka10001 REST 시세는 이 배포 미노출(500) → 국내도 토스로 조회.
- `app/snapshots.py` `fetch_and_update_quotes()`: 보유 12종목 시세 수집 → quotes에 current_price/prev_close_price/change_rate UPSERT (0나누기 예외 방지, 소수 2자리). 토스 미매칭 키움 ETF는 보유 현재가 백필. save_quotes ON CONFLICT(symbol) DO UPDATE. `python -m snapshots`(일일 크론)에 통합 → run_collect return에 quotes 결과 포함.
- 키움 토큰 만료(8005/인증실패) 시 자동 재발급+재시도 (토스와 동일 패턴).
- 검증: 12종목 updated, 환율 1356.73, 스냅샷 -5.25%, get_quote(005380,006800,QLD) → 현대차 384500/379500 KRW, QLD 91.22/90.38 USD.

## ✅ /api/quotes/summary 방어 + 단독 실행 테스트 (2026-09-04)
- `snapshots.get_quotes_summary()`: NULL 누락(prev_close_price/change_rate — 키움 ETF 3종목) → `0.0` 방어 처리 (프론트 렌더 에러 방지). 검증: 12종목 `count=12`, remaining_nulls=0. HTTP 200 확인 (uvicorn 로컬 /api/quotes/summary).
- `if __name__ == '__main__'`: run_collect 결과 + quotes summary 병행 출력 (수집·DB적재·요약 1회 콘솔 확인). 실행: `cd app && ../.venv/bin/python -m snapshots` → 12종목 updated/failed 0.
- 실통신: holding 12, 수집 12 quotes updated 0 failed, 환율 1356.73, 요약 정상.

## ✅ 인증(서버 세션) 구현 + env 배포 구조 파악 (2026-09-04, UI/UX M1)
- **서버 사이드 세션 인증**: `app/auth.py`(신규) — .env 자격(`DASHBOARD_USERNAME/PASSWORD`)을 `hmac.compare_digest`로 비교, `secrets.token_urlsafe` 세션토큰(7일 TTL) httpOnly쿠키. `app/config.py`에 2개 설정 추가. `app/main.py`에 `POST /api/login|logout`, `GET /api/auth/me`, `/api/*` 전역 http 미들웨어 가드(로그인 제외, 무효→401). `/health`는 공개 유지.
- **프론트(index.html)** M1-2 교체: 로컬세션 → 서버 세션. `guardInit()`이 `/api/auth/me`로 유효성 확인→미인증 시 로그인 overlay+`#appMain` 숨김. `doLogin()`이 실제 `/api/login` 호출, 실패 시 에러문구(#f85149). 로그인 카드 350→440→**560px**, 패딩/폰트 확대.
- **환경변수 배포 구조 (중요)**: 이 컨테이너는 **docker run(--env-file) 방식**이지 docker-compose가 아님(compose label 없음, 볼륨 마운트 `./app` 없음). 그러므로 ①새 env 키는 `--env-file /opt/data/.env`로 주입하고 ②코드는 `docker cp`로 반영해야 함. `docker restart`는 env를 재로드하지 않으므로 **새 env는 컨테이너 재생성(`docker rm -f`+`docker run -d --env-file /opt/data/.env ...`) 필요**.
- **배포된 컨테이너 재생성**: `docker rm -f stock-dash; docker run -d --name stock-dash --restart unless-stopped -p 8080:8080 -e TZ=Asia/Seoul -e PYTHONUNBUFFERED=1 --env-file /opt/data/.env -v stock_dash_data:/data stock-dash:latest uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 1` + 최신 코드 docker cp 8개 파일.
- **검증(실배포)**: 미로그인 /api/auth/me→401, 틀린 로그인→401, `.env` 실자격 로그인→200+쿠키, 이후 auth/me·portfolio→200, 로그아웃→200, 이후 auth/me→401. 사용자가 /opt/data/.env 606~607행에 자격 입력.(값 마스킹)
- **주의**: .env 내 DASHBOARD 키는 이전에는 없었음 → 사용자 직접 입력. 추후 브로커 키처럼 --env-file로만 주입.

## ⏭ 다음 세션 (남은 작업)
1. **AI 브리핑 카드** → Hermes 직접 처리로 연결 — **미진행** (사용자 유예)
2. (선택) **네이버 뉴스 수집 + 변동성 필터링** — **미진행** (사용자 미룸) 

## 참고
- 로컬 develop 브랜치는 원격에서 복원함(PR 병합 --delete-branch로 사라짐. `git checkout -b develop origin/develop`.)
- /opt/data/.env: KIWOOM_APP_KEY/SECRET/ACCOUNT_NO, TOSSINVEST_CLIENT_ID/SECRET, GITHUB_TOKEN. (TOSS_ACCOUNT_SEQ 자동.

- 브라우저 렌더링(live 도넛/추이선)은 이 환경 브라우저 daemon 미기동으로 미확인 — 사용자 직접 확인. JS 구문은 node --check로 검증.
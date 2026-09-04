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
- GitHub: **main = develop = `8483481`**(마지막 develop 헤드) + **main 최신 `f965170`** (develop→main 릴리즈 PR#4 admin 머지. main 보호: 리뷰1건 → 머지 시 `--admin`.).
- 원격 브랜치: main + develop 2개만 (feature/fix 모두 삭제·prune 완료. 
- PR 이력: #1 스키마+수집 → #2 REST API+추이선 → #4 릴리즈(→main) → #5 도넛환산.



## ⏭ 다음 세션 (남은 작업)
1. **AI 브리핑 카드** → Hermes 직접 처리로 연결 — **미진행** (사용자 유예)
2. (선택) **네이버 뉴스 수집 + 변동성 필터링** — **미진행** (사용자 미룸)
3. **당일 변동 보강**: quotes의 prev_close_price/change_rate가 NULL — 브로커가 전일종가/등락률을 안 줌 → **전용 시세 API**(키움/토스 따로 외) 필요. 추이선은 일일 스냅샷 크론이 쌓이는 중(현재 1일치. 

## 참고
- 로컬 develop 브랜치는 원격에서 복원함(PR 병합 --delete-branch로 사라짐. `git checkout -b develop origin/develop`.)
- /opt/data/.env: KIWOOM_APP_KEY/SECRET/ACCOUNT_NO, TOSSINVEST_CLIENT_ID/SECRET, GITHUB_TOKEN. (TOSS_ACCOUNT_SEQ 자동.

- 브라우저 렌더링(live 도넛/추이선)은 이 환경 브라우저 daemon 미기동으로 미확인 — 사용자 직접 확인. JS 구문은 node --check로 검증.
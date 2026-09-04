# Stock Dashboard — PROGRESS (세션간 핸드오프) · 최종 갱신 2026-09-03

## ✅ 완료·검증됨 (실통신)
- venv: stock-dashboard/.venv (requests, python-dotenv, fastapi, uvicorn). 실행: `cd app && ../.venv/bin/python xx.py`
- **토스**: 토큰 `POST /oauth2/token`(form, `data=`, NO json CT) → 200. 계좌 `GET /api/v1/accounts`→`{result:[{accountSeq,accountNo}]}`.
  잔고 `GET /api/v1/holdings`(헤더 `X-Tossinvest-Account`) → `{result:{items, marketValue}}`. 잔고/계좌목록 5분 캐시로 rate limit(429) 회피.
- **키움**: 토큰 `POST /oauth2/token` **body 필드 `secretkey`**(appsecret 아님). 잔고 **`POST /api/dostk/acnt` + 헤더 `api-id: kt00018`**,
  body `{acctNo, qry_tp:"2", dmst_stex_tp:"KRX"}`(dmst_stex_tp 필수! 없으면 500). 응답 스칼라 `tot_evlt_amt/tot_prft_rt` + 리스트 `acnt_evlt_remn_indv_tot`(stk_cd,rmnd_qty,pur_pric,cur_prc,evltv_prft,prft_rt).
  ❌ 예제의 `GET /uapi/dostk/inquire-balance TTTC8434R`는 키움 REST 아님(한투 스타일) → 사용금지.
- **DB**: SQLite 적재 OK (`save_holdings` upsert). accounts/holdings 테이블. (all db: /opt/data/dashboard.db)
- **collect_portfolio()**: 키움3+토스9 = **12종목**, 평가손익(`p_pnl`), 수익률(`p_pnl_rate`) 포함.
- **대시보드 UI** (index.html): 요약카드·종목테이블(평가손익/수익률 칼럼)·계좌카드(라벨 수정:"키움 ISA"/"토스", 계좌번호·통화 구분).
  **ECharts CDN(jsdelivr) 도넛 차트 2개**: ① 종목별 평가금액 비중 ② 원화(KRW) vs 외화(USD) 비중. (라벨 잘림 수정: 외화에 긴 $금액 제거)

## 🔧 배포 상태 (docker)
- 컨테이너 **stock-dash** Up, `0.0.0.0:8080`, 이미지 `stock-dash:latest`. 명명 볼륨 `stock_dash_data:/data`.
- docker-compose 미지원(이 호스트) → **`docker run`** 배포. 코드 수정 반영: `docker cp <file> stock-dash:/app/app/<path>` + `docker restart stock-dash`.
- 접속: `http://<NAS_IP>:8080` (브라우저 확인됨 정상 동작).
- git: 로컬 repo init(브랜치 main/develop). **GitHub push는 아직 안 함** (다음 세션에서)
- ⚠️ `docker-compose.yml`의 `./app:/app/app` 볼륨은 이 docker 환경 경로 불일치로 마운트 실패 → `docker run`으로 명명 볼륨만 사용.

## 🔧 유지할 교정
- 키움 base: `https://api.kiwoom.com`(실전). demo면 `mockapi.kiwoom.com.`
- TOSS_BASE_URL 기본 = `https://openapi.tossinvest.com`(api 아님). 경로 `/api/v1/...`.
- CACHE_DIR/DB 폴백: `/data` 없으면 `/opt/data/cache`·`/opt/data` (401/불안정 방지).
- 계좌 라벨: 키움="키움 ISA", 토스="토스". 토스 accountNo는 `179-01-023520`(표시 무시 결정, seq로만 사용).

## ⏭ 다음 세션 (남은 대시보드 개선)
1. **당일 변동 + 시계열 추이선** — **진행 중(DB+수집 완료, 시계열 조회 REST API 완료, 프론트 차트 미연동)**
   - ✅ 시계열 조회 REST API 엔드포인트 구현 (~2026-09-04)
     - `GET /api/portfolio/history?range={7d|30d|90d|all}`: day_snapshots 날짜 오름차순, 차트용 간결 JSON
       `{range, count, dates[], total_values[], total_profit_loss[], profit_rates[]}`. 무효 range→전체 조회. 빈 데이터→200+빈 배열.
       로직: `app/snapshots.py:get_portfolio_history()` (라우터 `main.py`는 호출만).
     - `GET /api/quotes/summary`: quotes 최신 종목별 등락 `{count, quotes[{symbol,current_price,prev_close_price,change_rate,updated_at}]}`.
       로직: `app/snapshots.py:get_quotes_summary()`.
     - 검증: uvicorn 로컬(8091) 실기동, history 7d/all·invalid-range·quotes·빈DB(빈 배열+200) 모두 200 OK.
   - **남음: 프론트(index.html) 차트 연동** (ECharts에 history/quotes 바인딩)
2. **AI 브리핑 카드** → Hermes 직접 처리로 연결 — 미진행 (사용자가 유예)
3. **GitHub push**: Proj_Stock_Dashboard → **완료** (2026-09-04, main 동기화)
4. (선택) 네이버 뉴스 수집 + 변동성 필터링 — 미진행 (사용자가 미룸)

## ✅ 시계열 DB 스키마 + 수집 로직 (~2026-09-04)
- 스키마 재설계: `quotes`(symbol PK, current_price/prev_close_price/change_rate/updated_at),
  `day_snapshots`(snapshot_date UNIQUE, total_evaluation_amount/investment/profit_loss/profit_rate/holdings_json/created_at).
- db._migrate_tables(): 기존 구(舊)스키마(quotes id방식·day_snapshots 항목)를 감지해 DROP 후 재생성(멱등).
- `app/snapshots.py`: collect_portfolio → KRW 환산 총액/손익 → day_snapshots UPSERT(snapshot_date 기준),
  종목별 시세 quotes UPSERT. 실행 ``cd app && ../.venv/bin/python -m snapshots`` (실통신 12종목 검증 OK).
- 종목별 수익률은 브로커 단위 불일치(퍼센트/비율)를 피하려 KRW 손익/원금으로 직접 계산.
- brokers.collect_portfolio에 prev_close/change_rate 필드 추가(전일종가·등락률, 있으면 채움: 키움 prdy_clpr/prdy_ctrt, 토스 best-effort).
- 환율: fx_rates 최신값 > USD_KRW_RATE env > 기본 1350.
- ⚠️ quotes의 prev_close/change_rate는 현재 브로커 응답이 안 줘서 NULL(추이선 시 전용 시세 API 필요).

## 참고
- app/에서 `../.venv/bin/python xx.py` 로 실행해야 import됨.
- /opt/data/.env 에 키: KIWOOM_APP_KEY/SECRET/ACCOUNT_NO, TOSSINVEST_CLIENT_ID/SECRET. (TOSS_ACCOUNT_SEQ는 계좌목록 API로 자동)
- GitHub 저장소 github-repo-std 스킬 표준 사용.
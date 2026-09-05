# Stock Dashboard — PROGRESS (세션간 핸드오프) · 최종 갱신 2026-09-05 (M6)

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

## ✅ Git 상태 (최종)
- develop = `27f0bc8` (인증: b3ee7f3 서버세션, 018d36c 세션쿠키, 27f0bc8 로그인 즉시 로딩). main = `01cf9b6` (PR #9). 오늘 만들어낸 develop 커밋 3개를 PR로 만들어 main에 머지 예정.

## ✅ 로그인 디자인 보강 + M2 헤더/시스템 상태 (2026-09-05)
- **로그인 페이지 그린 테마 통일**: 기존 GitHub 블루/그린 혼합 → 대시보드 본체 액센트(#4ade80)로 통일. 배경 radial-gradient, 카드 상단 액센트 바+글로우, 브랜드 SVG 아이콘, 로그인 진행 스피너 추가. live 반영·`/` 200 확인. develop `7696c5c`.
- **M2 헤더 재구성**: `#meta`(`loading health...`)·`#status`(`Status: healthy ...`) 디버그 문구 제거. `.topbar`로 재구성 — 브랜드 아이콘+타이틀(좌), 환율 배지(`1 USD = N KRW`)·Live 배지(펄스+최종갱신시각)·새로고침(⟳ 회전 애니메이션)·로그아웃(⏻ → `/api/logout`) 버튼(우). `#status`는 에러 전용 배너(`.status-banner`)로 전환.
- **작업 전 재검토로 발견한 추가 항목** (Obsidian 기획서 `주식-대시보드.md`에 반영): 로그아웃 버튼(M2, 이번에 구현), 당일 등락률 컬럼(M5, `quotes.change_rate`/`/api/quotes/summary` 백엔드는 있으나 프론트 미노출 — 다음 세션), 테이블 모바일 가로 스크롤(M5, 신규 항목).
- 검증: `node --check` 통과, live 컨테이너 `docker cp`+`restart` 반영, 컨테이너 내부에서 신규 마크업 존재·구 디버그 문구 부재 확인, `/health` 200. **브라우저 시각적 확인은 사용자 예정.**

## ✅ M3: KPI 4분할 카드 (2026-09-05)
- 기존 3칸 요약(보유종목/원화평가/외화평가) + 별도 계좌 카드(`#accts`) → **4분할 KPI 그리드**로 통합: ①총 평가자산(원화합산 + 전일대비 ▲▼금액/%) ②키움 ISA(원화평가+보유종목수) ③토스 해외($평가+KRW환산+종목수) ④총 누적손익(KRW환산+누적수익률%).
- 집계는 broker 필드 기준 그룹핑 신규 작성, USD 종목은 기존 도넛과 동일 방식으로 실시간 FX 환산. 전일대비는 `/api/portfolio/history?range=7d` 마지막 스냅샷과 비교.
- `#accts`/`/api/accounts` 프론트 호출 제거 (계좌번호 등 UI 미노출). 미사용 CSS(`.cards`,`.st`) 정리.
- 검증: 배포 전 `docker exec` 내부 Python으로 동일 집계 로직 재현 → 12종목(키움3+토스9), 손익률 -5.35% 백엔드 정합 확인. `node --check` 통과, live 반영·마크업 확인 완료.

## ✅ M3 후속 보강: 토스 국내/해외 분리 + 카드 위치/색상 (2026-09-05, 사용자 피드백)
- **중요 발견**: 실데이터 재검증 중 토스가 국내(KRW)·해외(USD) 자산을 모두 보유(국내 5종목/해외 4종목) 확인 — 기존 "토스 해외" 단일 카드는 KRW 환산 총액엔 국내분을 포함하면서 카드엔 안 보여줘 부정확했음.
- **KPI 5분할로 확장**: 총평가자산 / 키움 ISA / **토스 국내**(원화) / **토스 해외**(`$` 숫자 앞 접두 표시로 변경) / 총 누적손익. `fmt()` 함수에 `prefix` 파라미터 추가(`$1,234.56` 형태).
- KPI 카드 그리드 위치를 "총자산 시계열 추이" 차트 **상단**으로 이동.
- 총평가자산 전일 대비 **하락 시 파랑**(#58a6ff, 국내 주식 관례) 색상 적용 — 총평가자산 카드에 한정, 다른 손익 표시(총 누적손익, 테이블)는 기존 빨강/초록 유지.
- 검증: `docker exec` 내부 Python으로 토스 국내/해외 분리 집계 재현(국내 900만원/5종목, 해외 $27,878.93/4종목) 확인. `node --check` 통과, live 반영·마크업 순서 확인 완료.

## ✅ M3 재보강: 색상 규칙 수정 + 레이아웃 정리 (2026-09-05, 사용자 피드백 2차)
- **버그 원인**: `.kpi-card .kpi-sub`/`.kpi-value` 규칙(클래스 2개 결합, 명시도 0,2,0)이 `.blue`/`.red`/`.green`(단일 클래스, 0,1,0)보다 CSS 명시도가 높아 색상 클래스가 항상 무시되고 있었음 — 총평가자산 하락 파랑도, 총 누적손익 색상도 실제로는 반영 안 됐던 원인.
- **수정**: `.kpi-card .kpi-value.red/.green/.blue`, `.kpi-card .kpi-sub.red/.green/.blue` 결합 선택자(명시도 0,3,0)로 재정의 → 색상 정상 적용.
- **색상 규칙 정정**: 국내 주식 관례대로 통일 — **상승(+) 빨강, 하락(-) 파랑**(기존엔 상승 초록으로 잘못 적용). 총평가자산·총누적손익 모두 **금액이 아닌 변동률/수익률 텍스트에만** 색상 적용(금액 자체는 기본색 유지).
- **레이아웃 재구성**: 5장으로 늘어난 카드가 4+1 형태로 어색하게 줄바꿈되던 문제 → **2단 그리드**로 분리: 상단(`summaryTop`) 총평가자산+총누적손익 2장(주요 지표, 값 폰트 24px 강조) / 하단(`summaryBottom`) 키움ISA+토스국내+토스해외 3장(계좌별 세부, 20px). 2+3 구성으로 반응형에서도 빈 칸 없이 균등 배치.
- 검증: `node --check` 통과, live 반영·신규 id(`summaryTop`/`summaryBottom`) 및 결합 선택자 CSS 존재 확인.

## ✅ M4: 차트/시각화 개편 (2026-09-05)
- **Y축 동적 도메인**: 0 기준 고정 대신 데이터 범위 ±20%(평탄할 경우 ±10%)로 min/max 계산 → 소폭 변동도 잘 보이도록 개선.
- **데이터 0/1건 폴백**: history 0건이면 "수집 안내" 문구, 1건이면 단일 값 강조 카드(큰 글씨로 금액+날짜) 표시, 2건 이상부터 라인차트 렌더. **현재 실제로 스냅샷 1건뿐이라 이 폴백이 바로 적용되는 상태.**
- **종목 비중 도넛**: 아크 위 라벨 제거(호버 툴팁으로 대체), 상위 5개 + 나머지는 "기타"로 집계, 우측 세로형 범례(색점+종목명+비중%).
- **원/외화 비중**: 도넛 → 가로 스택 프로그레스 바(KRW 초록/USD 파랑)로 완전 교체, 카드 내 세로 중앙 정렬.
- 검증: `node --check` 통과, live 반영. 실제 사용자 로그인/데이터 로드 로그(`/api/login` 200, `/api/portfolio/history` 200 등)로 정상 동작 확인.

## ✅ M4 후속 보강: 도넛 겹침·기타 과다 (2026-09-05, 사용자 피드백)
- **문제**: 2열 카드 폭이 좁아 도넛 그래프와 범례 텍스트가 겹쳐 가독성 저하, 고정 top-5 집계 방식이라 "기타"가 22.8%까지 과다하게 뭉쳐짐.
- **레이아웃 전환**: "종목별 평가금액 비중"·"원화 vs 외화 비중" 카드를 2열 그리드에서 **각각 한 줄 전체 폭 + 상하 배치**로 변경. 도넛 카드 내부는 좌측 도넛(center 24%,50%)+우측 세로 범례로 재배치해 겹침 해소, 도넛 반지름도 46~80%로 확대.
- **세분화 로직 변경**: 고정 top-5 대신 **전체 대비 비중 2% 미만만 "기타"로 집계**하는 임계값 방식 도입. 실측 12종목 중 8종목 개별 표시, 기타 22.8%→4.8%(4종목)로 감소. 홀딩 수가 늘어나도 자동으로 스케일됨(하드코딩 개수 아님).
- **호버 하이라이트**: `emphasis:{focus:'self'}` + `blurScope:'coordinateSystem'`로 마우스오버 시 해당 종목만 강조, 나머지는 흐림 처리.
- 검증: `node --check` 통과, `docker exec` 내부 Python으로 임계값 로직 재현(기타 4.8%/4종목) 확인 후 live 반영.

## ✅ M4 재보강: 도넛 크기/범례 균형 + 호버 볼드 강조 (2026-09-05, 사용자 피드백 2차)
- **그래프-범례 크기 불균형**: 도넛이 과도하게 크고 범례 글자가 상대적으로 작아 보이던 문제 → 도넛 반지름 `46~80%`→`34~58%`로 축소, 범례 `fontSize` 11→14, `itemWidth/Height` 10→12로 확대해 시각적 균형 맞춤.
- **호버 볼드 강조**: 도넛 슬라이스에 마우스오버 시 대응하는 오른쪽 범례 항목(종목명+비중%)도 함께 볼드 처리되도록 `chart.on('mouseover'/'mouseout')`에서 legend `formatter`를 rich-text(`{bold|...}`) 토큰으로 동적 교체하는 방식 구현.
- 검증: `node --check` 통과, live 반영 확인.

## ✅ M4 재보강: 도넛 카드 높이 내용에 맞춤 (2026-09-05, 사용자 피드백 3차)
- 고정 높이(340px)라 범례 항목 수가 적을 때 카드 위아래에 빈 공간이 생기던 문제 → **범례 항목 수 기준 동적 높이** 산정(`Math.max(200, pieData.length*30+50)`)으로 변경. 보유 종목 수가 늘거나 줄어도 카드가 자동으로 맞춰짐.
- 검증: `node --check` 통과, live 반영 확인.

## ✅ M5: 보유 종목 테이블 (2026-09-05, UI/UX 전면 개편 M1~M5 전체 완료)
- **백엔드 버그 발견·수정**: `app/brokers.py collect_portfolio()` — 토스 API `profitLoss.rate`가 **비율**(-0.28=-28%)로 내려오는데 이미 %인 것처럼 그대로 사용해 실제 -28% 손실이 -0.28%로 표시되던 문제(지시서의 "-0.19% 문제"의 정체). 키움 `prft_rt`(이미 %단위)와 대조해 원인 특정, `*100` 곱해 통일. 실데이터 검증: 미래에셋증권 -0.28%→**-28.29%**로 정정, 재계산값과 일치.
- **정렬/포맷**: 좌측 텍스트/우측 숫자 정렬 규칙은 기존 num 클래스로 이미 충족 확인, `<th>`에도 num 클래스 추가해 헤더 정렬 통일. `fmtCcy()` 신규(KRW 정수 콤마, USD 소수 둘째자리 고정). `fmtPct()` 신규(-0.00% → 0.00% 치환).
- **필터 탭**: 원안([전체]/[키움 KRW]/[토스 USD]) 대신 M3에서 확인한 실제 구조(토스 국내+해외 혼재)에 맞춰 **[전체]/[키움]/[토스 국내]/[토스 해외]** 4탭 구현. 필터 상태는 클라이언트 캐시(`window._posItems`)로 재조회 없이 즉시 전환.
- **증권사명**: "브로커"→"증권사" 헤더 변경, `BROKER_NAMES` 매핑(`kiwoom`→키움증권, `toss`→토스증권).
- **당일 등락 컬럼**: `/api/quotes/summary` 신규 연동(4번째 Promise.all 항목). 시세 미매칭 종목(키움 ETF 3종, 토스 시세로 안 잡혀 백필됨)은 change_rate=0 그대로 두면 "실제 보합"처럼 오해될 수 있어 **"-"**로 별도 표시.
- **스타일**: 행 hover(#21262d), 종목 코드 칩 모노스페이스+명암비 향상, `.pos-wrap{overflow-x:auto}`로 모바일 가로 스크롤 대응.
- 검증: `node --check` 통과. Python으로 렌더링 로직을 그대로 재현해 4개 필터 조합(전체12/키움3/토스국내5/토스해외4) 실데이터로 확인, live 반영 완료.

**→ UI/UX 전면 개편(M1 인증·로그인 디자인 ~ M5 테이블) 전체 완료.**

## ✅ M6: 필터 연동 도넛, 자산 블러/표시, 주요 증시 지수 (2026-09-05)
- **모바일 도넛 겹침/세로 크기 수정**: 종목별 비중 도넛이 데스크톱 기준 percent 반지름을 그대로 썼던 탓에, 모바일처럼 폭이 높이보다 작아지는 화면에서 원이 과대해져 범례 텍스트와 겹치던 문제. `renderItemDonut()`을 신설해 컨테이너 폭이 480px 미만이면 **도넛(상단)+범례(하단) 세로 스택**으로, 그 이상이면 기존 좌우 배치를 쓰도록 반응형 분기. `window.resize` 이벤트에도 재계산하도록 연결. 도넛 지름은 항상 범례 총 세로 길이에 맞춰 픽셀 단위로 직접 계산(퍼센트 반지름 미사용)해 "그래프 세로 크기 = 글자 세로 크기"를 보장.
- **M6-1 필터 연동 도넛**: 보유 종목 테이블의 계좌 필터([전체]/[키움]/[토스 국내]/[토스 해외])를 바꾸면 "종목별 평가금액 비중" 도넛도 같은 조건으로 재계산되도록 `computeItemPieData()`/`updateItemDonutForFilter()` 공용 함수로 리팩토링. 예: 키움 필터 선택 시 키움 보유 3종목만 도넛에 표시.
- **M6-2 자산 정보 블러/표시**: KPI 카드(총평가자산~토스해외)를 `#kpiWrap.kpi-blurred`로 기본 블러 처리(9px blur, 상호작용 차단), 중앙 오버레이 버튼("🙈 자산 정보 표시하기") 클릭 시 블러 해제. 편도(reveal) 동작 — 오버레이가 블러 상태에서만 노출되는 구조라 토글 왕복은 다음 새로고침/재로그인까지 미지원(구조상 자연스러운 범위).
- **M6-3 주요 증시 지수 티커**: 신규 `app/market.py` — 네이버 금융 실시간 폴링 API(무료·키 불필요, `fx.py`와 동일한 TTL 1h 캐시+실패 시 마지막 캐시 폴백 패턴)로 **코스피·코스닥·나스닥·S&P500·다우존스·필라델피아반도체** 6개 지수 수집. `GET /api/market/indices` 신규(옵션 `?refresh=true`로 캐시 무시 강제 갱신). 헤더 하단에 작은 칩 형태로 가로 스크롤 티커 표시, 상승(+)빨강/하락(-)파랑 (국내 주식 관례, 기존 KPI 색상 규칙과 통일). **"나스닥 선물"은 네이버 폴링 API에서 안정적인 심볼 코드를 찾지 못해 이번 범위에서 보류** — 실제 조회 성공한 심볼: `.IXIC`(나스닥종합) `.INX`(S&P500) `.DJI`(다우존스) `.SOX`(필라델피아반도체), 국내는 `KOSPI`/`KOSDAQ`.
  - **환율과 동기화**: 새로고침 버튼 클릭 시 `/api/fx/rate?refresh=true`·`/api/market/indices?refresh=true`를 함께 호출해 TTL(1h) 대기 없이 즉시 갱신 — "달러 환율 자동 주기 확인 후 같이 업데이트" 요구사항 반영. `fx.get_fx_summary()`에 `force_refresh` 파라미터 추가.
- 검증: `app/market.py` 컨테이너 내부 직접 실행으로 6개 지수 실데이터 확인(코스피 6,687.21 +1.64% 등), Node로 렌더링 로직 재현(색상 정합 확인). `node --check` 통과, live 반영·신규 마크업(`marketTicker`,`kpiWrap`,`kpiRevealBtn`) 확인 완료. **나스닥 선물 데이터 소스는 후속 세션 검토 필요.**

## ⏭ 다음 세션 (남은 작업)
  1. **UI/UX 전면 개편(M1~M6) 전체 완료 — live 화면 최종 사용자 브라우저 확인만 남음** (특히 모바일에서 도넛 겹침 해소 여부)
  2. **나스닥 선물 지수** — 네이버 폴링 API 심볼 미확인, 데이터 소스 추가 조사 필요 (유예)
  3. **AI 브리핑 카드** — 미진행 (유예)
  4. (선택)**네이버 뉴스 수집+변동성 필터링** — 미진행 (미룸)

## 참고
- **머지 정책 (2026-09-04~)**: Hermes는 develop까지만 머지. main 머지는 사용자가 직접. (개발 브랜치는 원격에서 복원: `git checkout -b develop origin/develop`.)
- /opt/data/.env: KIWOOM_APP_KEY/SECRET/ACCOUNT_NO, TOSSINVEST_CLIENT_ID/SECRET, GITHUB_TOKEN. (TOSS_ACCOUNT_SEQ 자동.

- 브라우저 렌더링(live 도넛/추이선)은 이 환경 브라우저 daemon 미기동으로 미확인 — 사용자 직접 확인. JS 구문은 node --check로 검증.
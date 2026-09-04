# Stock Dashboard

Kiwoom (국내 ISA) + Toss (해외) 통합 주식 자산 대시보드. Docker 컨테이너로 배포, 브라우저에서 실시간 평가손익·추이선·환율 제공.

## 주요 기능

- **통합 보유 현황**: 키움(국내) + 토스(해외) 12종목, 평가손익/수익률·원/외화 환산 반영 (USD→KRW 실시간 환율)
- **총자산 시계열 추이선**: 대시보드 상단 ECharts Area 차트, 기간 필터 (7일/30일/전체)
- **ECharts 도넛 2개**: 종목별 평가금액 비중, 원화 vs 외화 비중
- **시계열 저장**: `day_snapshots` 일별 스냅샷, `quotes` 시세 캐시
- **일일 자동 수집 크론**: 매일 장마감 시 스냅샷 → 추이선 축적 (Slack+Telegram 리포트)

## API 엔드포인트

- `GET /health` - 상태 확인
- `GET /api/accounts` - 계좌 목록
- `GET /api/portfolio` - 보유 종목 + DB 적재
- `GET /api/portfolio/history?range={7d|30d|90d|all}` - 시계열 (차트용 간결 JSON)
- `GET /api/quotes/summary` - 최신 종목별 시세 캐시
- `GET /api/fx/rate` - 실시간 USD→KRW 환율 (TTL 1h 캐시·폴백 포함)

## 환경 변수 (.env)

- **Broker**: `KIWOOM_APP_KEY/SECRET/ACCOUNT_NO`, `TOSSINVEST_CLIENT_ID/SECRET` + 자동 계좌 seq
- **환율**: `EXCHANGE_RATE_API_URL` (기본 open.er-api.com/v6/latest/USD, 무료·키 없음; 비면 `FX_BASE_URL`)
- **Git**: `GITHUB_TOKEN/USER_ID/USER_EMAIL`
- **Obsidian**: `OBSIDIAN_VAULT_PATH`

## 배포 (docker)

```
docker run -p 8080:8080 --env-file /opt/data/.env -v stock_dash_data:/data stock-dash:latest
```

- 배포 반영: `docker cp <file> stock-dash:/app/app/<path>` + `docker restart stock-dash`
  - ⚠️ `db.py` 포함 필수 (구스키마 자동 마이그레이션)
- 접속: `http://<NAS_IP>:8080`

## Git 구조 (GitFlow)

- `main`(릴리즈) / `develop`(통합 개발) — 원격 2 브랜치만 유지
- feature 브랜치 → develop PR → 머지 → 릴리즈 시 develop→main PR (admin 머지: main 리뷰 1건 보호)
- 작업 후 자동 push, 상태는 `PROGRESS.md`에 기록

## 검증

- 실통신 12종목 수집·적재 OK, 시계열 REST API 전(7d/all·빈DB 200+빈 배열) OK
- 실시간 환율 `/api/fx/rate` 200 (~1356.7, open.er-api), 하드코딩 1350 제거)
- JS 구문 `node --check` OK, live 컨테이너 내부 검증 (호스트에서 curl/wget 불가 → `docker exec stock-dash python ...`)

## TODO

- 당일 변동 보강 (`quotes` prev_close/change_rate NULL → 전용 시세 API)
- AI 브리핑 카드 (유예)
- 네이버 뉴스 수집 (유예)

## 참고

- 세션간 핸드오프: `PROGRESS.md` (최신 상태·이슈·다음 단계)
- 일일 스냅샷 크론: `d97014bf74ee` (매일 06:30 UTC = 한국 15:30, no_agent 스크립트)
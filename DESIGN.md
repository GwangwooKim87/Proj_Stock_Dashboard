# 개인 주식 자산 통합 대시보드 — 시스템 설계서

저사양 NAS(가용 RAM 4GB, 내부 사설 IP 전용·공인 IP 노출 없음) 환경에서
키움증권(국내 ISA)·토스증권(해외주식) 자산을 통합 모니터링하는 웹서비스 + 아침 브리핑 파이프라인.

실시간 웹소켓 불필요, 장중 **15분 폴링 + 일 마감 스냅샷** 방식.

 AI는 DeepSeek v4 Flash, 토큰 소모를 최소화한다.



## 1. 최종 시스템 아키텍처 (컨테이너 구성)

```
                    ┌────────────────────  홈 네트워크 (사설 IP 전용)  ────────────────────┐
                    │                                                                        │
 브라우저/모바일 ──→ http://192.168.x.x:8080 ──→ [ app 컨테이너 ]                    │
 (다크모드 반응형)                                            │  python:3.12-slim        │
                                                       │  FastAPI ─ 대시보드 정적UI       │
                                                                                                              │  스케줄러(15분 폴링·마감·원본적재)  │
                                                                                                              │  AI는 없음 (Hermes Agent가 처리)  │
                                                                                                              │  Throttler(초당호출 제한)        │
                                                                                                              └──────────────┬───────────────────────┘
                                                                                                                    마운트│ (bind mount)
                                                                                                              ┌──────────────┴───────────────────────┐
                                                                                                              │  ./data/ (NAS 스토리지)              │
                                                                                                              │   dashboard.db   (SQLite, 단일파일)  │
                                                                                                              │   cache/          (마지막 확정 캐시)     │
                                                                                                              │   inbox/          (Hermes AI용 원본 feed)│
                                                                                                              └────────────────────────────────────────┘
                                                                                                                                         │
                                                                                          ┌──────────────────┬───────────────────────────┤
                                                                                          ▼                  ▼                           ▼
                                                                                 [ 키움 REST API ]    [ 토스 Open API ]        [ 네이버 금융 뉴스 ]
                                                                                 (국내 ISA, OAuth2)   (OAuth2 client id/secret)     (보유종목 헤드라인·2줄)
                                                                                          │                  │                           │
                                                                                          └─────── 통합 계좌 조회/환산(KRW)  ───────┘      │
                                                                                                                                         ▼
                                                                                                                       [ Hermes Agent ]  (이 환경, 외부 — AI 워커 없음)
                                                                                                                       DeepSeek v4 Flash(OpenRouter) 로
                                                                                                                       보유종목 브리핑 생성 → morning_feed/전송
```

**디자인 판단 (RAM 4GB):**
- **DB는 SQLite 단일파일** 선택. PostgreSQL 컨테이너(RAM 수백 MB)는 저사양에서 무겁고, 본 시스템은 동시 접속·고빈도 쓰기가 아니므로 SQLite가 정답. 15분 폴링이면 쓰기 경합도 무시 가능.
 
- **서비스 단일 컨테이너(`app`)** 만 상시 구동. 웹소켓/별도 nginx/별도 DB/별도 AI 워커를 두지 않아 컨테이너당 RAM 최소화. 4GB에서 ~600MB 수준으로 여유.fast 정적 서빙도 FastAPI가 직접 처리(nginx 불필요). 스케줄러는 FastAPI의 asyncio background task로 상주, 컨테이너 재시작 시 함께 재기동(`restart: unless-stopped`)).
- `mem_limit: 1g` 록(하드 상한) + `--workers 1`로 자원 고정.

## 2. docker-compose 서비스 분할 (RAM 4GB 준수)

`docker-compose.yml` 본문은 프로젝트 루트 참고. 요지:

| 서비스 | 이미지 | 용도 | mem_limit |
|---|---|---|---|
| `app` | `python:3.12-slim` | FastAPI API+UI, 스케줄러, AI 워커, 스로틀러 | 1g |

- 볼륨: `./app:/app`(코드), `./data:/data`(SQLite + 캐시, NAS 영속 스토리지)
- `env_file: .env` — 키/시크릿은 코드 밖 분리 유지
- 포트: `8080:8080` (사설 IP 전용. 공인 포트 노출 없음)
- `TZ=Asia/Seoul` 고정.

**자원 예측 (idle/폴링 시):** app ~300~500MB, OS/기반 ~1GB → 총 ~2GB 이내. 4GB 여유.



## 3. 증권사 연동 — 데이터 수집 흐름 및 API 인터페이스

```
키움(국내 ISA:                        토스(해외주식):
  .env: APP_KEY/APP_SECRET            .env: TOSSINVEST_TOKEN
   │                                      TOSSINVEST_ACCOUNT_SEQ
   ▼                                      │
 [OAuth2 토큰 발급] (JWT access       [Bearer 토큰]  X-Tossinvest-Account 헤더
  + refresh 토큰 갱신·캐시)              │
   │                                      ▼
 [Throttler]  보증 초당 ≤ N회          [Throttler]
   │                                      │
   ▼                                      ▼
 [국내 주식 잔고/예수금/평가손익]     [해외 보유종목/평가손익]
   │  ㅡ 종목명·수량·평단가·현재가          │  symbol·qty·avgPrice·curPrice
   ▼                                      ▼
      ┌────────────  환산 통합 (USD→KRW)  ────────────┐
      │  FX 소스: 실시간 매매기준율(+폴백: 전일 마감 환율)  │
      │  → 모든 계좌를 KRW 기준 단일 포트폴리오로 집계          │
      └──────────────────────────┬──────────────────────────┘
                                 ▼
              SQLite 적재 + 마지막 확정 데이터 cache/ 서빙
```

**모듈 인터페이스 (가상 시그니처):**

```python
# brokers/base.py
class BrokerPort:
    def refresh(self, throttle: Throttler -> list[Holding]:    # 계좌 보유/잔고 폴링
    def sync_quotes(self, symbols, throttle): -> dict[str, Quote]:
    def is_market_open(self, now: datetime) -> bool:      # 장시간 게이트

# brokers/kiwoom.py (REST + OAuth2 JWT)
class KiwoomBroker(BrokerPort):
    TOKEN_URL/ACCOUNT_URL  # OAuth2 access/refresh, access는 런타임 캐시, 만료 시 refresh로 자동 갱신
    # 초당 1회 수준 Throttle 준수 (rate limit 실측치로 튜닝)

# brokers/toss.py
class TossBroker(BrokerPort:
    CLIENT_ID/SECRET(S.env)
    BASE = "https://openapi.tossinvest.com/v1"
    # OAuth2: client id/secret 으로 발급 토큰(runtime 교환) 의 Bearer + X-Tossinvest-Account 헤더
    def _token(self, throttle): str:    # 발급·캐시·만료 자동 갱신
    def list_accounts(self, throttle): -> list[Account]:  # 계좌 목록 자동 수집 (순서 보존)
```

**토큰 관리 구조:**
- 키움: `AppKey/AppSecret`(.env) → **OAuth2** → JWT **access token**(수명 캐시, 만료 자동 갱신 via refresh). secret은 `.env`에만, 코드/로그/UI에 절대 미노출`.
- 토스: 발급 토큰을 `.env` 보관 → `Authorization: Bearer`. 만료 시 재발급 경보 로그.
 발급 시 서버 공인 IP를 해당 증권사에 등록해야 함.

 토스는 client id/secret(.env)으로 OAuth2 토큰을 런타임 교환한다.

 (발급 토큰은 런타임 캐시, .env엔 client id/secret만 보관. 정확한 OAuth 스코프 흐름은 토스 API 문서로 최종 검증 필요.)

**폴링/캐싱 규칙:**
- **장중(정규장 운영시간)만 15분 폴링** (시간당 4회 → API 호출 절감.)
- **장외(야간·주말·공휴일):** API 호출 **차단** → 마지막 확정 데이터 `cache/` 서빙.
- **일 스냅샷:** 국내장 마감(15:30), 미국장 마감(익일 06:00) 시점의 확정 자산을 `day_snapshots`에 적재.



## 4. 토큰 최적화 네이버 뉴스 + Hermes(DeepSeek v4 Flash) 브리핑 파이프라인

**처리 주체:** AI 모듈은 대시보드 컨테이너에 두지 않는다.** 네이버 뉴스 수집·필터링만 대시보드가 수행하고, 브리핑 생성은 **Hermes Agent(이 환경)가 직접** 담당한다(Hermes가 DeepSeek v4 Flash(OpenRouter) 호출). 대시보드는 선별 결과를 `inbox/`·`news_items`에 남기고, Hermes 크론이 이를 읽어 요약 생성 → `morning_feed` 적재 + 텔레그램/위젯 전송.**

**핵심 원칙:** "전 종목 × 뉴스 본문 전체"를 AI에 넣지 않는다.** 선별(감지) → 축약(2줄) → 상위만** 순으로 극소화한다.



```
[종목 전체 N개]
   │
   ▼ 스크린 (로컬 필터, AI 미사용)
  변동성 ±3% 이상  OR  당일 공시/뉴스 감지된 핵심 종목  ──→  선별 종목 S (S < N)
   │
   ▼ 수집 (주식·검색 크롤 + RSS 폴백)
   네이버 금융 뉴스 헤드라인 크롤 → 각 종목별 상위 K건
   │
   ▼ 축약 (컨텍스트 압축)
   뉴스 [제목 + 핵심 2줄 요약] 만 추출  (본문 전체 버림)
   │
   ▼ 입력 구성 (단일 프롬프트, 일괄)
   종목별로 묶은 S×K건의 제목+2줄 텍스트  →  DeepSeek v4 Flash
   │
   ▼ 출력
   모닝 피드 (종목별 1~2줄 요약 + 영향/시사점), JSON or 마크다운
   │
   ├─→  대시보드 상단 "AI 브리핑" 위젯 (SQLite morning_feed 적재)
   └─→  텔레그램 봇 발송 (평일  ​08:00~08:30, 상단 위젯과 동일 내용)
```

**토큰 예산 (비교):**

| 방식 | 입력 토큰(추정) |
|---|---|
| 전 종목(20)×본문 전체 | ~50k+ / 일 |
| **이 방식 (선별 5×뉴스 3×2줄)** | **~2k / 일** |

- 20종목 중 통상 3~8개만 변동성/뉴스로 선별 → 비용 ~1/25 수준.
- 실패 방어: 뉴스 미감지·API 무응답 시 "특이사항 없음"만 출력(추측 금지), AI 호출 자체를 건너뜀.**

**프롬프트 원형(예시):**

```
다음은  [오늘 날짜]  내 보유 종목 중 변동성/뉴스가 감지된 종목들의 요약 새로입니다.
 각 종목의 (1) 핵심 메시지 (2) 한국 시장·내 포지션에 대한 시사점 을 1~2줄로 간결히.
 종목별로 출처 링크를 붙여라. 추측은 금지, 뉴스에 없는 사실은 쓰지 마라.
 없는 종목은 생략하고  "특이사항 없음"만 내라:
--- 종목별 요약 ---
[symbol]:  [제목 — 핵심 2줄]
...
```



## 5. 시계열 DB 스키마 (SQLite 우선)

`schema.sql` 본문 참고 — 핵심 테이블:

- **accounts** — 브로커(kiwoom/toss), 계좌번호, 기준통화
- **holdings** — 계좌별 보유 현황 (수량, 평단가, 현재가, 평가손익)
- **quotes** — 종목 시세 시계열 (가격, 기준통화, KRW 환산가, 수집시각)
- **day_snapshots** — 일자별 총평가액·투자원금·실현/미실현손익·원화/외화 노출 (마감 스냅샷 적재)
- **news_items** — 종목 뉴스 (제목, 2줄 요약, URL, 발행시각)
- **morning_feed** — 모닝 피드 산출물 (날짜, 종목, 요약)
- **fx_rates** — USD→KRW 기준환율 시계열 (실시간 매매기준율/전일 마감 폴백)



## 6. .env 키 자리 (주석 양식)

프로젝트 루트의 `.env`(주석 양식은 `.env.example`)에 아래 키가 주석 처리되어 있다. 실값은 사용자가 직접 채운다:

```
KIWOOM_APP_KEY / KIWOOM_APP_SECRET / KIWOOM_ACCOUNT_NO
TOSSINVEST_CLIENT_ID / TOSSINVEST_CLIENT_SECRET / TOSSINVEST_ACCOUNT_SEQ
FX_BASE_URL
(계좌 번호/표시 순서는 하드코딩하지 않는다 — list_accounts() 로 자동 수집·display_order 정렬)
AI(Hermes 직접 처리)는 별도 DEEPSEEK_API_KEY 불필요 — Hermes가 OpenRouter로 동일 모델 보유.

```
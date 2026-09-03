# Stock Dashboard — PROGRESS (세션간 핸드오프)

## ✅ 검증 완료 (실통신)
- venv: stock-dashboard/.venv (requests, python-dotenv). 실행: `cd app && ../.venv/bin/python xx.py`
- **토스**: 토큰 `POST /oauth2/token`(form data=, NO json CT) → 200. 계좌 `GET /api/v1/accounts`→`{result:[{accountSeq,accountNo}]}`.
  잔고 `GET /api/v1/holdings`(X-Tossinvest-Account) → `{result:{items:[...], marketValue:{amount:{krw}}...}}`. _toss_seq() 자동해석.
- **키움**: 토큰 `POST /oauth2/token` **body 필드 `secretkey`**(appsecret 아님!) → `{token}`(access_token 아님).
  잔고 **`POST /api/dostk/acnt` + 헤더 `api-id: kt00018`**, body `{acctNo, qry_tp:"2", dmst_stex_tp:"KRX"}`.
  응답: `tot_evlt_amt`,`tot_pur_amt`,`tot_evlt_pl`,`tot_prft_rt`(스칼라) + `acnt_evlt_remn_indv_tot`(리스트: stk_cd,stk_nm,rmnd_qty,pur_pric,cur_prc,evltv_prft,prft_rt).
  ❌ 예제의 `GET /uapi/dostk/inquire-balance TTTC8434R`은 키움 REST가 아님(한투 스타일) → 사용금지.
- **collect_portfolio()**: 키움3(추) + 토스9 = **12종목** 통합 성공. 필드 symbol/name/qty/avg_price/cur_price/currency/broker. _to_num() 유틸 존재.

## 🔧 유지할 교정
- 키움 base: https://api.kiwoom.com (실전). _kiwoom_base(): KIWOOM_SERVER=demo → mockapi.
- TOSS_BASE_URL 기본 = https://openapi.tossinvest.com (api 아님). 계좌/잔고 경로 /api/v1/....
- CACHE_DIR 폴백: /data 없으면 /opt/data/cache (토큰 재발급 race→401 방지). _DATA_ROOT 로직 추가됨.
- 키움 isa 계좌번호=KIWOOM_ACCOUNT_NO(.env, 8자리=65992116). 토스 seq는 계좌목록 자동.

## ⏭ 다음 세션 (5분 분기)
1. main.py 에 `/api/portfolio` 엔드포인트 추가 → collect_portfolio() 반환 (대시보드 종목 표시).
2. DB 적재: holdings/quotes 테이블에 collect_portfolio 결과 upsert (db.py 이용).
3. (선택) 아침 요약 → Hermes 크론 / 스케줄러.
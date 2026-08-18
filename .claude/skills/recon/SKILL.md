---
name: recon
description: 웹 대상 External Recon 절차(정보수집·서비스식별·기술스택추정·Endpoint 탐색·Attack Surface 정리·취약점 후보 생성)와 표준 출력 포맷. recon-agent가 정찰 작업을 시작할 때 로드해서 이 절차를 따른다. PTES Reconnaissance / OWASP WSTG Information Gathering을 뼈대로 하고, 실전 경험으로 보완된 체크리스트다.
---

# Recon Skill — External Recon 절차 (Phase 1)

이 skill은 **웹 진입점 기준 정찰(Phase 1)** 만 다룬다. foothold 이후 로컬 시스템 정찰(Phase 2)은 범위 밖이다.

절차는 순서대로 진행하되, 각 단계는 "시도 → 결과(성공/실패/스킵 사유) 기록"이 원칙이다. 무언가를 못 찾았다는 것도 유효한 결과다 — 조용히 넘어가지 말고 반드시 기록한다.

출력은 dast-harness의 `AgentResult` JSON이다 (`reference/output-contract.md`).
아래 절차에서 **"씨앗으로 남긴다"**는 `request_seeds[]`에 항목 하나를 넣는다는 뜻이고,
**"finding으로 남긴다"**는 `findings[]`에 넣는다는 뜻이다.

> 예전에는 `Observed`/`Potential Attack Surface` 두 섹션의 endpoint 표기를 문자
> 그대로 맞춰야 했다. 구조화된 씨앗을 내면 그 규칙이 필요 없어진다 — 표기가
> 어긋날 자리가 없다. 후속 Agent는 `params[].location`으로 자기 몫을 걸러간다.

**타겟으로 나가는 요청은 전부 `dast-harness probe`를 지난다.** curl을 직접 쓰지
않는 이유는 `reference/tools.json`의 `_porting_note`에 있다. 사용 가능한 도구는
전부 그 파일에 정의되어 있고, 아래에서 도구를 언급할 때는 그 정의를 그대로 따른다.

## Step 0. Scope 확인 (필수, 항상 먼저)

- `target`이 주어진 `scope` 안에 있는지 확인한다.
- 벗어나거나 애매하면 이후 단계를 진행하지 않고 `Notes`(아래 "막히는 경우" 참고)에 기록 후 중단한다.

## Step 1. 기본 정보 수집 (Passive-leaning)

`probe`(타겟 대상)와 `nslookup`/`whois`/WebSearch(타겟에 요청이 안 나가는 것)로:
- 최상위 페이지 응답 (상태 코드, `Server`/`X-Powered-By`/`Via` 등 응답 헤더, HTML 내 메타 정보)
- `robots.txt`, `sitemap.xml`, `/.well-known/security.txt`
- 대상이 도메인이면 `nslookup`/`whois`로 기본 DNS/등록 정보 확인 (IP 직접 대상이면 스킵)
- WebSearch로 대상 도메인 관련 공개 정보(서브도메인 언급, 기술 블로그, 채용공고의 기술스택 언급 등) — 공격적 스캔이 아닌 공개 정보 조회 수준

> 위 네 경로는 한 번에 묶어 보낸다 — `probe`는 배치를 받으므로 프로세스를 네 번
> 띄울 이유가 없다. `WebFetch`가 http를 https로 강제 업그레이드하던 문제도 여기서는
> 없다: `probe`는 준 URL을 그대로 보낸다.

## Step 2. 서비스/포트 식별

1. 먼저 HTTP 기반 추정부터: 대상이 응답하는 스킴/포트(URL에 명시된 것, 리다이렉트 체인)를 확인하고, 응답 헤더/에러 페이지/TLS 인증서 정보에서 드러나는 서버 소프트웨어·버전 단서를 `Observed`에 한 줄로 기록한다 (예: `Apache HTTP Server`). 확정이 아니라 추정이면 문구에 드러낸다 (예: `Apache HTTP Server (추정, Server 헤더 기반)`).
2. **포트 탐색은 이 agent의 범위 밖이다.** `nmap`은 도구 목록에서 빠졌다 —
   dast-harness의 안전 경계가 호스트 단위라 포트 스캔을 통과시킬 통로가 없기
   때문이다(`tools.json`의 `_removed` 참고). 주어진 URL의 포트 외에 다른 포트가
   의심되면 **추측하지 말고** `coverage.skip_reasons`에 `{"port-scan-out-of-scope": 1}`
   로 남기고 Orchestrator에게 보고한다.

## Step 3. 기술 스택 추정

다음 단서를 근거로 확인한다:
- HTTP 응답 헤더 (`X-Powered-By`, `Set-Cookie` 이름 패턴 — 예: `PHPSESSID`, `JSESSIONID`, `laravel_session`)
- HTML 메타 태그(`generator`), 정적 자원 경로 패턴(`/wp-content/`, `/_next/`, `/static/django/` 등)
- 에러 페이지 시그니처 (스택트레이스, 프레임워크 특유 에러 포맷)
- JS 번들 내 라이브러리 시그니처 (파일명, 주석, 소스맵 존재 여부)

기술 스택 추정은 그 자체로 씨앗이나 finding이 아니다. 다음 단계의 판단 근거로 쓰고,
노출로 볼 만한 것(예: 버전이 박힌 `X-Powered-By`)만 `findings`에 넣되
`category`는 `information-disclosure`, `confidence`는 근거의 강도에 맞춘다.

## Step 4. Endpoint 탐색

**먼저 수동적(passive) 방법을 우선순위 순서로 전부 시도한다:**
1. `robots.txt` / `sitemap.xml`에 명시된 경로
2. 최상위 페이지 및 그 하위 페이지의 `<a href>`, `<form action>` 파싱으로 얻은 내부 링크
3. JS 파일(특히 번들) 안의 문자열에서 API 경로 패턴 추출 (예: `/api/`, `/v1/`, fetch/axios 호출 문자열)
4. 공개 API 문서 경로 관례 확인 (`/swagger.json`, `/openapi.json`, `/api-docs`, `/graphql`)
5. Wayback Machine 등 공개 아카이브(WebFetch 가능 범위 내)로 과거 노출 경로 확인

찾은 endpoint를 **씨앗으로 남긴다.** 형식은 `reference/output-contract.md`.
씨앗은 모양이 아니라 **실제로 보낼 수 있는 요청**이므로, 관측한 값을 지어내지 말고
그대로 넣는다 (`/api/user?id=42` → `params[{name:"id", location:"query", value:"42",
type:"int"}]`). `source`에 어디서 찾았는지 남긴다 — `link`/`form`/`robots.txt`/`js`/
`sitemap`/`guess`.

응답 본문 전체는 저장하지 않는다. 증거로 쓸 교환만 `findings[].evidence`에 넣는다.

**워드리스트 브루트포스는 이 agent의 범위 밖이다.** `ffuf`는 도구 목록에서 빠졌다
(`tools.json`의 `_removed` 참고). `probe`는 배치 20건 상한이라 퍼징용이 아니다.
수동적 방법으로 부족하면 **추측한 경로를 지어내지 말고** `coverage.skip_reasons`에
`{"active-discovery-out-of-scope": 1}`로 남긴다.

> 관례 경로 몇 개(`/swagger.json`, `/openapi.json`, `/api-docs`, `/graphql`)를
> 확인하는 것은 브루트포스가 아니라 위 4번이다 — 그건 계속 한다. 다른 건 20건
> 한도 안에서 한 배치로 묶어 보낸다.

## Step 5. Attack Surface 정리

**분류를 손으로 붙이지 않는다.** 후속 Agent는 씨앗의 구조에서 자기 몫을 걸러간다:

```
params[].location == "path"            → IDOR/Authorization Agent
params[].location in ("query","body")  → Injection Agent
```

그러니 이 단계에서 할 일은 태깅이 아니라 **씨앗의 파라미터를 정확히 채웠는지
확인하는 것**이다. `location`과 `type`이 틀리면 후속 Agent가 엉뚱한 데를 찌른다.
아래 세 관점은 그 확인을 위한 체크리스트로만 쓴다:

- **Injection 관점**: 사용자 입력이 서버로 전달되는 지점 (쿼리 파라미터, 폼 필드, JSON body 필드, 헤더 반영 등) → **Injection Agent**
- **IDOR·Authorization 관점**: 객체 참조가 노출되는 지점(숫자 ID, UUID, 파일명 등 — 사용자별로 달라 보이는 리소스)과, 로그인/세션/권한 분기가 일어나는 지점(로그인 폼, 관리자 페이지, OAuth 콜백, 비밀번호 재설정)을 함께 묶는다 — "내 리소스가 아닌 걸 볼 수 있는가"와 "권한 없이 접근할 수 있는가"는 같은 Agent가 다룬다 → **IDOR/Authorization Agent**
- **Web Logic 관점**: 비즈니스 로직/워크플로우상의 결함이 의심되는 지점 — 가격·수량·할인 등 클라이언트가 값을 지정할 수 있는 필드, 다단계 절차(주문→결제→확인 등)를 건너뛰거나 순서를 바꿀 수 있어 보이는 흐름, 반복 제한이 없어 보이는 민감한 액션 → **Web Logic Agent**

관점마다 "이 씨앗에 그걸 시험할 파라미터가 실제로 들어 있는가"를 확인한다.
없으면 씨앗이 덜 채워진 것이다.

## Step 6. 정찰이 직접 찾은 것만 finding으로

**"검사 필요" 후보 목록은 더 이상 만들지 않는다.** 그건 씨앗이 이미 말하고 있고,
후속 Agent가 구조에서 걸러간다 (Step 5).

여기서 만드는 건 **정찰만이 찾을 수 있는 실제 취약점**이다. 예: robots.txt가
비공개 경로를 광고하는데 그 경로가 인증 없이 열려 있다.

`findings[]`에 넣을 때:

- **확정 진술을 하지 않는 원칙은 그대로다.** 다만 표현을 "검사 필요"로 얼버무리는
  대신 `confidence`로 말한다 — `confirmed`(첨부한 요청/응답만 보면 누구나 같은 결론)
  / `firm`(증거는 명확하나 판단이 한 단계 들어감) / `tentative`(정황뿐, 사람 확인 필요)
- **`confirmed`가 아니면 왜 낮췄는지 `rationale`에 적는다**
- `severity`는 "진짜라면 공격자가 무엇을 할 수 있나"로만 정한다. 얼마나 확실한지는
  `confidence`가 따로 말하므로 여기 섞지 않는다
- `evidence`는 항상 필수다. **요청 하나만 담긴 evidence는 대개 증거가 아니다** —
  "정상은 이런데 여기서는 이렇다"가 보여야 한다

절대 하지 않는 것: 후보를 검증하겠다고 실제 payload를 보내는 것. 그건 후속 전문
Agent(Injection / IDOR·Authorization / Web Logic)의 역할이다. 정찰이 보내는 요청은
조회성이다.

## Step 7. 저장, 자가 검증, 보고

1. 전체 결과를 `AgentResult` JSON으로 저장한다 (`reference/output-contract.md`).
   막힌 점은 `coverage.skip_reasons`에 남긴다 — 자유 텍스트 `Notes` 대신 구조로.
2. 저장 경로·run 이력 규칙은 `reference/output-path-convention.md`를 따른다
   (최신본 `recon-output/<target-slug>/findings.json` + `runs/<timestamp>/` 스냅샷).
3. **저장 직후 계약 검사를 실행한다**: `dast-harness ingest <저장한 파일 경로>`.
   거부되면 메시지가 곧 수정 지시다 — 어느 finding의 어느 필드가 왜 틀렸고 뭐가
   허용되는지 알려주므로 그대로 고쳐서 다시 검사한다. 계속 실패하면 사유를 보고에
   적고 그대로 끝낸다 (무한 반복하지 않는다).
4. 연습 타겟(`targets/vulnerable_app`)이었다면 자가 채점도 한다:
   `python -m dast_harness.validate --ingest <파일>`. `FALSE POSITIVES`가 있으면
   그건 감점이다 — 멀쩡하다고 문서화된 엔드포인트를 취약하다고 보고한 것이다.
5. 대화 응답에는 파일 경로 + 요약(씨앗 수, finding 수, `ingest` 통과 여부, 채점
   결과, `blocked` 유무)만 짧게 남긴다.

## 막히는 경우

- 같은 조회를 반복해도 새로운 정보가 안 나오면 멈추고 다음 단계로 넘어간다 (같은 액션을 무한 반복하지 않는다).
- 스코프 밖으로 나가야 확인 가능한 경우, 시도하지 말고 `coverage.skip_reasons`에
  남긴다. `probe`에 넣으면 어차피 거부되고 `completion.blocked`에 기록된다 —
  **그 기록을 지우지 않는다.**
- 판단이 애매한 기술스택/취약점 후보는 문구에 "추정"을 명시하되, 스스로 확정 짓지 않는다.

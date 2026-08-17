---
name: recon
description: 웹 대상 External Recon 절차(정보수집·서비스식별·기술스택추정·Endpoint 탐색·Attack Surface 정리·취약점 후보 생성)와 표준 출력 포맷. recon-agent가 정찰 작업을 시작할 때 로드해서 이 절차를 따른다. PTES Reconnaissance / OWASP WSTG Information Gathering을 뼈대로 하고, 실전 경험으로 보완된 체크리스트다.
---

# Recon Skill — External Recon 절차 (Phase 1)

이 skill은 **웹 진입점 기준 정찰(Phase 1)** 만 다룬다. foothold 이후 로컬 시스템 정찰(Phase 2)은 범위 밖이다.

절차는 순서대로 진행하되, 각 단계는 "시도 → 결과(성공/실패/스킵 사유) 기록"이 원칙이다. 무언가를 못 찾았다는 것도 유효한 결과다 — 조용히 넘어가지 말고 반드시 기록한다.

현재 채택된 출력 포맷은 `Target / Observed / Potential Attack Surface` 3단 텍스트다 (`reference/attack-surface-schema.md` 후보 A'). 아래 절차에서 "기록한다"는 이 포맷 중 해당하는 섹션에 한 줄로 적는다는 뜻이다. **`Observed`와 `Potential Attack Surface`에서 같은 endpoint를 가리킬 때는 문자열을 완전히 동일하게 쓴다** — Orchestrator가 이 둘을 문자열 매칭으로 연결해서 다음 Agent에게 최소한만 넘기기 때문이다 (스키마 문서의 "Orchestrator가 최소 컨텍스트를 추리는 방법" 참고).

사용 가능한 도구(이름·실행위치·호출형식·플래그·wordlist·제한값)는 전부 `reference/tools.json`에 정의되어 있다. 아래 절차에서 도구를 언급할 때는 그 파일의 정의를 그대로 따른다 — 플래그나 경로를 여기 별도로 적지 않는다.

## Step 0. Scope 확인 (필수, 항상 먼저)

- `target`이 주어진 `scope` 안에 있는지 확인한다.
- 벗어나거나 애매하면 이후 단계를 진행하지 않고 `Notes`(아래 "막히는 경우" 참고)에 기록 후 중단한다.

## Step 1. 기본 정보 수집 (Passive-leaning)

WebFetch/WebSearch/curl/nslookup/whois로 확인 가능한 범위에서:
- 최상위 페이지 응답 (상태 코드, `Server`/`X-Powered-By`/`Via` 등 응답 헤더, HTML 내 메타 정보) — `WebFetch`가 실패하면(예: 순수 HTTP 대상) `curl -sI`/`curl -s`로 재시도
- `robots.txt`, `sitemap.xml`, `/.well-known/security.txt`
- 대상이 도메인이면 `nslookup`/`whois`로 기본 DNS/등록 정보 확인 (IP 직접 대상이면 스킵)
- WebSearch로 대상 도메인 관련 공개 정보(서브도메인 언급, 기술 블로그, 채용공고의 기술스택 언급 등) — 공격적 스캔이 아닌 공개 정보 조회 수준

> `WebFetch`가 http를 https로 강제 업그레이드해서 실패하는 경우, 같은 요청을 `curl`로 재시도한다 (GET/HEAD만, Safety Gate 참고).

## Step 2. 서비스/포트 식별

1. 먼저 HTTP 기반 추정부터: 대상이 응답하는 스킴/포트(URL에 명시된 것, 리다이렉트 체인)를 확인하고, 응답 헤더/에러 페이지/TLS 인증서 정보에서 드러나는 서버 소프트웨어·버전 단서를 `Observed`에 한 줄로 기록한다 (예: `Apache HTTP Server`). 확정이 아니라 추정이면 문구에 드러낸다 (예: `Apache HTTP Server (추정, Server 헤더 기반)`).
2. 대상이 어떤 포트를 열어놨는지 자체가 불확실하면(이미 아는 포트 하나만 확인하는 걸로는 부족하면) `tools.json`의 `nmap` 정의(호출 형식·고정 플래그)를 그대로 따라 실행한다. 결과에서 열린 포트/서비스/버전을 `Observed`에 한 줄씩 추가한다. nmap 실행도 능동 요청이므로 `execution_log`에 남긴다.

## Step 3. 기술 스택 추정

다음 단서를 근거로 확인한다:
- HTTP 응답 헤더 (`X-Powered-By`, `Set-Cookie` 이름 패턴 — 예: `PHPSESSID`, `JSESSIONID`, `laravel_session`)
- HTML 메타 태그(`generator`), 정적 자원 경로 패턴(`/wp-content/`, `/_next/`, `/static/django/` 등)
- 에러 페이지 시그니처 (스택트레이스, 프레임워크 특유 에러 포맷)
- JS 번들 내 라이브러리 시그니처 (파일명, 주석, 소스맵 존재 여부)

각 항목을 `Observed`에 한 줄씩 추가한다. 근거가 한눈에 안 보이는 항목이면 괄호로 짧게 덧붙인다 (예: `PHP (PHPSESSID 쿠키 관찰)`).

## Step 4. Endpoint 탐색

**먼저 수동적(passive) 방법을 우선순위 순서로 전부 시도한다:**
1. `robots.txt` / `sitemap.xml`에 명시된 경로
2. 최상위 페이지 및 그 하위 페이지의 `<a href>`, `<form action>` 파싱으로 얻은 내부 링크
3. JS 파일(특히 번들) 안의 문자열에서 API 경로 패턴 추출 (예: `/api/`, `/v1/`, fetch/axios 호출 문자열)
4. 공개 API 문서 경로 관례 확인 (`/swagger.json`, `/openapi.json`, `/api-docs`, `/graphql`)
5. Wayback Machine 등 공개 아카이브(WebFetch 가능 범위 내)로 과거 노출 경로 확인

찾은 endpoint를 `Observed`에 한 줄씩 추가한다 (`/api/user endpoint` 처럼). 파라미터가 있고 다음 단계(Step 5/6)에서 중요해 보이면 endpoint 옆에 짧게 덧붙인다 (예: `/api/user?id= endpoint (숫자 id 파라미터)`). 응답 본문 전체는 저장하지 않는다 — 필요한 스니펫만 인용한다.

**수동적 방법으로 찾은 게 부족해 보이면(예: 링크가 거의 없는 앱), `tools.json`의 `ffuf` 정의대로 능동 탐색을 추가한다** — wordlist·스레드·타임아웃은 그 파일에 정해진 값만 쓴다. 발견된 경로도 `Observed`에 같은 방식으로 추가하고, `discovered_via`를 "ffuf"로 남긴다.

> 수동적 방법을 건너뛰고 바로 ffuf부터 쓰지 않는다 — 링크로 이미 찾을 수 있는 걸 굳이 능동 요청으로 다시 찾을 필요는 없다 (불필요한 요청 최소화 원칙).

## Step 5. Attack Surface 정리

Step 4에서 모은 endpoint들을 아래 세 관점으로 **분류/태깅**한다 (하나의 endpoint가 여러 관점에 동시에 속할 수 있다). 이 세 관점은 실제 존재하는 후속 전문 Agent(Injection Agent / IDOR·Authorization Agent / Web Logic Agent)와 1:1로 대응한다 — 필요시 이 목록에 카테고리가 추가될 수 있다:

- **Injection 관점**: 사용자 입력이 서버로 전달되는 지점 (쿼리 파라미터, 폼 필드, JSON body 필드, 헤더 반영 등) → **Injection Agent**
- **IDOR·Authorization 관점**: 객체 참조가 노출되는 지점(숫자 ID, UUID, 파일명 등 — 사용자별로 달라 보이는 리소스)과, 로그인/세션/권한 분기가 일어나는 지점(로그인 폼, 관리자 페이지, OAuth 콜백, 비밀번호 재설정)을 함께 묶는다 — "내 리소스가 아닌 걸 볼 수 있는가"와 "권한 없이 접근할 수 있는가"는 같은 Agent가 다룬다 → **IDOR/Authorization Agent**
- **Web Logic 관점**: 비즈니스 로직/워크플로우상의 결함이 의심되는 지점 — 가격·수량·할인 등 클라이언트가 값을 지정할 수 있는 필드, 다단계 절차(주문→결제→확인 등)를 건너뛰거나 순서를 바꿀 수 있어 보이는 흐름, 반복 제한이 없어 보이는 민감한 액션 → **Web Logic Agent**

이 분류가 바로 다음 단계(취약점 후보 생성)와 후속 전문 Agent 라우팅의 근거가 되므로, **근거(evidence) 없이 분류하지 않는다.**

## Step 6. 취약점 후보 생성 (Potential Attack Surface)

Step 5의 분류를 바탕으로 `Potential Attack Surface` 섹션을 만든다. 형식은 `<endpoint> → <카테고리>(<신뢰도>) 검사 필요 (근거)`:

```
- /search?q= → Injection(강함) 검사 필요 (q 파라미터 값이 응답에 그대로 반영됨)
- /api/user?id= → IDOR/Authorization(강함) 검사 필요 (id만 바꿔서 타 사용자 정보 조회됨)
- /admin → IDOR/Authorization(보통) 검사 필요
- /api/order?price=&qty= → Web Logic(약함) 검사 필요
```

- 반드시 **가설** 톤이다 ("검사 필요"이지 "취약하다"가 아니다). 확정 진술을 하지 않는다.
- 카테고리는 `Injection` / `IDOR/Authorization` / `Web Logic` / 필요시 `Other`.
- **신뢰도는 필수다** — `(강함)` / `(보통)` / `(약함)` 중 하나를 카테고리 뒤에 반드시 붙인다:
  - `강함`: 반응/에러/직접 관찰로 근거가 분명함
  - `보통`: 정황상 의심되지만 직접 확인은 못 함 (예: endpoint 이름/구조 기반 추정)
  - `약함`: 근거가 약하지만 후보로는 남길 만함
  - (이전엔 "근거가 자명하면 생략 가능"이었지만, Orchestrator가 신뢰도로 호출 여부를 거를 수 있어야 해서 이제 항상 표기한다.)
- **endpoint 표기는 `Observed`에 적은 것과 문자 그대로 동일하게 쓴다.** Orchestrator가 이 문자열로 두 섹션을 연결하므로 표기가 어긋나면 안 된다.
- **한 줄에는 endpoint 하나, 카테고리 하나만 담는다.** `/vulnerabilities/xss_r/, /vulnerabilities/xss_s/ → Injection(보통) 검사 필요`처럼 여러 endpoint를 쉼표로 묶거나, 하나의 endpoint에 대해 두 카테고리를 한 줄에 같이 적지 않는다 — `Observed`와의 문자열 매칭이 깨져서 Orchestrator가 최소 컨텍스트를 추릴 수 없게 된다. 여러 endpoint가 같은 근거를 공유하거나, 하나의 endpoint가 여러 카테고리에 걸치면(Step 5 참고) 줄을 그만큼 나눠서 적는다.
- 근거는 한 줄로 짧게 덧붙인다 (예: `q 파라미터 값이 응답에 그대로 반영됨`). `강함`인데 근거가 없으면 안 된다 — 최소한 왜 강함인지는 한 줄 있어야 한다. `보통`/`약함`은 근거가 짧아도 된다.

절대 하지 않는 것: 후보를 검증하겠다고 실제 payload를 보내는 것. 그건 후속 전문 Agent(Injection / IDOR·Authorization / Web Logic Agent)의 역할이다.

## Step 7. 저장, 자가 검증, 보고

1. 전체 결과를 `Target / Observed / Potential Attack Surface` 3단 포맷(`reference/attack-surface-schema.md` 후보 A')으로 저장한다. 막힌 점이 있었다면 `Notes` 섹션을 추가해 남긴다.
2. 저장 경로·파일명(`.md` 또는 `.txt`)·run 이력 보존 규칙은 `reference/output-path-convention.md`를 따른다 (최신본 `recon-output/<target-slug>/attack-surface.<ext>` + `runs/<timestamp>/` 스냅샷 영구 보존).
3. **저장 직후 `tools.json`의 `validate_attack_surface` 정의대로 자가 검증을 실행한다**: `python tools/validate_attack_surface.py <저장한 파일 경로>`. 위반이 나오면 지적된 줄을 규칙(신뢰도 필수, endpoint 표기 일관성)에 맞게 고치고 다시 검증한다. 계속 실패하면 `Notes`에 사유를 남기고 그대로 보고한다 (무한 반복하지 않는다).
4. 대화 응답에는 파일 경로 + 요약(발견한 endpoint 수, 후보 수, 검증 통과 여부, Notes 유무)만 짧게 남긴다.

## 막히는 경우

- 같은 조회를 반복해도 새로운 정보가 안 나오면 멈추고 다음 단계로 넘어간다 (같은 액션을 무한 반복하지 않는다).
- 스코프 밖으로 나가야 확인 가능한 경우, 시도하지 말고 결과 파일 맨 아래 `Notes:` 섹션에 남긴다.
- 판단이 애매한 기술스택/취약점 후보는 문구에 "추정"을 명시하되, 스스로 확정 짓지 않는다.

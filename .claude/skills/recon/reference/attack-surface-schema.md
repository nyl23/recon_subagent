# Attack Surface 표준 출력 스키마 (Phase 1 / External Recon)

recon-agent가 산출하는 Attack Surface 결과물의 구조 정의다. 이 문서는 recon skill(`../SKILL.md`)에서 참조된다.

> **✅ 채택**: 후보 A'(A를 다듬은 버전)로 결정됨 (후보 B는 재검토 후보로 아래에 보존). `SKILL.md`는 이미 A' 기준으로 갱신되어 있다.
>
> **카테고리 체계**: 후속 전문 Agent는 **Injection Agent / IDOR·Authorization Agent / Web Logic Agent** 3종 (+ 필요시 추가). IDOR와 Authorization은 별개 Agent가 아니라 하나로 합쳐져 있다. 아래 예시·스펙은 이 체계로 갱신되어 있다.

## 후보 A' — 단순 텍스트 + 필수 신뢰도 + endpoint 표기 일관성 (채택됨)

원래 후보 A(Target / Observed / Potential Attack Surface 3단 텍스트)에 두 가지만 더한 것. JSON(후보 B)으로 안 가고도, Orchestrator가 다음 Agent에게 최소 정보만 추려 넘길 수 있게 하는 게 목적이다.

실제 예시:

```
Target: localhost:8080

Observed:
- Apache HTTP Server
- /api/user?id= endpoint (숫자 id 파라미터, 소유권 확인 없이 다른 사용자 정보 반환)
- /search?q= endpoint (q 값이 응답 본문에 그대로 반영됨)
- /admin endpoint (인증 없이 접근 가능)

Potential Attack Surface:
- /search?q= → Injection(강함) 검사 필요 (q 파라미터 값이 응답에 그대로 반영됨)
- /api/user?id= → IDOR/Authorization(강함) 검사 필요 (id만 바꿔서 타 사용자 정보 조회됨)
- /admin → IDOR/Authorization(보통) 검사 필요
```

### 추가 규칙 두 가지

**1. 신뢰도 표기는 이제 필수다.** 카테고리 뒤에 괄호로 3단계 중 하나를 반드시 붙인다:
- `(강함)` — 반응/에러/직접 관찰로 근거가 분명함 (예: 파라미터가 에러를 유발, 인증 없이 민감 기능 접근 확인됨)
- `(보통)` — 정황상 의심되지만 직접 확인은 못 함 (예: endpoint 이름이나 구조상 의심)
- `(약함)` — 근거가 약하지만 후보로는 남길 만함

기존처럼 "근거가 자명하면 생략"은 더 이상 허용하지 않는다 — Orchestrator가 이 값으로 "부를 가치가 있는지"를 기계적으로 거를 수 있어야 하기 때문이다 (예: `(약함)` 후보는 스킵하는 정책을 Orchestrator가 나중에 둘 수 있음).

**2. `Potential Attack Surface`의 endpoint 표기는 `Observed`에 적은 것과 문자 그대로 동일해야 한다.** (`/api/user?id=`이면 두 섹션 다 정확히 `/api/user?id=`로 — 공백/대소문자/줄임 없이.) 이래야 Orchestrator가 endpoint 문자열로 두 섹션을 연결(grep)할 수 있다.

**3. 한 줄에는 endpoint 하나, 카테고리 하나만 담는다.** 여러 endpoint를 쉼표로 묶은 줄(예: `/a/, /b/, /c/ → Injection(보통) 검사 필요`)은 규칙 2를 어기게 된다 — 묶인 문자열 전체가 `Observed`에 그대로 나타날 일이 거의 없기 때문이다. endpoint별로, 카테고리별로 줄을 나눈다.

### Orchestrator가 최소 컨텍스트를 추리는 방법 (JSON 없이)

전체 `attack-surface.md`를 다음 Agent에게 통째로 넘기지 않는다. 대신:

1. `Potential Attack Surface`에서 호출할 카테고리로 필터한다 (예: `Injection` 포함된 줄만).
2. 그 줄에서 endpoint 문자열을 뽑는다 (예: `/search?q=`).
3. `Observed`에서 같은 endpoint 문자열이 포함된 줄(들)을 찾는다.
4. **2번 줄(후보) + 3번 줄(관련 관찰 사실) + `Target`** 만 다음 Agent에게 전달한다.

DVWA 테스트 실제 사례로 보면, Injection Agent에게는 이 정도만 넘기면 된다:
```
Target: http://127.0.0.1:8081
- /vulnerabilities/sqli/ → Injection(보통) 검사 필요 (모듈명 기반 SQL 인젝션 데모로 추정)
```
전체 파일(16개 후보, `Observed` 22줄)을 다 안 넘기고 이 3줄만 넘기면 되므로, JSON의 `context_for_agent` 없이도 실질적으로 같은 효과를 낸다.

**확장 (필요할 때만)**: 진행 중 막히거나(스코프 밖, 도구 부재, 판단 불가) 후속 Agent에게 남길 특이사항이 있으면 맨 아래 `Notes:` 섹션을 덧붙인다. 없으면 생략한다.
```
Notes:
- 포트 스캔 필요하지만 능동 스캔 도구 없어 확인 못함
```

**장점**
- 사람이 한눈에 읽기 쉽고, 작성/생성 토큰 비용이 여전히 적다 (필드 몇 개 추가한 정도)
- 신뢰도가 필수화되어 "부를 가치가 있는가"를 Orchestrator가 기계적으로 거를 수 있음
- endpoint 표기 일관성 덕분에, JSON 없이도 grep 수준으로 Agent별 최소 컨텍스트 추출이 가능함 (위 방법 참고)

**남은 단점 (여전히 후보 B보다 약한 부분)**
- 완전한 기계 파싱 안정성은 아니다 — recon-agent가 규칙(신뢰도 필수, 표기 일관성)을 안 지키면 grep이 깨질 수 있다. 강제 검증 스크립트는 아직 없음.
- 되돌릴 수 없는 행동(실행 로그) 추적은 여전히 별도 파일(`execution_log.jsonl`)이지 이 문서 안에 통합되어 있지 않다 (다만 이건 애초에 별도 파일로 관리하기로 한 설계라 문제라기보단 그대로 유지).

## 후보 B — 상세 JSON 스키마 (보류, 재검토 후보)

**지금은 채택하지 않음.** Phase 1을 후보 A'로 실제 돌려본 뒤, 토큰 최소화(`context_for_agent`)·자동 검증·라우팅 자동화가 실제로 필요해지면 다시 꺼내 쓴다. 설계는 폐기하지 않고 아래에 보존한다.

`facts`(사실)와 `vulnerability_candidates`(가설)를 분리하고, 각 후보가 후속 Agent에게 전달할 최소 컨텍스트(`context_for_agent`)를 스스로 들고 있는 구조. 아래 "후보 B 상세 스펙"에 전체 정의가 있다.

**장점**
- 기계 파싱이 안정적이라 Orchestrator가 조건 분기(예: confidence가 낮으면 스킵)를 코드로 처리할 수 있다
- `context_for_agent`로 토큰 최소화 원칙을 스키마 레벨에서 강제할 수 있다
- `execution_log`로 되돌릴 수 없는 행동(대상에 나간 실제 요청)을 추적할 수 있다
- 나중에 "AI가 못 푸는 지점"을 실행 데이터로 분석할 때 (evidence, confidence, open_questions 등이) 근거가 된다

**단점**
- 사람이 훑어보기엔 장황하다
- recon-agent가 이 구조를 다 채우는 데 드는 토큰/turn 비용이 후보 A'보다 크다

---

## 후보 B 상세 스펙

### 설계 원칙

1. **`facts`(확인된 사실)와 `vulnerability_candidates`(가설)를 분리한다.** 후속 Agent와 사람이 신뢰도를 구분해서 쓸 수 있어야 한다.
2. **각 vulnerability_candidate는 소비할 Agent가 필요로 하는 최소 컨텍스트를 스스로 들고 있는다(`context_for_agent`).** Orchestrator는 이 필드를 그대로 다음 Agent 호출의 입력으로 전달하면 되고, 전체 리포트나 대화 기록을 다시 넘길 필요가 없다 — 토큰 최소화 원칙.
3. **세션 독립성**: 이 파일이 recon-agent와 후속 Agent 사이의 유일한 상태 전달 수단이다. 대화 기록에 의존하지 않는다.
4. **되돌릴 수 없는 행동의 추적**: 대상에게 실제로 나간 요청은 `execution_log`에 전부 남긴다.

### 최상위 구조

```json
{
  "meta": {
    "target": "https://example.com",
    "scope": ["example.com", "*.example.com"],
    "generated_at": "2026-08-16T00:00:00Z",
    "recon_agent_version": "1.0",
    "phase": "external"
  },
  "facts": {
    "hosts": [
      { "host": "example.com", "resolved_via": "input", "evidence": "..." }
    ],
    "services": [
      {
        "host": "example.com",
        "port": 443,
        "protocol": "https",
        "service_guess": "nginx",
        "version_guess": "1.18.0",
        "evidence": "Server 헤더: nginx/1.18.0",
        "confidence": "medium"
      }
    ],
    "tech_stack": [
      {
        "name": "PHP",
        "category": "backend_language",
        "version": null,
        "evidence": "Set-Cookie: PHPSESSID=... 관찰됨",
        "confidence": "high"
      }
    ],
    "endpoints": [
      {
        "id": "EP-001",
        "url": "https://example.com/search",
        "method": "GET",
        "discovered_via": "홈페이지 내 <form action> 파싱",
        "parameters": [
          { "name": "q", "location": "query", "type_guess": "string" }
        ],
        "forms": [],
        "auth_required": false,
        "status_code": 200,
        "response_summary": "검색 결과 페이지, q 값이 결과 제목에 그대로 반영됨"
      }
    ]
  },
  "attack_surface": {
    "injection_relevant": [
      { "endpoint_ref": "EP-001", "parameter": "q", "location": "query", "note": "입력값이 응답 HTML에 그대로 반영됨(반사 힌트)" }
    ],
    "idor_authorization_relevant": [],
    "web_logic_relevant": []
  },
  "vulnerability_candidates": [
    {
      "id": "VC-001",
      "category": "injection",
      "target_agent": "injection-agent",
      "endpoint_ref": "EP-001",
      "hypothesis": "q 파라미터가 응답에 그대로 반영되어 XSS 또는 템플릿 인젝션 가능성이 있다",
      "evidence": ["q=test123 요청 시 응답 본문에 test123이 이스케이프 없이 포함됨"],
      "confidence": "medium",
      "context_for_agent": {
        "target": "https://example.com/search",
        "endpoint": { "url": "https://example.com/search", "method": "GET", "parameter": "q", "location": "query" },
        "parameter_relevant_response": "응답 본문 중 q 값 주변 스니펫만 (전체 HTML 아님)",
        "previous_evidence": ["q=test123 → 반영 확인 (recon 단계, payload 미전송)"]
      }
    }
  ],
  "open_questions": [
    "포트 스캔이 필요하지만 이 agent는 능동 스캔 도구가 없어 확인 못함"
  ],
  "execution_log": [
    { "action": "WebFetch", "url": "https://example.com/robots.txt", "purpose": "endpoint 탐색", "timestamp": "2026-08-16T00:00:01Z" }
  ]
}
```

### 필드 설명

#### `meta`
recon 실행 자체에 대한 메타데이터. `phase`는 항상 `"external"` (Phase 2가 생기면 `"local"`을 쓰는 별도 스키마/agent가 담당).

#### `facts.*`
관찰된 사실만. 추정이 섞이면 `confidence` 필드로 명시하고, 절대 취약점 여부를 여기서 단정하지 않는다.

#### `attack_surface.*`
`facts.endpoints`를 세 관점(injection / idor_authorization / web_logic)으로 분류한 인덱스. endpoint 원본을 복제하지 않고 `endpoint_ref`로 참조한다.

#### `vulnerability_candidates[]`
후속 전문 Agent 라우팅의 실제 입력이 되는 배열. 필드:

| 필드 | 설명 |
|---|---|
| `category` | `injection` \| `idor_authorization` \| `web_logic` \| `other` |
| `target_agent` | 힌트일 뿐, 실제 호출 여부는 Orchestrator가 결정 |
| `hypothesis` | 반드시 가설 톤 ("~일 수 있다") |
| `confidence` | `low` \| `medium` \| `high` |
| `context_for_agent` | **후속 Agent에게 그대로 전달할 최소 입력**. 아래 "Context Template" 참고 |

#### `open_questions[]`
recon 단계에서 해결 못한 것 (스코프 밖, 도구 부재, 판단 불가 등). 사람 또는 Orchestrator가 다음 액션을 정할 때 참고.

#### `execution_log[]`
대상에게 실제로 나간 모든 능동 요청 기록. 되돌릴 수 없는 행동이므로 감사(audit)와 재현성을 위해 빠짐없이 남긴다.

### Context Template (카테고리별 최소 컨텍스트)

`context_for_agent`를 채울 때, 카테고리별로 아래 필드만 포함한다 — 그 이상은 넣지 않는다.

#### `injection`
```json
{
  "target": "URL",
  "endpoint": { "url": "...", "method": "...", "parameter": "...", "location": "query|body|path|header" },
  "parameter_relevant_response": "해당 파라미터와 관련된 응답 스니펫만 (전체 응답 아님)",
  "previous_evidence": ["recon 단계에서 관찰된 것, payload 없이"]
}
```

#### `idor_authorization`
IDOR(객체 참조 노출)와 Authorization(권한/인증 분기 결함)을 하나의 Agent가 같이 다루므로, 둘 중 해당하는 필드만 채우면 된다 (둘 다 해당하면 둘 다 채운다).
```json
{
  "target": "URL",
  "endpoint": { "url": "...", "method": "..." },
  "object_reference_pattern": "예: 정수 증가 ID가 /users/{id}/profile 형태로 노출 (해당 없으면 생략)",
  "sample_values_observed": ["관찰된 값 (예: 1023)"],
  "auth_mechanism": "예: 세션 쿠키(JSESSIONID), JWT, OAuth 콜백 등 (해당 없으면 생략)",
  "flow_note": "로그인/권한분기가 일어나는 지점에 대한 짧은 설명 (해당 없으면 생략)",
  "previous_evidence": ["..."]
}
```

#### `web_logic`
```json
{
  "target": "URL",
  "endpoint": { "url": "...", "method": "..." },
  "logic_concern": "예: price/qty 파라미터를 클라이언트가 임의로 지정 가능, 음수 허용 여부 미확인",
  "workflow_note": "다단계 절차 중 특정 단계를 건너뛸 수 있어 보이는지, 순서를 바꿀 수 있어 보이는지 등",
  "previous_evidence": ["..."]
}
```

새 카테고리가 추가되면, 이 파일에 템플릿을 추가하고 `SKILL.md` Step 5/6에서 참조를 갱신한다.

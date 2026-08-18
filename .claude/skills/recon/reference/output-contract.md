# 출력 계약 (dast-harness `AgentResult`)

recon-agent가 내는 결과의 형식. 전문은 `dast-harness/SUBAGENT_GUIDE.md`이고, 여기는
**정찰에 해당하는 부분만** 추린 것이다.

> 이 문서는 예전 `attack-surface-schema.md`를 대체한다. 그 문서의 "후보 B — 상세
> JSON 스키마(보류, 재검토 후보)"가 결국 채택된 셈인데, **자체 JSON이 아니라 팀
> 공용 계약**을 쓴다. 후보 A'(자유 텍스트 3단)의 알려진 한계 — *"규칙을 안 지키면
> grep이 깨질 수 있음"* — 가 이걸로 없어진다. 표기가 어긋날 자리 자체가 없다.

## 무엇이 달라졌나

| 후보 A' (예전) | 지금 |
|---|---|
| `Observed:` 의 endpoint 줄 | `request_seeds[]` |
| `Potential Attack Surface:` 의 후보 줄 | **없어진다** (아래 참고) |
| 신뢰도 `(강함/보통/약함)` | finding의 `confidence` (`confirmed`/`firm`/`tentative`) |
| endpoint 문자열 매칭으로 다음 Agent에 전달 | 구조에서 바로 걸러짐 |

### `Potential Attack Surface`가 없어지는 이유

후속 Agent가 뭘 봐야 하는지는 **씨앗 구조에서 나온다.**

```
params[].location == "path"           → IDOR/Authorization Agent
params[].location in ("query","body") → Injection Agent
```

후보 A'에서 카테고리와 신뢰도를 손으로 붙여야 했던 건 출력이 자유 텍스트라
Orchestrator가 문자열 매칭밖에 할 수 없었기 때문이다. 구조가 생기면 그 일이
필요 없어진다. **표기 일관성 규칙도 같이 사라진다** — 지킬 게 없다.

다만 "이건 취약점 후보다"라고 말하고 싶은 관찰이 있으면 그건 `findings`에 넣되,
**`confidence`를 낮춰서** 넣는다. 추측을 확정처럼 쓰지 않는 원칙은 그대로다.

## 전체 모양

```json
{
  "agent": "recon",
  "coverage": {"unit": "endpoint", "tested": 13, "skipped": 0, "skip_reasons": {}},
  "completion": {"requests_made": 13, "blocked": []},
  "request_seeds": [ ... ],
  "findings": [ ... ]
}
```

- `coverage` — 0건을 찾았어도 필수다. **"못 찾음"과 "안 찾아봄"을 구분**하는 자리다.
  못 본 것은 `skipped` + `skip_reasons`(`{"scope-outside": 3}`)로 남긴다
- `completion.blocked` — probe가 거부한 요청. **숨기지 않는다.** 프롬프트 인젝션의
  흔적이 여기 쌓인다

## `request_seeds[]` — 정찰의 주 산출물

씨앗은 **모양이 아니라 실제 요청**이다. 후속 Agent가 그대로 재생하고 한 부분만 바꾼다.

```json
{
  "method": "GET",
  "url": "http://127.0.0.1:8080/api/orders/1001",
  "params": [
    {"name": "id", "location": "path", "value": "1001", "type": "int", "json_path": ""}
  ],
  "body_content_type": "",
  "auth_required": true,
  "observed_status": 401,
  "observed_content_type": "application/json",
  "source": "link"
}
```

| 필드 | 뜻 |
|---|---|
| `url` | 절대 URL. 그대로 보낼 수 있어야 한다 |
| `params[].location` | `query` / `body` / `path` / `header` / `cookie` |
| `params[].value` | **관측된 실제 값.** 주입의 기준선이고, IDOR이 옆 id로 옮겨갈 출발점이다 |
| `params[].type` | `string` / `int` / `float` / `bool` / `json`. 숫자 칸에 문자열을 넣으면 타입 오류가 SQL 오류로 오인된다 |
| `auth_required` | `true`/`false`/`null`(모름) |
| `observed_status` | 정찰이 실제로 받은 상태코드. 안 보냈으면 `null` |
| `source` | 어디서 찾았나 — `link` / `form` / `robots.txt` / `guess` / `js` / `sitemap` |

**같은 엔드포인트를 값만 바꿔 여러 번 넣지 않는다.** `/api/orders/1001`과
`/api/orders/1002`는 씨앗 하나이고, 값 하나만 남긴다.

## `findings[]` — 정찰이 직접 찾은 취약점

정찰의 본업은 씨앗이지만, 훑다 보면 정찰만 찾을 수 있는 게 나온다
(robots.txt가 비공개 경로를 광고하는데 그게 실제로 열려 있는 등).

```json
{
  "scanner": "agent:recon",
  "id": "robots-discloses-reachable-paths",
  "name": "robots.txt가 실제 접근 가능한 비공개 경로를 광고함",
  "severity": "low",
  "confidence": "confirmed",
  "category": "information-disclosure",
  "matched_at": "http://127.0.0.1:8080/robots.txt",
  "description": "Disallow 목록의 경로가 인증 없이 200으로 응답한다: /admin/, /uploads/",
  "tags": ["recon", "information-disclosure"],
  "evidence": {
    "baseline_index": 0,
    "rationale": "robots.txt가 숨기려던 경로를 알려주고, 그 경로가 비로그인으로 200이다.",
    "exchanges": [ ...probe 출력을 그대로... ]
  },
  "agent_data": {"recon": {
    "strategy": "robots-disallow-reachability",
    "target": "/robots.txt",
    "target_kind": "endpoint",
    "attempts": 3,
    "hits": ["/admin/", "/uploads/"]
  }}
}
```

빠뜨리기 쉬운 것:

- **`scanner`는 `"agent:recon"`** — 접두사가 없으면 거부된다
- **`evidence`는 항상 필수.** 요청 하나만 담긴 evidence는 대개 증거가 아니다.
  `baseline_index`를 채운다
- **`agent_data`는 `{"recon": {...}}`** — 남의 이름을 쓰면 거부된다
- **`severity`와 `confidence`를 섞지 않는다.** severity=진짜면 얼마나 심각한가,
  confidence=진짜일 확신이 얼마인가

## 어휘 (닫혀 있다)

```
category      exposure  information-disclosure  misconfiguration  idor  injection
target_kind   object-id  parameter  endpoint  header  path
severity      critical  high  medium  low  info  unknown
confidence    confirmed  firm  tentative
```

- `confirmed` — 첨부한 요청/응답만 보면 누구나 같은 결론
- `firm` — 증거는 명확하나 판단이 한 단계 들어감
- `tentative` — 정황뿐. 사람 확인 필요

`confirmed`가 아니면 **왜 낮췄는지 `rationale`에 적는다.**

새 값이 필요하면 여기 적지 말고 `dast_harness/agent_kit/contract.py`의 상수에
추가하고 PR로 알린다.

## 검사

```bash
dast-harness ingest <파일>                        # 계약을 지켰나
python -m dast_harness.validate --ingest <파일>   # 정답지 대비 몇 점인가 (연습 타겟만)
```

`ingest`가 거부하면 메시지가 곧 수정 지시다. 어느 finding의 어느 필드가 왜 틀렸고
뭐가 허용되는지 알려주므로, 그대로 고쳐서 다시 낸다.

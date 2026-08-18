# recon_subagent

> ### ⚠️ 2026-08 dast-harness 이식됨
>
> 이 agent는 이제 팀 공용 하네스([dast-harness](https://github.com/moovingGun/dast-harness))
> 위에서 돈다. 바뀐 것:
>
> | 예전 | 지금 |
> |---|---|
> | `curl` / `nmap` / `ffuf` 직접 호출 | `dast-harness probe` (매 요청 `safety.py` 통과) |
> | `attack-surface.md` 자유 텍스트 3단 | `findings.json` — `AgentResult` 계약 |
> | `tools/validate_attack_surface.py` | `dast-harness ingest` |
> | 자체 lab-target | `targets/vulnerable_app` (정답지가 있어 **채점된다**) |
>
> 역할·경계·Safety Gate·탐색 절차는 그대로다. **배관만 갈아끼웠다.**
> 아래 문서 중 결정 로그·실험 기록은 **이식 이전** 시점의 것이며, 기록으로 보존한다.
> 지금 기준의 형식은 [`output-contract.md`](.claude/skills/recon/reference/output-contract.md),
> 도구는 [`tools.json`](.claude/skills/recon/reference/tools.json)을 본다.

> 👋 **팀에 처음 공유받았다면** 이 README(하네스 엔지니어링 결정 로그 포함, 시행착오 전부)보다 [`docs/recon-agent-guide.md`](docs/recon-agent-guide.md)를 먼저 읽는 걸 추천합니다 — "지금 이 agent가 뭘 하는지"만 5분 안에 정리해둔 문서입니다. 이 README는 "왜 지금 이 형태가 됐는지"까지 시간순으로 남긴 빌드 로그입니다.

## 이 프로젝트가 검증하려는 것

> "어떤 하네스 구조가 더 좋은가"가 아니라, **"취약점별 전문 Agent를 설계·조합하는 방식이 범용 AI 단독보다 실제 취약점 진단 업무에서 더 생산적인가"** 를 확인하는 프로젝트다.

핵심 철학: 하나의 LLM에게 전 과정을 맡기지 않는다. 보안 전문가의 진단 절차를 Agent 단위로 모듈화하고, 필요한 Agent를 조합해서 실제 취약점을 생산성 있게 발견한다. 이 저장소는 그중 **recon-agent**(정찰 담당) 하나를 만드는 부분이다.

## 전체 아키텍처에서 recon-agent의 위치

```
Target(URL) → Orchestrator → Recon Agent(External, Phase 1) → Attack Surface
                                                                     │
                    ┌────────────────────────────────────────────────┼────────────────────────────────────────────────┐
                    ▼                                                ▼                                                ▼
             Injection Agent                              IDOR/Authorization Agent                              Web Logic Agent
                    └────────────────────────────────────────────────┼────────────────────────────────────────────────┘
                                                                     ▼
                                                     Finding → Vulnerability Chain → Actual Threat(→root)
```

**recon-agent는 판단 주체가 아니라 정보 생산자다.** 취약점을 확정하거나, 다음에 어떤 Agent를 부를지 결정하지 않는다. 후속 Agent(Injection / IDOR·Authorization / Web Logic, 필요시 추가)가 바로 쓸 수 있는 구조화된 정보(Attack Surface)만 만든다.

recon-agent의 6가지 역할: Target 기본정보 수집 → 서비스/포트 식별 → 기술스택 추정 → Endpoint 탐색 → 공격표면 정리 → 취약점 후보 생성. Foothold 이후 root로 가는 내부(Local) 정찰은 별개 Agent(Phase 2, 미착수)의 몫이다.

## 저장소 구조 — 파일별 역할과 "왜"

```
.claude/
  agents/
    recon-agent.md                       ← subagent 정의: 역할·경계·도구·Safety Gate
  skills/recon/
    SKILL.md                             ← 실행 절차 (Step 0~7)
    reference/
      attack-surface-schema.md           ← 출력 포맷 정의 (후보 A'/B)
      output-path-convention.md          ← 결과 저장 경로 규칙
      tools.json                         ← 사용 가능한 도구의 단일 기준 정의 (Single Source of Truth)
  settings.json                          ← Bash 명령 허용 범위 (권한 규칙, tools.json에서 자동 생성됨)
docs/
  recon-agent-guide.md                   ← 팀 공유용 요약 가이드 ("지금 상태"만, 시행착오는 이 README에)
lab-target/
  app.py, app2.py, README.md             ← 로컬 연습용 더미 취약 웹앱 2종 (127.0.0.1 전용)
tools/
  wordlists/common.txt                   ← ffuf용 큐레이션된 wordlist (165개)
  sync_permissions.py                    ← tools.json → settings.json 동기화 스크립트
  validate_attack_surface.py             ← attack-surface.md가 후보 A' 규칙을 지키는지 자가 검증
recon-output/                            ← recon-agent 실행 결과 (git 추적 안 함)
.gitignore
```

### [`recon-agent.md`](.claude/agents/recon-agent.md) — subagent 정의
- `tools:` 목록이 **파일/검색/웹 도구 위주**로 좁혀져 있다 (`Read, Write, Grep, Glob, WebFetch, WebSearch, Bash`). 처음엔 Bash가 아예 없었다 — 이유는 "## 4. 실행 전 확인 절차 (Safety Gate)" 섹션에 있음: Claude Code 체크포인트는 파일 편집만 되돌릴 수 있고, 대상에 나간 네트워크 요청 같은 외부 부작용은 되돌릴 수 없기 때문에, 애초에 능동적으로 위험한 행동을 할 수 있는 도구 자체를 안 주는 방향으로 시작했다.
- "## 1. 역할과 경계"는 recon-agent가 정보 생산자일 뿐 판단/라우팅 주체가 아니라는 걸 명시한다.
- "## 3. 입력 계약" / "## 5. 출력 계약"은 **세션 독립성**(subagent 호출마다 새 컨텍스트로 시작) 때문에 존재한다 — 대화 기록에 기대지 않고, 파일로 상태를 주고받는다.

### [`SKILL.md`](.claude/skills/recon/SKILL.md) — 실행 절차
- PTES Reconnaissance / OWASP WSTG Information Gathering 같은 공인 방법론을 뼈대로 한 Step 0~7 체크리스트다.
- agent.md에 절차를 안 적고 skill로 분리한 이유: **skill은 필요할 때만 로드되므로**, 절차가 매 세션 컨텍스트를 차지하는 CLAUDE.md류 파일에 있으면 낭비다. agent.md는 "얇게" 유지하고, "어떻게 하는지"는 여기로 몰았다.

### [`attack-surface-schema.md`](.claude/skills/recon/reference/attack-surface-schema.md) — 출력 포맷
- 처음엔 상세 JSON(후보 B: facts/vulnerability_candidates 분리, agent별 최소 컨텍스트 `context_for_agent`, execution_log)로 설계했다가, 실제 사용자가 원한 예시(`Target/Observed/Potential Attack Surface` 3단 텍스트, 후보 A)로 **채택을 바꿨다.** 후보 B는 지우지 않고 "보류"로 남겨둠 — 나중에 토큰 최소화·자동검증이 필요해지면 재검토.
- 카테고리 체계는 **Injection / IDOR·Authorization(합침) / Web Logic** 3종 — 실제 후속 Agent 구성과 1:1 대응하도록 두 번째로 갱신됨(처음엔 Injection/IDOR/Auth 3종이었다가, IDOR와 Auth가 같은 Agent로 합쳐지면서 바뀜).

### [`output-path-convention.md`](.claude/skills/recon/reference/output-path-convention.md) — 저장 경로
- `recon-output/<target-slug>/attack-surface.<ext>`(최신본) + `runs/<timestamp>/`(매 실행 영구 보존). **run 히스토리를 지우지 않는 이유**: 재현성·사후 실행데이터 분석이 프로젝트 핵심 목표라서.

### [`tools.json`](.claude/skills/recon/reference/tools.json) — 도구 단일 기준 정의
- 도구 이름·실행 위치·호출 형식·플래그·wordlist·제한값을 **한 곳에 모아둠**(현재는 전부 로컬 네이티브 실행 — 처음엔 nmap/gobuster/ffuf가 WSL 경유였다가 결정로그 #20에서 네이티브로 전환됨). `recon-agent.md`/`SKILL.md`는 이 파일을 참조만 하고 세부값을 반복해서 적지 않는다 — 처음엔 이 정보가 `recon-agent.md`/`SKILL.md`/`settings.json` 세 곳에 흩어져 있어서(도구를 3개 추가하면서 실감함) 통합함.
- YAML이 아니라 **JSON**인 이유: 사람이 보기엔 YAML이 편하지만, `sync_permissions.py`가 파싱해야 하는데 YAML은 PyYAML이라는 외부 의존성이 필요하고 JSON은 Python 표준 라이브러리만으로 됨. LLM(recon-agent)이 읽는 데는 형식 차이가 없어서, 스크립트 쪽 제약을 우선함.
- **한계**: `.claude/settings.json`의 실제 권한 강제는 Claude Code 엔진이 직접 읽는 것이라 이 파일을 자동 참조하지 못한다. 도구를 추가/제거할 때만 `tools/sync_permissions.py`를 실행해서 수동으로 동기화해야 한다 (플래그·wordlist 같은 세부값 조정은 `settings.json`이 애초에 그 단위를 제어 못 해서 동기화 불필요).

### [`tools/sync_permissions.py`](tools/sync_permissions.py) — 권한 동기화 스크립트
- `tools.json`의 각 도구가 선언한 `permission_patterns`를 모아 `settings.json`의 `permissions.allow`를 재생성한다. `--check`로 불일치만 확인 가능. **판단을 코드로 대체**해서, "두 파일이 일치하나?"를 매번 사람이나 LLM이 다시 추론할 필요를 없앰.

### [`lab-target/`](lab-target/) — 연습용 더미 타겟
- `127.0.0.1` 전용 바인딩(외부 노출 불가), Python 표준 라이브러리만 사용.
- **`app.py`(`:8080`)**: Injection/IDOR·Authorization/Web Logic 결함을 의도적으로 하나씩 심어둠. recon-agent를 실제로 돌려볼 최소 안전한 대상이 필요해서 만듦. endpoint가 전부 홈페이지 링크로 노출돼 있어 수동 탐색만으로 다 찾을 수 있다.
- **`app2.py`(`:8082`, 신규)**: `app.py`와 DVWA 테스트 둘 다 endpoint가 (링크로든 디렉터리 리스팅으로든) 전부 드러나 있어서, recon-agent가 능동 탐색 도구(gobuster/ffuf)를 실제로 승격해서 쓰는지는 한 번도 검증하지 못했다는 게 드러남 → endpoint 절반은 링크로 노출하고 절반은 링크·robots.txt 어디에도 없이 완전히 숨겨서, "수동 우선 → 부족하면 능동 승격"(SKILL.md Step 4)이 실제로 작동하는지 채점 가능하게 만듦. 카테고리도 File Upload/SSRF까지 5종으로 늘려서, 지금 3개 후속 Agent 체계에 안 맞는 유형을 recon-agent가 어떻게 분류하는지(Other로 보내는지) 관찰하는 용도도 겸함.

## 실행 결과는 어디에 쌓이나 (recon-agent 호출할 때마다)

```
recon-output/<target-slug>/attack-surface.md              ← 최신 결과
recon-output/<target-slug>/runs/<timestamp>/attack-surface.md    ← 그 실행의 스냅샷
recon-output/<target-slug>/runs/<timestamp>/execution_log.jsonl  ← 그 실행이 실제로 보낸 요청 전부
```

## 하네스 엔지니어링 결정 로그 (시간순)

문제가 뭐였고, 어떻게 풀었고, 어디에 반영됐는지:

| # | 문제/논의 | 결정 | 반영 위치 |
|---|---|---|---|
| 1 | recon-agent 산출물을 후속 Agent가 어떻게 받나 | 표준 스키마 필요, "사실"과 "가설"을 분리 | `attack-surface-schema.md` |
| 2 | 세션 독립성 — 호출마다 새 컨텍스트 | 결과를 반드시 파일로 영속화, 대화 기록 의존 금지 | `recon-agent.md` §5, `output-path-convention.md` |
| 3 | 체크포인트가 외부 부작용(네트워크 요청)을 못 되돌림 | Safety Gate 신설: scope 확인, 공격적 요청 금지, 모든 능동 요청 로그화 | `recon-agent.md` §4 |
| 4 | 위 원칙 때문에 처음엔 Bash를 아예 안 줌 | tools를 파일/검색/웹 도구로만 제한 | `recon-agent.md` `tools:` |
| 5 | **실제 테스트 1회차**: 순수 HTTP 대상(`http://127.0.0.1:8080`)에서 WebFetch가 http→https 강제 업그레이드해서 전부 실패 | recon-agent가 정직하게 실패를 기록하고 중단 (환각 없음, 반복 재시도 없음) — 하지만 실제 정찰 실패 | `recon-output/127.0.0.1_8080/runs/2026-08-17T00-00-00Z/` |
| 6 | 5번을 어떻게 보완할지 | Bash는 열되 `curl`/`nslookup`/`whois`만 권한 규칙으로 자동 승인, curl은 GET/HEAD(조회성)만 | `.claude/settings.json`, `recon-agent.md` §4-6 |
| 7 | **실제 테스트 2회차**: 같은 대상, curl 폴백으로 재시도 | 성공 — WebFetch 실패 → curl 재시도 → 4개 endpoint, 4개 후보(Injection/IDOR·Authorization/Web Logic) 전부 정확히 태깅 | `recon-output/127.0.0.1_8080/runs/2026-08-17T11-10-00Z/` |
| 8 | vuln-agent 체계가 Injection/IDOR/Auth 3종에서 Injection/IDOR·Authorization/Web Logic 3종으로 확정됨 | 카테고리 체계 전면 갱신 | `SKILL.md` Step 5/6, `attack-surface-schema.md` |
| 9 | nmap/gobuster/ffuf 설치 시도 → Windows 호스트에서 nmap이 Npcap/UAC 문제로 실패 | 이 컴퓨터에 이미 있던 **WSL(Ubuntu, nmap 기설치)** 을 발견, 실행 환경을 로컬(curl 등)과 WSL(nmap 등)로 분리하는 모델 제안 (아직 gobuster/ffuf는 미설치, YAML 도구 정의는 미착수) | (대화 기록, 아직 파일 반영 전) |
| 10 | **실제 테스트 3회차**: 실제 취약 웹앱(DVWA, PHP/Apache/MySQL)에 대해 recon 수행 | curl만으로 16개 Attack Surface 후보(모듈 14개 포함) 전부 발견 — 단, Apache 디렉터리 리스팅이라는 **서버 설정 실수 덕분**이었음이 확인됨. 디렉터리 리스팅이 없었다면 능동 브루트포스(gobuster/ffuf) 없이는 못 찾았을 것 → 능동 endpoint 탐색 도구 필요성이 실증됨. DB를 초기화하는 미인증 폼을 발견했지만 되돌릴 수 없는 부작용이라 제출하지 않음(Safety Gate 재확인) | `recon-output/127.0.0.1_8081/runs/2026-08-17T12-05-00Z/` |
| 11 | WSL Ubuntu에 gobuster/ffuf를 직접 설치(사용자가 수동으로 — sudo 비밀번호는 agent가 다룰 수 없어서 직접 진행), nmap은 이미 있었음 | 세 도구 모두 확인. Git Bash에서 `wsl.exe`로 넘기는 `/mnt/c/...` 경로가 MSYS 자동변환에 의해 깨지는 문제 발견 → `MSYS_NO_PATHCONV=1` 접두어로 해결. gobuster/ffuf/nmap 전부 DVWA 대상으로 실제 동작 검증(README.md/CHANGELOG.md 등 curl로는 못 찾은 endpoint 추가 발견, nmap이 포트/서비스 정확히 식별) | `.claude/settings.json`(권한 6개 추가), `recon-agent.md` §4-7(안전 정책: nmap `-Pn -sV --top-ports 100 -T3` 고정, gobuster/ffuf 스레드 10 제한 + 전용 wordlist), `SKILL.md` Step 2/4, `tools/wordlists/common.txt`(신규, 큐레이션된 162개 wordlist) |
| 12 | 도구 정보가 `recon-agent.md`/`SKILL.md`/`settings.json` 세 곳에 흩어져서 매번 같이 고쳐야 하는 문제가 실제로 드러남 (도구 3개 추가하면서 체감) | `tools.json`으로 단일화(처음엔 YAML로 하려다, 동기화 스크립트가 PyYAML 의존성 없이 표준 라이브러리만으로 파싱하도록 JSON으로 변경). `settings.json`은 Claude Code 엔진이 직접 읽는 값이라 자동 참조는 안 되지만, `tools/sync_permissions.py`로 "새 도구 추가/제거 시에만" 동기화하도록 결정론적 스크립트화 | `.claude/skills/recon/reference/tools.json`(신규), `tools/sync_permissions.py`(신규), `recon-agent.md`/`SKILL.md`(참조로 치환) |
| 13 | 후보 A(단순 텍스트)가 "토큰 최소화"와 "Orchestrator 라우팅 판단 지원"을 동시에 만족하는지 재검토 — JSON(후보 B) 없이도 될지 | **후보 A' 채택**: 신뢰도(`강함`/`보통`/`약함`) 표기를 선택→필수로, `Observed`/`Potential Attack Surface`의 endpoint 문자열을 완전히 동일하게 쓰도록 강제. 이 두 가지만으로 Orchestrator가 카테고리+endpoint 문자열 매칭(grep)만으로 다음 Agent에게 필요한 최소 줄(Target + 후보 줄 + 관련 Observed 줄)만 추려 전달할 수 있게 됨 — JSON의 `context_for_agent` 없이도 실질적으로 같은 효과. 남은 한계: 여전히 자유 텍스트라 규칙을 안 지키면 grep이 깨질 수 있고, 강제 검증 스크립트는 아직 없음 | `attack-surface-schema.md`(후보 A' 섹션 신설), `SKILL.md` Step 6, `recon-agent.md` §5 |
| 14 | 13번에서 남긴 한계("강제 검증 스크립트는 아직 없음")를 실제로 채움 | `validate_attack_surface.py` 작성 — Target/Observed/Potential Attack Surface 섹션 존재, 후보 줄의 카테고리·신뢰도 패턴, `강함`인데 근거 없는 경우, endpoint 표기 불일치를 전부 잡아냄. 기존 실행결과 4개(A' 규칙 이전 생성)를 돌려서 전부 위반으로 정확히 잡아내는 것으로 검증 완료. recon-agent가 Step 7에서 저장 직후 **스스로** 이 스크립트를 돌려 자가 검증하도록 절차에 포함시킴(파일 저장 후 검증 실패 시 고쳐서 재검증) | `tools/validate_attack_surface.py`(신규), `tools.json`(도구로 등록), `SKILL.md` Step 7, `recon-agent.md` §6(완료 조건) |
| 15 | **실제 테스트 4회차**(DVWA `:8081`) 결과물을 검증기로 재검사하다가 두 가지 실제 문제 발견: (1) `validate_attack_surface.py`의 근거(reason) 정규식이 줄 끝에 괄호 하나만 있어야 통과해서, 근거 안에 중첩 괄호가 있거나 근거 뒤에 부가설명이 더 붙는 **정상적인 줄까지 "형식 위반"으로 오탐**했다. (2) recon-agent 1차 결과물이 여러 endpoint를 쉼표로 묶어 한 줄에 적어서(`Observed`와 문자열 불일치) 자가 검증에 실패 → **Step 7 설계대로 recon-agent가 스스로 재작업해서 통과본을 다시 저장**했음을 실행 로그 대조로 확인(다만 최종 채팅 보고에는 이 자가교정 과정이 언급되지 않았음) | 검증 정규식을 "필수 구조는 앞부분만 강제, 근거는 자유 텍스트"로 재설계(합성 테스트로 회귀 없음 확인). SKILL.md/schema.md에 "한 줄에 endpoint 하나" 규칙 명문화. recon-agent.md §5에 최종 보고 시 검증 통과 여부 명시를 강제하는 문구 추가 | `tools/validate_attack_surface.py`, `SKILL.md` Step 6, `attack-surface-schema.md`, `recon-agent.md` §5 |
| 16 | 15번 리뷰 중, DVWA·`app.py` 두 테스트 모두 endpoint가 전부 드러나 있어서(디렉터리 리스팅/링크) 능동 탐색 승격 자체는 실전에서 한 번도 검증 못 했다는 사각지대가 확인됨 | 두 번째 랩 타겟 `app2.py`(`:8082`) 신설 — endpoint 절반은 링크 노출, 절반은 링크·robots.txt 어디에도 없이 완전히 숨겨서 능동 탐색 승격 여부를 직접 채점 가능하게 함. File Upload/SSRF 카테고리 추가로 기존 3분류 체계의 한계도 같이 관찰 | `lab-target/app2.py`(신규), `lab-target/README.md`, `tools/wordlists/common.txt`(fetch/proxy/webhook 추가) |
| 17 | **실제 테스트 5회차**(`app2.py`, `:8082`) 진행 중 gobuster가 connection refused로 실패 → recon-agent가 즉흥적으로 curl 순차 요청으로 대체해서 3개 endpoint(`/admin`,`/upload`,`/fetch`) 전부 발견. 원인을 직접 재현 검증한 결과: **WSL은 Windows 호스트와 별도 네트워크 네임스페이스라, `127.0.0.1`에 직접 바인딩된 Windows 쪽 서비스엔 원천적으로 도달 불가**(자신의 `127.0.0.1`이 다름). 반대로 WSL에서 `nmap 127.0.0.1`을 돌리면 (WSL/Docker 네트워크에 떠 있던) DVWA `:8081`은 여전히 열려 보임 — 즉 결정로그 #11이 "실제로 검증"했다고 기록한 건 "WSL 도구 자체가 작동한다"는 것뿐이었고, "WSL이 Windows loopback에 도달한다"는 건 아니었음이 뒤늦게 드러남. `example.com`/`scanme.nmap.org`(nmap 공식 테스트 허용 대상)로는 WSL의 curl/nmap이 정상 도달하는 것도 같이 확인 — **이 문제는 target이 `127.0.0.1`/`localhost`이고 Windows 쪽에 직접 바인딩된 로컬 랩일 때만 해당하며, 실습으로 주어지는 실제 URL(도메인/LAN IP/인터넷 호스트)에는 영향 없음** | recon-agent의 즉흥 대응(curl 순차 요청)을 우연이 아닌 정식 절차로 승격: `tools.json`의 `nmap`/`gobuster`/`ffuf`에 `known_limitation` + `curl_fallback` 필드 추가, `SKILL.md` Step 4에 조건부 안내 추가 |
| 18 | "다음 예정 작업"에 남아있던 "gobuster/ffuf/nmap을 실제 재실행해서 검증"이 실제로 됐는지 사용자가 되물음 → 모든 `recon-output/*/runs/*/execution_log.jsonl`을 전수 조사함(recon-agent의 정식 실행에서 실제로 실행된 명령만 남는 파일이므로, 사람이 수기로 돌려본 것과 구분 가능한 유일한 근거). 결과: **`nmap`은 1회 성공(결정로그 #10/DVWA)했지만, `gobuster`는 1회 시도 후 실패(결정로그 #17)했고, `ffuf`는 recon-agent 정식 실행에서 단 한 번도 시도된 적이 없었다.** 결정로그 #11의 "gobuster/ffuf/nmap 전부 DVWA 대상으로 실제 동작 검증"이라는 문구는, `execution_log.jsonl`에 남지 않는 방식(설치 직후 사람이 터미널에서 직접 돌려본 수기 확인)으로 이뤄졌을 가능성이 높고, recon-agent 실행 기준으로는 사실이 아니었음이 드러남 — 과거 항목이었어도 기록을 지우지 않고 이 항목으로 정정한다(레포 전체 컨벤션과 동일) | `README.md` "다음으로 예정된 작업"을 실측 상태로 재작성, 이 항목(#18) 추가로 #11 정정 |
| 19 | 18번의 후속: "gobuster/ffuf가 이 환경에서 기술적으로 작동은 하는가"만이라도 지금 확인하기 위해, WSL에서 도달 가능하다고 이미 확인된 DVWA(`:8081`)를 대상으로 **recon-agent를 거치지 않고 사람이 직접**(=이번에도 execution_log에 안 남는 수기 확인, #11과 성격이 같음을 명시) `gobuster dir`/`ffuf`를 돌려봄 | 둘 다 정상 작동 확인(`README.md`/`CHANGELOG.md` 등 gobuster/ffuf 전용으로만 찾히는 파일까지 발견). **다만 이건 "도구 문법·네트워킹이 이 환경에서 되는가"만 증명한다 — "recon-agent가 스스로 판단해서 gobuster를 호출하고 그걸로 새로운 걸 찾아내는 전체 파이프라인"은 여전히 미검증이다** (DVWA는 디렉터리 리스팅 때문에 recon-agent가 gobuster를 애초에 "필요없다"고 정당하게 판단하고 건너뜀). 이걸 마저 닫으려면 WSL 안에 직접 뜬 랩 타겟이 필요함(아직 없음) | (대화 기록, 수기 확인 — 결정로그 자체가 "실제 recon-agent 실행 증거"와 "수기 확인"을 앞으로는 구분해서 적어야 한다는 18번의 교훈을 따름) |
| 20 | 사용자가 "WSL 말고 다른 방법으로 127.0.0.1과 실습 URL 둘 다 되게 할 수 있는가"를 물음 → WSL 경계 문제 자체를 없애는 근본 해법은 **Windows 네이티브 설치**라고 판단, 설치 전 조회만 해봄: **Npcap 드라이버가 이미 설치·실행 중**이었음(결정로그 #9의 실패 원인이 이미 해소돼 있었음), winget에 `Insecure.Nmap`(공식 Nmap Project)과 `ffuf.ffuf`가 등록돼 있었음, `gobuster`는 winget에 없음. 사용자 승인 받고 `winget install`로 nmap 7.80·ffuf 2.2.1 네이티브 설치 → **127.0.0.1(`:8081`,`:8082`)과 실제 인터넷 대상(`scanme.nmap.org`) 양쪽 다 정상 작동을 직접 실행해서 확인함**(nmap 포트 스캔, ffuf 디렉터리 탐색 모두). gobuster는 winget에 없어서 안 깔고 ffuf로 일원화(`tools.json`에 이미 "대체 도구"로 명시돼 있던 관계를 그대로 승격) | `tools.json`(nmap/ffuf `exec: local`로 전환, 네이티브 invocation으로 교체, WSL 관련 `known_limitation`/`curl_fallback` 필드 제거, `gobuster` 항목 삭제), `.claude/settings.json`(`sync_permissions.py`로 재생성 — `wsl -d Ubuntu -- ...` 패턴 6개 → `Bash(nmap *)`/`Bash(ffuf *)` 2개로 축소), `SKILL.md` Step 4(WSL 주의 문단 삭제, gobuster→ffuf), `recon-agent.md` §4(도구 목록에서 gobuster 제거) |
| 21 | 20번 검증 도중 재확인 사살: `nmap`/`ffuf`를 플레인 이름(`nmap ...`)으로 치면 이 대화 세션의 Bash/PowerShell 양쪽 다 못 찾음(`CommandNotFoundException`) — winget이 설치 시 PATH를 갱신해도, **이미 떠 있던 셸 프로세스는 그 갱신을 못 본다.** 새 터미널을 열면 해결되지만, recon-agent(subagent) 호출이 매번 새 세션인 건 보장이 안 되므로 세션 신선도에 기대지 않는 방법이 필요했음 | 도구를 그때그때 즉흥적으로 PATH 보정하지 말고, `tools.json`의 `invocation_prefix` 자체에 PATH 보정을 박아넣음(`PATH="<설치경로>:$PATH" nmap`/`ffuf`) — 실제 실행해서 동작 확인. ffuf 경로는 이 컴퓨터의 사용자 계정(KDT40)에 종속적이라는 한계를 `notes`에 명시 | `tools.json`(nmap/ffuf `invocation_prefix`/`permission_patterns`에 PATH 보정 내장), `.claude/settings.json`(재생성) |
| 22 | 21번 반영 후, **recon-agent 정식 실행(Agent 호출) 안에서 네이티브 nmap/ffuf가 실제로 성공하는지** 처음으로 확인(#18/#19에서 미해결로 남겨뒀던 항목) — `app2.py`(`:8082`) 대상으로 재실행 | **성공.** `execution_log.jsonl`에 `nmap`/`ffuf`가 `wsl` 접두사 없이 실행된 기록이 실제로 남음. 새 endpoint는 없었지만(이전 결과와 동일하게 재현) 자가 검증 통과. 이걸로 "다음 예정 작업"에 남아있던 gobuster/ffuf/nmap 검증 항목을 완전히 닫음 | `recon-output/127.0.0.1_8082/runs/2026-08-17T15-23-08Z/` |
| 23 | 22번 검증 중 nmap이 `top-ports 100`으로는 `8082`를 못 잡는 걸 발견(top-100엔 `8080`/`8081`은 있어도 `8082`는 없음 — nmap의 포트 빈도 데이터베이스 순위 문제, 랩 타겟이 흔치 않은 포트를 쓰는 한 계속 재발할 문제였음). 사용자가 "100을 500으로 올리면 되나" 질문 → `--top-ports 500`으로 실제 스캔해서 `8082`가 포함되고 정상 탐지되는 것 직접 확인 | `nmap`의 `fixed_flags`/`scope_limit`을 `--top-ports 100` → `--top-ports 500`으로 변경 | `tools.json`, `README.md`(사용 가능한 도구 표) |
| 24 | 마지막 남은 todo("`/agents`로 목록 확인")를 사용자가 직접 PowerShell에서 시도 → **`/agents` 위저드 자체가 이 Claude Code 버전에서 제거됨**을 발견(계획했던 확인 방법이 애초에 더 이상 존재하지 않았음). 처음엔 프로젝트 디렉터리로 `cd` 하지 않고 홈 경로에서 `claude`를 실행해서 "이 프로젝트에 등록된 subagent 알려줘"라고 물어도 `recon-agent`가 안 보이는 문제까지 겹침(모델 차이가 원인 아니냐는 질문 있었으나, Claude Code가 실행 위치 기준으로 `.claude/agents/`를 스캔하는 구조라 그냥 작업 디렉터리 문제였음) | `cd`로 프로젝트 폴더로 이동 후 재실행하니 "Your project currently has a recon-agent defined already"로 정상 확인됨 — `/agents` UI 목록 대신 대화형 확인으로 검증 완료. subagent 인식은 모델(Sonnet/Opus) 종류와 무관하고 순전히 하네스가 실행 시점에 스캔하는 디렉터리 문제라는 것도 같이 확인됨 | (대화 기록 — 문서 수정 불필요, `/agents` UI가 없어졌다는 사실 자체는 프로젝트 파일이 아니라 Claude Code 버전 문제라 여기 반영할 파일이 없음) |
| 25 | 팀 공유용 문서를 준비하면서 전체 파일을 재검토하다가, #24를 적으면서 나 스스로도 "이 대화에서 4차례 호출"이라는 **셈 안 해본 숫자를 또 단정적으로 적은 것**을 발견 — #18에서 "정확히 셀 수 있을 때만 숫자를 적는다"고 스스로 정해놓고 바로 다음 항목에서 어김. 실제로 다시 세어보니 이 대화에서 `subagent_type: recon-agent` **Agent 호출은 3회**였고(DVWA, app2 1차, app2 네이티브 검증), "4"는 DVWA 1회 호출이 자가교정하며 남긴 run 스냅샷을 2개로 셌을 때 나오는 숫자였음(호출 수 ≠ run 스냅샷 수) | #24 문구에서 부정확한 숫자를 제거 | `README.md` 결정로그 #24 |

## 실행 테스트 요약 (지금까지 6회)

| 회차 | 대상 | 도구 | 결과 |
|---|---|---|---|
| 1 | 더미 lab-target (`:8080`) | WebFetch/WebSearch만 | **실패** — http→https 강제 업그레이드로 전부 막힘. 정직하게 실패 기록하고 중단 |
| 2 | 더미 lab-target (`:8080`) | + curl(GET/HEAD) | **성공** — endpoint 4개, 후보 4개(의도한 결함과 전부 일치), 가짜 Apache 배너에 안 속고 "더미 서버로 추정"까지 스스로 판단 |
| 3 | DVWA (`:8081`, 실제 PHP/Apache/MySQL) | + curl | **성공하되 한계 노출** — 후보 16개 찾았지만 디렉터리 리스팅 덕분. 로그인 이후 컨텐츠는 범위 밖이라 미확인. DB 리셋 폼은 안전하게 회피 |
| 4 | DVWA (`:8081`) 재실행 | + nmap(WSL) | **성공, 자가교정 확인** — 1차 저장본이 자가 검증 실패 → Step 7대로 스스로 재작업해서 통과본 재저장(결정로그 #15) |
| 5 | `app2.py`(`:8082`, 링크 절반 숨김 + File Upload/SSRF) | + curl 대체 능동탐색 | **성공** — 5개 endpoint 전부 발견(숨긴 3개 포함), 새 카테고리는 `Other`로 정확히 분류, 자가 검증 통과 + 최종 보고에 검증 결과 명시(결정로그 #15의 지적 사항이 이번엔 지켜짐). WSL-Windows loopback 경계 문제 발견(결정로그 #17) |
| 6 | `app2.py`(`:8082`) 재실행 | + nmap/ffuf(**네이티브**) | **성공** — WSL→네이티브 전환(결정로그 #20~21) 이후 첫 정식 실행. `execution_log.jsonl`에 `nmap`/`ffuf`가 `wsl` 접두사 없이 성공 실행된 기록 확인(결정로그 #22). 발견 결과는 5회차와 동일하게 재현(새 endpoint 없음) |

## 사용 가능한 도구 (2026-08-18 기준)

| 도구 | 실행 위치 | 정책 |
|---|---|---|
| `curl` | 로컬(Windows Bash) | GET/HEAD만 |
| `nslookup` / `whois` | 로컬(Windows Bash) | 도메인 대상일 때만 |
| `nmap` | **Windows 네이티브**(`winget install Insecure.Nmap`, 결정로그 #20) | `-Pn -sV --top-ports 500 -T3` 고정(결정로그 #23 — top-100엔 8082가 없어서 500으로 올림), 공격적 타이밍/취약점 스크립트 금지. WSL 경유가 아니라서 `127.0.0.1`/실제 인터넷 대상 둘 다 문제없이 도달. 흔치 않은 포트는 서비스 핑거프린팅에 시간이 걸릴 수 있음(타임아웃 넉넉히) |
| `ffuf` | **Windows 네이티브**(`winget install ffuf.ffuf`, 결정로그 #20) | `tools/wordlists/common.txt`만 사용, 스레드 ≤10, 타임아웃 필수. `gobuster`는 winget에 없어서 뺐고 ffuf로 일원화 |

## 다음으로 예정된 작업

- ~~네이티브 전환 이후 nmap/ffuf가 recon-agent 정식 실행 안에서 실제로 성공하는지 검증~~ **완료(결정로그 #22)** — `execution_log.jsonl`에 실제 성공 기록 확인됨.
- 도구 정의를 YAML로 뽑는 것 검토 중 (Hawx-Recon-Agent의 layer0.yaml 참고 아이디어)
- ~~`/agents` 슬래시 명령으로 목록에 정상적으로 뜨는지 사람이 터미널에서 직접 확인~~ **완료(결정로그 #24)** — 단, 계획했던 방식(`/agents` UI 목록)이 아니라 대화형 확인으로 검증됨. `recon-agent`가 정식 등록돼 있다는 것 자체는 이 대화에서 여러 차례 실제 호출·실행된 것으로 이미 충분히 증명돼 있었음

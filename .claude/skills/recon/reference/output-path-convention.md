# 결과 저장 경로 규칙 (Output Path Convention)

recon-agent가 결과를 어디에, 어떤 이름으로 저장할지에 대한 규칙이다. `recon-agent.md`와 `SKILL.md` Step 7에서 참조된다.

## 목적

"세션 독립성"(각 subagent 호출은 새 컨텍스트로 시작) 때문에, 결과 파일의 경로가 **예측 가능**해야 Orchestrator·다른 Agent·사람이 대화 기록 없이도 결과를 찾을 수 있다. 또한 같은 타겟을 여러 번 recon할 수 있으므로, 실행 이력이 **재현성/사후 분석**을 위해 남아있어야 한다.

## 디렉토리 구조

```
recon-output/
  <target-slug>/
    attack-surface.<ext>          ← 최신 결과 (후속 Agent·Orchestrator가 보는 "현재 상태")
    runs/
      <run-timestamp>/
        attack-surface.<ext>      ← 그 실행 시점의 스냅샷
        execution_log.jsonl       ← 그 실행에서 대상에 나간 모든 능동 요청 (raw, 추가전용)
        raw/                      ← 필요시 원본 응답 일부 보관 (evidence 인용 근거)
```

- `<ext>` = `md` ([attack-surface-schema.md](./attack-surface-schema.md) 후보 A' 채택됨 — Target/Observed/Potential Attack Surface 3단 텍스트, 필요시 Notes 섹션 추가). 후보 B(JSON)를 나중에 다시 채택하면 `json`으로 바뀔 수 있다.
- **run 히스토리는 영구 보존한다** (삭제/rotate 하지 않음). 재현성·사후 실행데이터 분석이 프로젝트 핵심 목표이므로 이력을 지우지 않는다.
- 최상단 `attack-surface.json`은 매 실행마다 최신 run의 내용으로 덮어쓴다. "지금 기준 상태"만 보면 되는 소비자(후속 vuln-agent)는 이 파일만 읽으면 된다.

## `run-timestamp` 형식

ISO 8601 UTC, 파일시스템에 안전하도록 `:` 을 `-`로 치환:
```
2026-08-17T03-15-00Z
```

## `<target-slug>` 생성 규칙

recon의 단위는 **host(:port) 하나**로 본다 (scope에 여러 호스트가 있으면 호스트별로 폴더가 나뉜다).

1. 스킴(`http://`, `https://`) 제거
2. 소문자화
3. 포트 구분자 `:` → `_`
4. path/query가 있으면 버린다 (recon 대상은 host 단위이지, path 단위가 아니다)

예:
| 입력 | slug |
|---|---|
| `localhost:8080` | `localhost_8080` |
| `https://example.com` | `example.com` |
| `https://example.com:8443/login` | `example.com_8443` |

## Git 관리

`recon-output/`은 실제 조사 대상에 대한 결과(민감할 수 있는 정보)를 담으므로 저장소에 커밋하지 않는다. 리포지토리 루트 `.gitignore`에 `recon-output/`을 추가해 관리한다.

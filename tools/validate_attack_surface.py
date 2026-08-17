#!/usr/bin/env python3
"""
recon-agent가 만든 attack-surface.md(후보 A')가 스키마 규칙을 지키는지 검증한다.
(.claude/skills/recon/reference/attack-surface-schema.md 의 "후보 A'" 절 기준)

규칙:
1. `Target:` 줄이 있어야 한다.
2. `Observed:` 섹션 헤더가 있어야 한다.
3. `Potential Attack Surface:` 섹션 헤더가 있어야 한다.
4. `Potential Attack Surface` 안에서 `- `로 시작하는 각 줄(=구조화된 후보)은 앞부분이
   다음 형식으로 시작해야 한다 (그 뒤에 오는 근거·부가설명은 자유 텍스트로 허용):
     - <endpoint> → <카테고리>(<신뢰도>) 검사 필요 ...
   - 카테고리 ∈ {Injection, IDOR/Authorization, Web Logic, Other}
   - 신뢰도 ∈ {강함, 보통, 약함} — 반드시 있어야 함 (생략 불가)
   - 신뢰도가 `강함`이면 "검사 필요" 뒤 어딘가에 괄호로 된 근거가 하나라도 있어야 함
     (중첩 괄호나 근거 뒤에 덧붙는 추가 설명은 허용 — 필수 구조만 앞부분에서 강제한다)
5. 각 후보의 endpoint 문자열은 `Observed` 섹션 어딘가에 문자 그대로 나타나야 한다
   (Orchestrator가 카테고리+endpoint 문자열 매칭만으로 다음 Agent에게 최소 컨텍스트를
   추릴 수 있어야 하므로 — 스키마 문서의 핵심 전제).

`- `로 시작하지 않는 줄(예: `(없음 — ...)` 같은 안내문)은 자유 텍스트로 보고 검사하지 않는다.

사용법:
    python tools/validate_attack_surface.py <파일경로> [<파일경로> ...]
    python tools/validate_attack_surface.py --all       # recon-output/*/attack-surface.md 전부 검사

종료코드: 0 = 전부 통과, 1 = 하나 이상 위반
"""
import io
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent

CATEGORIES = ["Injection", "IDOR/Authorization", "Web Logic", "Other"]
CONFIDENCES = ["강함", "보통", "약함"]

# 필수 구조(endpoint → 카테고리(신뢰도) 검사 필요)만 앞부분에서 강제한다.
# 그 뒤에 오는 근거(괄호)는 자유 텍스트로 취급한다 — 근거 안에 중첩 괄호가 있거나
# (예: "OWASP A01(Broken Access Control)"), 근거 뒤에 추가 설명이 더 붙는 경우
# (예: "... 필요) — 인증 메커니즘 자체이므로 함께 확인 필요")를 실제 recon 결과에서
# 관찰했는데, 예전에는 `reason`을 `[^)]*\)\s*$`로 앞뒤가 딱 맞아야만 인정해서
# 이런 정상적인 줄까지 "형식 위반"으로 오탐했다.
CANDIDATE_PREFIX_RE = re.compile(
    r"^-\s*(?P<endpoint>.+?)\s*→\s*"
    r"(?P<category>" + "|".join(re.escape(c) for c in CATEGORIES) + r")"
    r"\((?P<confidence>" + "|".join(CONFIDENCES) + r")\)\s*검사\s*필요\s*"
)
# "근거가 있는지"는 접두부 이후 나머지 텍스트 어디에든 괄호가 하나라도 있으면
# 인정한다 (중첩 괄호 포함 — 안쪽 내용까지 정밀 검증하지는 않는다).
HAS_PAREN_RE = re.compile(r"\(.*\)")

SECTION_HEADERS = ("Observed:", "Potential Attack Surface:", "Notes:")


def split_sections(text: str) -> dict:
    sections: dict[str, list[str]] = {"__preamble__": []}
    current = "__preamble__"
    for line in text.splitlines():
        stripped = line.strip()
        if stripped in SECTION_HEADERS:
            current = stripped[:-1]  # "Observed:" -> "Observed"
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return sections


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")

    if not re.search(r"^Target:\s*\S+", text, re.MULTILINE):
        errors.append("`Target:` 줄이 없거나 값이 비어있음")

    sections = split_sections(text)

    if "Observed" not in sections:
        errors.append("`Observed:` 섹션 헤더가 없음")
    if "Potential Attack Surface" not in sections:
        errors.append("`Potential Attack Surface:` 섹션 헤더가 없음")
        return errors  # 이후 검사 의미 없음

    observed_text = "\n".join(sections.get("Observed", []))
    pas_lines = sections.get("Potential Attack Surface", [])

    candidate_lines = [l for l in pas_lines if l.strip().startswith("- ")]
    for line in candidate_lines:
        stripped = line.strip()
        m = CANDIDATE_PREFIX_RE.match(stripped)
        if not m:
            errors.append(f"형식 위반 (카테고리/신뢰도/endpoint 패턴 불일치): {stripped!r}")
            continue

        endpoint = m.group("endpoint")
        confidence = m.group("confidence")
        rest = stripped[m.end():]
        has_reason = bool(HAS_PAREN_RE.search(rest))

        if confidence == "강함" and not has_reason:
            errors.append(f"신뢰도가 '강함'인데 근거가 없음: {stripped!r}")

        if endpoint not in observed_text:
            errors.append(
                f"endpoint 표기 불일치 — Potential Attack Surface의 {endpoint!r} 가 "
                f"Observed 섹션에 문자 그대로 없음 (grep 연결 불가)"
            )

    return errors


def main() -> int:
    args = sys.argv[1:]
    if not args or args == ["--all"]:
        paths = sorted(REPO_ROOT.glob("recon-output/*/attack-surface.md"))
        if not paths:
            print("recon-output/*/attack-surface.md 파일이 없음.")
            return 0
    else:
        paths = [Path(a) for a in args]

    overall_ok = True
    for path in paths:
        if not path.exists():
            print(f"[스킵] {path} — 파일 없음")
            continue
        errors = validate(path)
        if errors:
            overall_ok = False
            print(f"[FAIL] {path}")
            for e in errors:
                print(f"  - {e}")
        else:
            print(f"[OK]   {path}")

    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

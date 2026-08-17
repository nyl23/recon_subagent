#!/usr/bin/env python3
"""
.claude/skills/recon/reference/tools.json 의 각 도구가 선언한 permission_patterns를
모아서 .claude/settings.json 의 permissions.allow 를 재생성한다.

새 도구를 tools.json에 추가/제거했을 때만 이 스크립트를 실행하면 된다.
(플래그·wordlist·스레드 수 같은 세부 정책 조정은 settings.json이 애초에
 제어하지 않으므로 tools.json만 고치면 되고, 이 스크립트를 돌릴 필요가 없다.)

사용법:
    python tools/sync_permissions.py            # settings.json 갱신
    python tools/sync_permissions.py --check    # 갱신 없이 차이만 확인 (CI용, 종료코드 1이면 불일치)
"""
import io
import json
import sys
from pathlib import Path

# Windows 콘솔 기본 인코딩(cp949)에서도 한글 출력이 깨지지 않도록 강제 UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_JSON = REPO_ROOT / ".claude" / "skills" / "recon" / "reference" / "tools.json"
SETTINGS_JSON = REPO_ROOT / ".claude" / "settings.json"


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def collect_patterns(tools_data: dict) -> list[str]:
    patterns: list[str] = []
    for name, spec in tools_data["tools"].items():
        tool_patterns = spec.get("permission_patterns")
        if not tool_patterns:
            print(f"경고: '{name}' 도구에 permission_patterns가 없음 — 건너뜀", file=sys.stderr)
            continue
        for p in tool_patterns:
            if p not in patterns:
                patterns.append(p)
    return patterns


def main() -> int:
    check_only = "--check" in sys.argv

    tools_data = load_json(TOOLS_JSON)
    settings_data = load_json(SETTINGS_JSON) if SETTINGS_JSON.exists() else {}

    desired = collect_patterns(tools_data)
    current = settings_data.get("permissions", {}).get("allow", [])

    if desired == current:
        print("이미 동기화되어 있음 — 변경 없음.")
        return 0

    if check_only:
        print("불일치 발견:")
        print(f"  settings.json 현재: {current}")
        print(f"  tools.json 기준:    {desired}")
        return 1

    settings_data.setdefault("permissions", {})["allow"] = desired
    save_json(SETTINGS_JSON, settings_data)
    print(f"settings.json 갱신됨 ({len(desired)}개 패턴):")
    for p in desired:
        print(f"  - {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

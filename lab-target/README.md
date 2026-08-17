# Lab Target (recon-agent 연습용 로컬 더미 사이트)

`recon-agent`를 실제로 테스트해보기 위한 **완전히 안전한 로컬 연습용 웹앱**입니다.

## 안전성

- `127.0.0.1`(loopback)에만 바인딩됩니다 — 이 컴퓨터 밖에서는 절대 접근할 수 없습니다.
- 실제 서비스가 아니고, 데이터도 전부 더미입니다.
- Python 표준 라이브러리만 사용해서 추가 설치가 필요 없습니다.
- 이 컴퓨터 방화벽/네트워크 설정을 바꾸지 않는 한 인터넷에 노출되지 않습니다.

## 실행

```bash
python lab-target/app.py
```

접속: `http://127.0.0.1:8080`

## recon-agent 테스트 시 입력값

```
target = "http://127.0.0.1:8080"
scope  = ["127.0.0.1", "localhost"]
```

## 심어둔 연습용 결함 (일부러 만든 것 — 실제 서비스에 쓰면 안 됨)

| Endpoint | 결함 종류 | 대응 Agent |
|---|---|---|
| `GET /search?q=` | 입력값을 이스케이프 없이 반영 (Reflected XSS류) | Injection Agent |
| `GET /api/user?id=` | 소유권 확인 없이 id만으로 다른 사용자 정보 조회 가능 | IDOR/Authorization Agent |
| `GET /admin` | 로그인/권한 검사 없이 접근 가능 | IDOR/Authorization Agent |
| `GET /api/order?price=&qty=` | 가격/수량을 클라이언트가 임의 지정, 검증 없음 | Web Logic Agent |

응답 헤더에는 recon 연습(서비스/기술스택 추정)을 위한 가짜 배너(`Server: Apache/2.4.41 (Ubuntu) [lab-dummy]`, `PHPSESSID` 쿠키)가 붙어 있습니다 — 실제로는 이 파이썬 서버가 응답하는 것이며, 배너는 연습을 위해 흉내낸 것입니다.

## 종료

터미널에서 `Ctrl+C`. 또는 프로세스를 직접 종료하세요.

---

## Lab Target 2 (`app2.py`) — 능동 탐색 + 카테고리 확장 테스트용

`app.py`는 모든 endpoint가 홈페이지 링크로 다 드러나 있어서, recon-agent가 능동 탐색
도구(ffuf)까지 실제로 승격해서 쓰는지는 검증하지 못했다 (DVWA도 디렉터리
리스팅 덕분에 같은 사각지대가 있었다 — `recon-output/127.0.0.1_8081/attack-surface.md`
참고). `app2.py`는 이 사각지대를 메우기 위한 두 번째 랩이다.

### 안전성

`app.py`와 동일 — `127.0.0.1`에만 바인딩, 표준 라이브러리만 사용, 전부 더미 데이터.
`/fetch?url=`은 서버가 실제로 아웃바운드 HTTP 요청을 보내는 **진짜 SSRF 동작**을
재현한다 — 로컬 전용 연습 환경이라 안전하지만, 외부에 노출된 환경에서는 절대 이렇게
만들면 안 된다.

### 실행

```bash
python lab-target/app2.py
```

접속: `http://127.0.0.1:8082`

### recon-agent 테스트 시 입력값

```
target = "http://127.0.0.1:8082"
scope  = ["127.0.0.1", "localhost"]
```

### 탐색 난이도 설계 — 절반은 링크로, 절반은 완전히 숨김

| Endpoint | 홈페이지 링크 | robots.txt 언급 | 정상적으로 발견되는 방법 |
|---|---|---|---|
| `/search?q=` | ✅ 있음 | — | 수동 탐색(링크 파싱)으로 발견되어야 정상 |
| `/user?id=` | ✅ 있음 | — | 수동 탐색(링크 파싱)으로 발견되어야 정상 |
| `/upload` | ❌ 없음 | ❌ 없음 | **능동 탐색(ffuf)으로만** 발견되어야 정상 |
| `/admin` | ❌ 없음 | ❌ 없음 | 능동 탐색으로 발견되거나, `/fetch?url=`을 통한 SSRF 피벗으로 도달 |
| `/fetch?url=` | ❌ 없음 | ❌ 없음 | **능동 탐색(ffuf)으로만** 발견되어야 정상 |

`/upload`, `/admin`, `/fetch`를 SKILL.md Step 4의 수동 방법(robots.txt/링크/JS 파싱/
wayback)만으로 찾았다면, 그건 recon-agent가 실제로 능동 탐색을 승격하지 않고도 답을
맞혔다는 뜻이므로 — 오히려 채점 실패에 가깝다. `tools/wordlists/common.txt`에 `upload`,
`admin`, `fetch`가 포함되어 있는지 먼저 확인해두면 좋다 (없으면 ffuf를 돌려도 못 찾음).

### 심어둔 연습용 결함

| Endpoint | 결함 종류 | 대응 카테고리 |
|---|---|---|
| `GET /search?q=` | 입력값을 이스케이프 없이 반영 (Reflected XSS류) | Injection |
| `GET /user?id=` | 소유권 확인 없이 id만으로 다른 사용자 정보 조회 가능 | IDOR/Authorization |
| `POST /upload` (`filename=`) | 확장자/콘텐츠 타입 검증 없이 임의 파일명 업로드 허용 | **File Upload** — 지금 후속 Agent 체계(Injection/IDOR·Authorization/Web Logic)에 안 맞음. recon-agent가 어떻게 분류하는지가 관찰 포인트 |
| `GET /admin` | 로그인/권한 검사 없이 접근 가능 | IDOR/Authorization |
| `GET /fetch?url=` | 목적지 URL 허용목록/사설 IP 차단 없이 서버가 그대로 아웃바운드 요청 (SSRF). `?url=http://127.0.0.1:8082/admin`으로 숨겨진 `/admin`에 서버를 거쳐 도달 가능 | **SSRF** — 마찬가지로 기존 3개 카테고리에 안 맞음. `Other`로 가는지 관찰 |

응답 헤더에는 `app.py`(Apache+PHP 흉내)와 다른 스택을 흉내내는 가짜 배너가 붙어 있다
(`Server: nginx/1.24.0`, `X-Powered-By: Express`, `connect.sid` 쿠키 — Node/Express처럼
보이게 구성) — 실제로는 이 파이썬 서버가 응답하는 것이며, 배너는 기술스택 추정 연습을
다양화하기 위한 것이다.

### 종료

터미널에서 `Ctrl+C`. 또는 프로세스를 직접 종료하세요.

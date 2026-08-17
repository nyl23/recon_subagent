#!/usr/bin/env python3
"""
recon-agent 연습용 로컬 랩 타겟 #2 (LAB TARGET 2)

app.py(:8080)와 다른 걸 테스트하기 위해 만든 두 번째 더미 앱이다:
- app.py는 모든 endpoint가 홈페이지 링크로 다 드러나 있어서(전부 수동 발견 가능),
  recon-agent가 능동 탐색 도구(gobuster/ffuf)까지 실제로 승격해서 쓰는지는
  검증하지 못했다 (DVWA 테스트도 디렉터리 리스팅 덕분에 같은 사각지대가 있었다).
- 이 앱은 endpoint 절반은 홈페이지에서 링크로 노출하고(수동 탐색으로 발견되어야 정상),
  나머지 절반은 링크도 robots.txt도 없이 완전히 숨겨둔다(수동 탐색으로는 못 찾고,
  gobuster/ffuf 같은 능동 탐색으로 승격해야만 발견 가능해야 정상) — SKILL.md Step 4의
  "수동 우선, 부족하면 능동" 절차가 실제로 승격되는지 그대로 채점할 수 있다.
- 취약점 카테고리도 5종으로 늘렸다: Injection / IDOR / File Upload / Authorization / SSRF.
  File Upload와 SSRF는 현재 후속 Agent 체계(Injection/IDOR·Authorization/Web Logic)에
  깔끔하게 안 맞는 카테고리라서, recon-agent가 이런 걸 만났을 때 Potential Attack Surface에
  어떻게 분류하는지(Other로 보내는지, 억지로 기존 카테고리에 끼워 맞추는지)를 관찰하는
  용도이기도 하다.

- 127.0.0.1 에만 바인딩된다 (외부/네트워크 노출 없음, 이 컴퓨터 밖에서 접근 불가)
- 표준 라이브러리만 사용 (추가 설치 불필요)
- 전부 더미 데이터. 실제 사용자/서비스와 무관하다.
- 학습 목적으로 결함을 "의도적으로" 심어둔 연습용 앱이다. 실제 서비스에 이런 패턴을
  쓰면 절대 안 된다. /fetch?url= 은 서버가 실제로 임의 URL에 아웃바운드 요청을 보내는
  진짜 SSRF 동작을 재현한다 — 127.0.0.1 전용 로컬 연습 환경이라 안전하지만, 외부에
  노출된 환경에서는 절대 이렇게 만들면 안 된다.

실행:
    python app2.py
접속:
    http://127.0.0.1:8082

recon-agent 테스트 시 사용할 값:
    target = "http://127.0.0.1:8082"
    scope  = ["127.0.0.1", "localhost"]
"""
import html
import json
import socketserver
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler

HOST = "127.0.0.1"  # 반드시 loopback에만 바인딩 — 외부 노출 방지
PORT = 8082

# 더미 사용자 데이터 (IDOR 연습용 — id만 바꾸면 다른 사용자 정보가 보임)
FAKE_USERS = {
    "1": {"id": 1, "username": "carol", "email": "carol@lab2.local", "role": "user"},
    "2": {"id": 2, "username": "dave", "email": "dave@lab2.local", "role": "user"},
    "3": {
        "id": 3,
        "username": "root",
        "email": "root@lab2.local",
        "role": "admin",
        "note": "이건 연습용 더미 계정입니다. 실제 자격증명이 아닙니다.",
    },
}

# 업로드 "저장소" — 실제 디스크에 쓰지 않고 메모리에만 유지한다 (프로세스 재시작 시 초기화)
FAKE_UPLOAD_STORE = []

# [의도 설계] 홈페이지에는 이 두 endpoint만 링크로 걸어둔다.
# 나머지(/upload, /admin, /fetch)는 아래 어디에도(HTML, robots.txt) 절대 언급하지 않는다 —
# recon-agent가 수동 방법으로는 못 찾고, gobuster/ffuf 능동 탐색으로만 찾을 수 있어야 한다.
HOME_PAGE = """<!doctype html>
<html><head><title>Lab Notes (recon 연습용 #2)</title></head>
<body>
<h1>Lab Notes</h1>
<p>이 사이트는 recon-agent 연습을 위한 로컬 더미 사이트입니다. 실제 서비스가 아닙니다.</p>
<form action="/search" method="get">
  <input type="text" name="q" placeholder="노트 검색">
  <button type="submit">검색</button>
</form>
<ul>
  <li><a href="/search?q=todo">검색 예시</a></li>
  <li><a href="/user?id=1">내 프로필</a></li>
</ul>
</body></html>"""

ADMIN_PAGE = """<!doctype html>
<html><head><title>Admin</title></head>
<body>
<h1>관리자 대시보드 (더미)</h1>
<p>이 페이지는 원래 로그인/권한 확인이 있어야 하지만, 연습용으로 확인 로직이 없다.
링크로도 노출되지 않는다 — 능동 탐색이나 SSRF 피벗으로만 도달해야 정상이다.</p>
<ul><li>사용자 목록 (더미)</li><li>시스템 설정 (더미)</li></ul>
</body></html>"""

UPLOAD_FORM_PAGE = """<!doctype html>
<html><head><title>Upload</title></head>
<body>
<h1>파일 업로드 (더미)</h1>
<p>확장자/내용 검증 없이 파일명을 그대로 받아 저장한다. POST로 <code>filename</code>
필드를 보내면 저장된 것으로 기록한다 (실제 바이너리 업로드는 흉내만 낸다).</p>
<form action="/upload" method="post">
  <input type="text" name="filename" placeholder="예: shell.php">
  <button type="submit">업로드</button>
</form>
</body></html>"""


class Lab2Handler(BaseHTTPRequestHandler):
    # 응답 헤더에 표시할 서버 배너 (recon의 "서비스/기술스택 추정" 연습을 위한 것 —
    # app.py는 Apache+PHP를 흉내냈으니, 여기서는 nginx 뒤의 Node/Express를 흉내낸다.
    # 실제로는 이 파이썬 서버가 처리한다.
    server_version = "nginx/1.24.0"

    def _send(self, status, body, content_type="text/html; charset=utf-8", extra_headers=None):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Powered-By", "Express")
        self.send_header("Set-Cookie", "connect.sid=s%3Alab2dummy.abcdef; Path=/; HttpOnly")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path == "/":
            self._send(200, HOME_PAGE)

        elif path == "/robots.txt":
            # [의도 설계] 숨긴 endpoint(/upload, /admin, /fetch)는 여기 절대 언급하지 않는다.
            self._send(200, "User-agent: *\nDisallow: /\n", "text/plain; charset=utf-8")

        elif path == "/search":
            q = params.get("q", [""])[0]
            # [의도적 취약점] Reflected XSS 연습용: q를 이스케이프 없이 그대로 응답에 반영한다.
            body = (
                "<!doctype html><html><body>"
                f"<h2>검색 결과: {q}</h2>"
                f"<p>'{q}'에 대한 노트를 찾지 못했습니다.</p>"
                "</body></html>"
            )
            self._send(200, body)

        elif path == "/user":
            uid = params.get("id", [None])[0]
            # [의도적 취약점] IDOR 연습용: 인증/소유권 확인 없이 id만으로 다른 사용자 정보를 반환한다.
            user = FAKE_USERS.get(uid)
            if user is None:
                self._send(404, json.dumps({"error": "not found"}), "application/json")
            else:
                self._send(200, json.dumps(user, ensure_ascii=False), "application/json")

        elif path == "/upload":
            # 링크로 노출되지 않는 숨김 endpoint. GET은 업로드 폼만 보여준다.
            self._send(200, UPLOAD_FORM_PAGE)

        elif path == "/admin":
            # [의도적 취약점] Authorization 연습용: 로그인/권한 검사 없이 누구나 접근 가능하다.
            # 링크로 노출되지 않는 숨김 endpoint — SSRF 피벗(/fetch?url=.../admin)으로도 도달 가능.
            self._send(200, ADMIN_PAGE)

        elif path == "/fetch":
            target_url = params.get("url", [None])[0]
            # [의도적 취약점] SSRF 연습용: 목적지 URL에 대한 허용목록/사설IP 차단 없이
            # 서버가 그대로 아웃바운드 요청을 보내고 응답 일부를 돌려준다.
            # 예: /fetch?url=http://127.0.0.1:8082/admin 으로 숨겨진 /admin에 서버를 거쳐 도달 가능.
            if not target_url:
                self._send(400, json.dumps({"error": "url parameter required"}), "application/json")
                return
            try:
                with urllib.request.urlopen(target_url, timeout=3) as resp:
                    fetched = resp.read(2048).decode("utf-8", errors="replace")
                self._send(
                    200,
                    json.dumps({"requested_url": target_url, "body_snippet": fetched}, ensure_ascii=False),
                    "application/json",
                )
            except (urllib.error.URLError, ValueError, TimeoutError) as e:
                self._send(
                    502,
                    json.dumps({"requested_url": target_url, "error": str(e)}, ensure_ascii=False),
                    "application/json",
                )

        else:
            self._send(404, "<html><body><h1>404 Not Found</h1></body></html>")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/upload":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode("utf-8", errors="replace")
            params = urllib.parse.parse_qs(raw)
            filename = params.get("filename", [""])[0]
            # [의도적 취약점] File Upload 연습용: 확장자/콘텐츠 타입 검증이 전혀 없다.
            # .php, .jsp, .exe 등 어떤 확장자든 그대로 "저장"(메모리 기록)한다.
            FAKE_UPLOAD_STORE.append(filename)
            body = (
                "<!doctype html><html><body>"
                f"<p>업로드됨: {html.escape(filename)}</p>"
                f"<p>지금까지 업로드된 파일 수: {len(FAKE_UPLOAD_STORE)}</p>"
                "</body></html>"
            )
            self._send(200, body)
        else:
            self._send(404, "<html><body><h1>404 Not Found</h1></body></html>")

    def log_message(self, format, *args):
        # 콘솔에 매 요청 로그를 남기되 표준 stderr로만 (별도 파일 기록 안 함)
        super().log_message(format, *args)


def main():
    with socketserver.ThreadingTCPServer((HOST, PORT), Lab2Handler) as httpd:
        print(f"[lab-target-2] http://{HOST}:{PORT} 에서 실행 중 (Ctrl+C로 종료)")
        print("[lab-target-2] 이 서버는 127.0.0.1에만 바인딩되어 외부에서 접근할 수 없습니다.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[lab-target-2] 종료합니다.")


if __name__ == "__main__":
    main()

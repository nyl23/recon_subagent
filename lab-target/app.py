#!/usr/bin/env python3
"""
recon-agent 연습용 로컬 랩 타겟 (LAB TARGET)

- 127.0.0.1 에만 바인딩된다 (외부/네트워크 노출 없음, 이 컴퓨터 밖에서 접근 불가)
- 표준 라이브러리만 사용 (추가 설치 불필요)
- 전부 더미 데이터. 실제 사용자/서비스와 무관하다.
- 학습 목적으로 SQL/XSS/IDOR/Authorization/Web Logic 결함을 "의도적으로" 심어둔 연습용 앱이다.
  실제 서비스에 이런 패턴을 쓰면 안 된다.

실행:
    python app.py
접속:
    http://127.0.0.1:8080

recon-agent 테스트 시 사용할 값:
    target = "http://127.0.0.1:8080"
    scope  = ["127.0.0.1", "localhost"]
"""
import html
import json
import socketserver
import urllib.parse
from http.server import BaseHTTPRequestHandler

HOST = "127.0.0.1"  # 반드시 loopback에만 바인딩 — 외부 노출 방지
PORT = 8080

# 더미 사용자 데이터 (IDOR 연습용 — id만 바꾸면 다른 사용자 정보가 보임)
FAKE_USERS = {
    "1": {"id": 1, "username": "alice", "email": "alice@lab.local", "role": "user"},
    "2": {"id": 2, "username": "bob", "email": "bob@lab.local", "role": "user"},
    "3": {
        "id": 3,
        "username": "admin",
        "email": "admin@lab.local",
        "role": "admin",
        "note": "이건 연습용 더미 계정입니다. 실제 자격증명이 아닙니다.",
    },
}

HOME_PAGE = """<!doctype html>
<html><head><title>Lab Shop (recon 연습용)</title></head>
<body>
<h1>Lab Shop</h1>
<p>이 사이트는 recon-agent 연습을 위한 로컬 더미 사이트입니다. 실제 서비스가 아닙니다.</p>
<form action="/search" method="get">
  <input type="text" name="q" placeholder="상품 검색">
  <button type="submit">검색</button>
</form>
<ul>
  <li><a href="/search?q=laptop">검색 예시</a></li>
  <li><a href="/api/user?id=1">내 프로필 (API)</a></li>
  <li><a href="/admin">관리자 페이지</a></li>
  <li><a href="/api/order?price=100&qty=1">주문(체크아웃) API</a></li>
</ul>
</body></html>"""

ADMIN_PAGE = """<!doctype html>
<html><head><title>Admin</title></head>
<body>
<h1>관리자 대시보드 (더미)</h1>
<p>이 페이지는 원래 로그인/권한 확인이 있어야 하지만, 연습용으로 확인 로직이 없습니다.</p>
<ul><li>사용자 목록 (더미)</li><li>시스템 설정 (더미)</li></ul>
</body></html>"""


class LabHandler(BaseHTTPRequestHandler):
    # 응답 헤더에 표시할 서버 배너 (recon의 "서비스/기술스택 추정" 연습을 위한 것 — 실제 Apache 아님)
    server_version = "Apache/2.4.41 (Ubuntu) [lab-dummy]"

    def _send(self, status, body, content_type="text/html; charset=utf-8"):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        # 기술스택 추정 연습용 쿠키 시그니처 (PHP인 척 — 실제로는 이 파이썬 서버가 처리)
        self.send_header("Set-Cookie", "PHPSESSID=labdummy1234; Path=/")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path == "/":
            self._send(200, HOME_PAGE)

        elif path == "/robots.txt":
            self._send(
                200,
                "User-agent: *\nDisallow: /admin\nDisallow: /api/\n",
                "text/plain; charset=utf-8",
            )

        elif path == "/search":
            q = params.get("q", [""])[0]
            # [의도적 취약점] Reflected XSS 연습용: q를 이스케이프 없이 그대로 응답에 반영한다.
            body = (
                "<!doctype html><html><body>"
                f"<h2>검색 결과: {q}</h2>"
                f"<p>'{q}'에 대한 상품을 찾지 못했습니다.</p>"
                "</body></html>"
            )
            self._send(200, body)

        elif path == "/api/user":
            uid = params.get("id", [None])[0]
            # [의도적 취약점] IDOR 연습용: 인증/소유권 확인 없이 id만으로 다른 사용자 정보를 반환한다.
            user = FAKE_USERS.get(uid)
            if user is None:
                self._send(404, json.dumps({"error": "not found"}), "application/json")
            else:
                self._send(200, json.dumps(user, ensure_ascii=False), "application/json")

        elif path == "/admin":
            # [의도적 취약점] Authorization 연습용: 로그인/권한 검사 없이 누구나 접근 가능하다.
            self._send(200, ADMIN_PAGE)

        elif path == "/api/order":
            # [의도적 취약점] Web Logic 연습용: price/qty를 클라이언트가 임의로 지정 가능하고
            # 음수/이상값에 대한 검증이 없어 total이 비정상적으로 계산될 수 있다.
            price = params.get("price", ["100"])[0]
            qty = params.get("qty", ["1"])[0]
            try:
                total = float(price) * float(qty)
            except ValueError:
                total = None
            self._send(
                200,
                json.dumps({"price": price, "qty": qty, "total": total}, ensure_ascii=False),
                "application/json",
            )

        else:
            self._send(404, "<html><body><h1>404 Not Found</h1></body></html>")

    def log_message(self, format, *args):
        # 콘솔에 매 요청 로그를 남기되 표준 stderr로만 (별도 파일 기록 안 함)
        super().log_message(format, *args)


def main():
    with socketserver.ThreadingTCPServer((HOST, PORT), LabHandler) as httpd:
        print(f"[lab-target] http://{HOST}:{PORT} 에서 실행 중 (Ctrl+C로 종료)")
        print("[lab-target] 이 서버는 127.0.0.1에만 바인딩되어 외부에서 접근할 수 없습니다.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[lab-target] 종료합니다.")


if __name__ == "__main__":
    main()

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

PAGE = Path(__file__).with_name("index.html").read_bytes()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.respond(send_body=True)

    def do_HEAD(self):
        self.respond(send_body=False)

    def respond(self, send_body):
        path = urlsplit(self.path).path
        content_type = "text/plain; charset=utf-8"
        status = 200
        if path == "/":
            body = PAGE
            content_type = "text/html; charset=utf-8"
        elif path == "/healthz":
            body = b"ok\n"
        else:
            status = 404
            body = b"Not found\n"
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if send_body:
            self.wfile.write(body)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    with ThreadingHTTPServer(("0.0.0.0", port), Handler) as server:
        print(f"Listening on port {port}", flush=True)
        server.serve_forever()

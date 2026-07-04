#!/usr/bin/env python3
"""n8n webhook endpoint — expose auto_route to no-code workflows.

    python -m skills.webhooks.n8n_endpoint [--port 8769]

Listens for POST /auto_route with JSON body {prompt, task_type}.
Returns routing decision as JSON.
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import sys


class RouteHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/auto_route":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        from skills.auto_router import auto_route
        result = auto_route(body.get("prompt", ""), body.get("task_type", ""))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(result, indent=2).encode())

    def log_message(self, format, *args):
        pass  # silent


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8769
    server = HTTPServer(("0.0.0.0", port), RouteHandler)
    print(f"n8n webhook → http://localhost:{port}/auto_route")
    server.serve_forever()


if __name__ == "__main__":
    main()

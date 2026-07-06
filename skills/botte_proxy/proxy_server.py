"""Botte Proxy — transparent LLM proxy with universal compression.

Acts as a local HTTP proxy that sits between your AI agent and the LLM API.
All requests are compressed before being forwarded, reducing token consumption
by 40-95% while preserving answer quality.

Usage:
    botte proxy --port 8787
    botte proxy --target https://api.openai.com/v1
    botte proxy --target http://192.168.1.47:11434/v1  # Ollama/LocalAI
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class ProxyStats:
    """Aggregate proxy statistics."""
    total_requests: int = 0
    total_input_tokens_saved: int = 0
    total_input_tokens_original: int = 0
    total_output_tokens_saved: int = 0
    total_output_tokens_original: int = 0
    total_time_ms: float = 0.0
    errors: int = 0
    requests_by_model: dict[str, int] = field(default_factory=dict)
    savings_by_model: dict[str, dict] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)

    @property
    def input_savings_ratio(self) -> float:
        if self.total_input_tokens_original == 0:
            return 0.0
        return round(self.total_input_tokens_saved / self.total_input_tokens_original * 100, 1)

    @property
    def avg_time_ms(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return round(self.total_time_ms / self.total_requests, 1)

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self.start_time

    def record_request(
        self,
        model: str,
        input_original: int,
        input_compressed: int,
        output_original: int = 0,
        output_compressed: int = 0,
        time_ms: float = 0.0,
        error: bool = False,
    ):
        self.total_requests += 1
        self.total_input_tokens_original += input_original
        self.total_input_tokens_saved += input_original - input_compressed
        self.total_output_tokens_original += output_original
        self.total_output_tokens_saved += output_original - output_compressed
        self.total_time_ms += time_ms
        if error:
            self.errors += 1
        self.requests_by_model[model] = self.requests_by_model.get(model, 0) + 1
        if model not in self.savings_by_model:
            self.savings_by_model[model] = {"input_saved": 0, "input_total": 0, "output_saved": 0, "output_total": 0}
        self.savings_by_model[model]["input_saved"] += input_original - input_compressed
        self.savings_by_model[model]["input_total"] += input_original
        self.savings_by_model[model]["output_saved"] += output_original - output_compressed
        self.savings_by_model[model]["output_total"] += output_original

    def to_dict(self) -> dict:
        return {
            "total_requests": self.total_requests,
            "total_input_tokens_saved": self.total_input_tokens_saved,
            "total_input_tokens_original": self.total_input_tokens_original,
            "input_savings_pct": self.input_savings_ratio,
            "total_output_tokens_saved": self.total_output_tokens_saved,
            "total_output_tokens_original": self.total_output_tokens_original,
            "avg_time_ms": self.avg_time_ms,
            "errors": self.errors,
            "uptime_seconds": round(self.uptime_seconds, 1),
            "requests_by_model": self.requests_by_model,
            "savings_by_model": self.savings_by_model,
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
        }


# Global stats singleton
_stats = ProxyStats()


def get_stats() -> ProxyStats:
    return _stats


def estimate_tokens(text: str) -> int:
    """Rough token estimation (~4 chars per token)."""
    return max(1, len(text) // 4)


def compress_messages(messages: list[dict]) -> tuple[list[dict], int, int]:
    """Compress a messages array for an LLM request.

    Compresses each message's content field using the universal compressor.
    Returns (compressed_messages, original_tokens, compressed_tokens).
    """
    from skills.universal_compressor.compressor import compress

    original_size = 0
    compressed_size = 0
    compressed = []

    for msg in messages:
        content = msg.get("content", "")
        role = msg.get("role", "")

        if isinstance(content, str) and content.strip():
            orig_tokens = estimate_tokens(content)
            original_size += orig_tokens

            # Choose strategy based on role and content
            if role == "system":
                ctype = "text"
            elif role == "tool":
                ctype = "tool_output"
            elif len(content) > 1000:
                ctype = "auto"
            else:
                ctype = "text"

            result = compress(content, content_type=ctype, reversible=False)
            comp_tokens = estimate_tokens(result.data)
            compressed_size += comp_tokens

            new_msg = dict(msg)
            new_msg["content"] = result.data
            compressed.append(new_msg)
        else:
            compressed.append(msg)
            if isinstance(content, str):
                original_size += estimate_tokens(content)
                compressed_size += estimate_tokens(content)

    return compressed, original_size, compressed_size


def create_proxy_app(target_url: str, api_key: Optional[str] = None):
    """Create a WSGI/ASGI-like proxy application that compresses LLM requests.

    Args:
        target_url: The upstream LLM API endpoint (e.g. http://localhost:11434/v1)
        api_key: Optional API key for the upstream endpoint

    Returns:
        A callable that handles HTTP requests (standard library http.server handler)
    """
    import http.server
    import urllib.request
    import urllib.error

    class CompressingProxyHandler(http.server.BaseHTTPRequestHandler):
        """HTTP request handler that compresses requests before forwarding."""

        def _get_target_url(self) -> str:
            """Build the upstream URL from the incoming request."""
            return target_url.rstrip("/") + self.path

        def _forward_request(self, body: Optional[bytes] = None) -> dict:
            """Forward a request to the upstream API and return the response."""
            target = self._get_target_url()
            headers = {
                "Content-Type": "application/json",
            }
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            req = urllib.request.Request(
                target,
                data=body,
                headers=headers,
                method=self.command,
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    resp_body = resp.read()
                    return {
                        "status": resp.status,
                        "headers": dict(resp.headers),
                        "body": resp_body,
                    }
            except urllib.error.HTTPError as e:
                return {
                    "status": e.code,
                    "headers": dict(e.headers),
                    "body": e.read(),
                }
            except Exception as e:
                return {
                    "status": 502,
                    "headers": {"Content-Type": "text/plain"},
                    "body": str(e).encode(),
                }

        def _send_response(self, response: dict):
            """Send the proxied response back to the client."""
            self.send_response(response["status"])
            for key, value in response.get("headers", {}).items():
                # Skip transfer-encoding/chunked — we're sending the full body
                if key.lower() in ("transfer-encoding", "content-encoding", "content-length"):
                    continue
                self.send_header(key, value)
            body = response.get("body", b"")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _compress_and_forward_chat(self, body_dict: dict) -> dict:
            """Compress a chat/completions request and forward it.
            
            Also applies output reduction:
            - Verbosity steering (system prompt injection) on the request
            - Content trimming on the response
            """
            start = time.time()
            model = body_dict.get("model", "unknown")
            messages = body_dict.get("messages", [])

            # ═══ Output reduction: verbosity steering ═══
            from skills.botte_proxy.output_shaper import (
                add_verbosity_steer, shape_response, should_shape,
            )
            apply_output_shaping = should_shape()

            if apply_output_shaping:
                shaped_messages = add_verbosity_steer(messages)
            else:
                shaped_messages = messages

            # Compress messages (input side)
            compressed_messages, orig_tokens, comp_tokens = compress_messages(shaped_messages)

            # Build compressed request
            compressed_body = dict(body_dict)
            compressed_body["messages"] = compressed_messages

            body_bytes = json.dumps(compressed_body).encode()

            # Forward
            response = self._forward_request(body_bytes)
            elapsed_ms = (time.time() - start) * 1000

            # ═══ Output reduction: shape the response ═══
            output_original = 0
            output_compressed = 0
            try:
                if response.get("body"):
                    resp_json = json.loads(response["body"])
                    if "choices" in resp_json:
                        shaped_json, output_original, output_compressed = shape_response(
                            resp_json, shaped=apply_output_shaping
                        )
                        response["body"] = json.dumps(shaped_json).encode()
                    # Also parse usage info
                    if "usage" in resp_json:
                        usage = resp_json["usage"]
                        if output_original == 0:
                            output_original = usage.get("completion_tokens", 0)
                        if output_compressed == 0:
                            output_compressed = output_original
            except (json.JSONDecodeError, KeyError, Exception) as e:
                pass

            # Record stats
            stats = get_stats()
            stats.record_request(
                model=model,
                input_original=orig_tokens,
                input_compressed=comp_tokens,
                output_original=output_original,
                output_compressed=output_compressed,
                time_ms=elapsed_ms,
                error=response["status"] >= 400,
            )

            # Log
            savings = round((1 - comp_tokens / max(orig_tokens, 1)) * 100, 1)
            out_savings = ""
            if output_original > 0:
                out_pct = round((1 - output_compressed / max(output_original, 1)) * 100, 1)
                out_savings = f" / out: {output_original}→{output_compressed} ({out_pct}%)"
            print(f"  📊 {model}: in {orig_tokens}→{comp_tokens} tok ({savings}% saved){out_savings} in {elapsed_ms:.0f}ms")

            return response

        def _handle_stats(self):
            """Return proxy statistics as JSON."""
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(get_stats().to_dict()).encode())

        def _handle_dashboard(self):
            """Return a simple HTML dashboard."""
            stats = get_stats().to_dict()
            html = f"""<!DOCTYPE html>
<html><head><title>Botte Proxy Dashboard</title>
<style>
body {{ font-family: monospace; background: #1a1a2e; color: #e0e0e0; padding: 2rem; }}
h1 {{ color: #9b59b6; }}
.card {{ background: #16213e; border-radius: 8px; padding: 1rem; margin: 1rem 0; }}
.value {{ font-size: 2rem; color: #2ecc71; }}
.label {{ color: #7f8c8d; font-size: 0.8rem; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ padding: 0.5rem; text-align: left; border-bottom: 1px solid #333; }}
th {{ color: #9b59b6; }}
.model {{ color: #3498db; }}
.savings {{ color: #2ecc71; }}
</style></head><body>
<h1>🧦 Botte Secrète Proxy</h1>
<div class="card">
  <div class="value">{stats['total_requests']}</div>
  <div class="label">Total Requests</div>
</div>
<div class="card">
  <div class="value">{stats['total_input_tokens_saved']:,} / {stats['total_input_tokens_original']:,}</div>
  <div class="label">Input Tokens Saved / Total ({stats['input_savings_pct']}%)</div>
</div>
<div class="card">
  <div class="value">{stats['total_output_tokens_saved']:,} / {stats['total_output_tokens_original']:,}</div>
  <div class="label">Output Tokens Saved / Total ({round(stats['total_output_tokens_saved']/max(stats['total_output_tokens_original'],1)*100,1)}%)</div>
</div>
<div class="card">
  <div class="value">{stats['avg_time_ms']} ms</div>
  <div class="label">Avg Response Time</div>
</div>
<div class="card">
  <div class="value">{stats['errors']}</div>
  <div class="label">Errors</div>
</div>
<h2>Per-Model Savings</h2>
<table>
<tr><th>Model</th><th>Requests</th><th>Tokens Saved</th><th>Total Tokens</th><th>Savings %</th></tr>
{''.join(
    f'<tr><td class="model">{m}</td><td>{_stats.requests_by_model[m]}</td>'
    f'<td class="savings">{_stats.savings_by_model[m]["input_saved"]:,}</td>'
    f'<td>{_stats.savings_by_model[m]["input_total"]:,}</td>'
    f'<td class="savings">{round(_stats.savings_by_model[m]["input_saved"]/max(_stats.savings_by_model[m]["input_total"],1)*100,1)}%</td></tr>'
    for m in _stats.requests_by_model
)}
</table>
<p style="color:#7f8c8d;margin-top:2rem;">Uptime: {stats['uptime_seconds']:.0f}s · Started: {stats['start_time']}</p>
</body></html>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html.encode())

        def do_GET(self):
            if self.path == "/stats":
                self._handle_stats()
            elif self.path in ("/", "/dashboard"):
                self._handle_dashboard()
            else:
                # Forward GET as-is (for models list, etc.)
                response = self._forward_request()
                self._send_response(response)

        def do_POST(self):
            # Read body
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else b""

            # Parse JSON
            try:
                body_dict = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"error": "Invalid JSON"}')
                return

            # Check if this is a chat completion request
            is_chat = "/chat/completions" in self.path or "/v1/chat/completions" in self.path
            is_completions = "/completions" in self.path and not is_chat

            if is_chat and "messages" in body_dict:
                response = self._compress_and_forward_chat(body_dict)
            else:
                # Forward as-is
                start = time.time()
                response = self._forward_request(body)
                elapsed_ms = (time.time() - start) * 1000
                # Record minimal stats for non-chat requests
                get_stats().record_request(
                    model=body_dict.get("model", "unknown"),
                    input_original=estimate_tokens(body.decode() if isinstance(body, bytes) else str(body)),
                    input_compressed=estimate_tokens(body.decode() if isinstance(body, bytes) else str(body)),
                    time_ms=elapsed_ms,
                    error=response["status"] >= 400,
                )

            self._send_response(response)

        def log_message(self, format, *args):
            # Suppress default logging
            pass

    return CompressingProxyHandler


def run_proxy(
    host: str = "0.0.0.0",
    port: int = 8787,
    target_url: str = "http://localhost:11434/v1",
    api_key: Optional[str] = None,
):
    """Run the botte proxy server.

    Args:
        host: Bind address
        port: Listen port
        target_url: Upstream LLM API endpoint
        api_key: Optional API key
    """
    import http.server

    handler = create_proxy_app(target_url, api_key)
    server = http.server.HTTPServer((host, port), handler)

    print(f"🧦 Botte Proxy running on http://{host}:{port}")
    print(f"   → Forwarding to: {target_url}")
    print(f"   → Dashboard: http://localhost:{port}/dashboard")
    print(f"   → Stats: http://localhost:{port}/stats")
    print(f"   (Ctrl+C to stop)")
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()

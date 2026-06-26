"""patterns — database of security patterns (regex + metadata).

Each pattern is a dict:
    name: str                  — check identifier
    severity: Severity         — critical, error, warning, info
    description: str           — what this detects
    regex: str                 — regex pattern
    example_bad: str           — example of bad code
    example_good: str          — example of safer alternative
    ast_check: bool            — whether AST analysis can verify
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Severity(Enum):
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Pattern:
    name: str
    severity: Severity
    description: str
    regex: str
    example_bad: str = ""
    example_good: str = ""
    ast_check: bool = False


# ── Pattern database ──

PATTERNS: list[Pattern] = [
    # ══ Dangerous imports ══
    Pattern("eval_call", Severity.CRITICAL,
            "eval() with non-literal argument — code injection risk",
            r"eval\s*\(", "eval(user_input)", "ast.literal_eval(user_input)",
            ast_check=True),
    Pattern("exec_call", Severity.CRITICAL,
            "exec() with non-literal argument — code injection risk",
            r"exec\s*\(", "exec(code_string)", "subprocess.run([...])",
            ast_check=True),
    Pattern("compile_call", Severity.ERROR,
            "compile() — can be used for dynamic code execution",
            r"compile\s*\(", "compile(source, '<string>', 'exec')",
            "Use pre-compiled modules instead",
            ast_check=True),
    Pattern("import_call", Severity.ERROR,
            "__import__() bypasses normal import checks",
            r"__import__\s*\(", "__import__('os')", "import os",
            ast_check=True),

    # ══ Network exfiltration ══
    Pattern("requests_to_ip", Severity.CRITICAL,
            "requests.post/get to a hardcoded IP address",
            r"requests\.(get|post|put|delete)\s*\(\s*[\"']https?://\d{1,3}\.\d{1,3}\.\d{1,3}",
            'requests.post("http://192.168.1.1:9999/data")',
            "requests.post(\"https://api.example.com/data\")"),
    Pattern("urllib_external", Severity.WARNING,
            "urllib.request to external URL — potential exfiltration",
            r"urllib\.request\.(urlopen|Request)\s*\(\s*[\"']https?://",
            'urllib.request.urlopen("http://evil.com")',
            "Use environment-specific config for URLs"),
    Pattern("socket_connect", Severity.WARNING,
            "socket.connect() — raw network connection",
            r"socket\.\w*connect\s*\(",
            "s.connect(('attacker.com', 4444))",
            "Use higher-level APIs with whitelisted endpoints"),

    # ══ Filesystem abuse ══
    Pattern("open_write_critical", Severity.ERROR,
            "open() with write mode to sensitive paths",
            r"open\s*\(\s*[\"']/(etc|boot|dev|proc|sys|root)/",
            'open("/etc/passwd", "w")',
            "Write only to project directory"),
    Pattern("open_write_relative", Severity.WARNING,
            "open() with write mode — verify path is intended",
            r"open\s*\([^)]*[\"'][^\"']*[\"'][^)]*[\"']w[\"']",
            'open("../secrets.txt", "w")',
            "Use pathlib with explicit project paths"),
    Pattern("tempfile_unsafe", Severity.WARNING,
            "tempfile with predictable names — race condition risk",
            r"tempfile\.(mktemp|TemporaryFile|NamedTemporaryFile)",
            'tempfile.mktemp()', "tempfile.mkstemp()",
            ast_check=True),

    # ══ Subprocess injection ══
    Pattern("subprocess_shell", Severity.CRITICAL,
            "subprocess.run/call with shell=True — command injection",
            r"subprocess\.\w+\s*\(.*shell\s*=\s*True",
            'subprocess.run(f"rm {file}", shell=True)',
            "subprocess.run([\"rm\", file])"),
    Pattern("os_system", Severity.CRITICAL,
            "os.system() — shell command injection risk",
            r"os\.system\s*\(", 'os.system(f"rm {file}")',
            "subprocess.run([...])"),
    Pattern("os_popen", Severity.ERROR,
            "os.popen() — shell command injection risk",
            r"os\.popen\s*\(", 'os.popen("ls " + path)',
            "subprocess.run([...], capture_output=True)"),
    Pattern("shutil_rmtree", Severity.WARNING,
            "shutil.rmtree() — recursive delete, verify path",
            r"shutil\.rmtree\s*\(", 'shutil.rmtree("/important")',
            "Validate path before rmtree"),
    Pattern("glob_injection", Severity.WARNING,
            "glob with user input — path traversal risk",
            r"glob\.\w+\s*\(\s*.*input|glob\.\w+\s*\(\s*.*f[\"']",
            'glob.glob(f"data/{user_input}/*")',
            "Restrict glob patterns to known prefixes"),

    # ══ Obfuscation ══
    Pattern("base64_decode", Severity.CRITICAL,
            "base64 decode followed by exec/eval — obfuscated code",
            r"base64\.(b64decode|standard_b64decode|urlsafe_b64decode)",
            'exec(base64.b64decode("cHJpbnQoJ2hlbGxvJyk="))',
            "Avoid base64-encoded code in source"),
    Pattern("bytes_decode_obfuscation", Severity.WARNING,
            "bytes([...]).decode() pattern — potential obfuscation",
            r"bytes\s*\(\[.*\]\)\s*\.decode\s*",
            'bytes([112, 114, 105]).decode()',
            "Use plain string literals"),
    Pattern("xor_obfuscation", Severity.WARNING,
            "XOR loop on bytes — common obfuscation technique",
            r"(for|while).*(xor|\^).*(ord|chr)",
            "for i in range(len(d)): d[i] ^= key[i % len(key)]",
            "Avoid custom XOR decryption in source"),
    Pattern("exec_from_string", Severity.CRITICAL,
            "exec() from a string variable — code injection",
            r"exec\s*\(\s*[\"']",
            'exec("import os; os.system(\"ls\")")',
            "Use proper modules instead of dynamic exec"),

    # ══ Crypto weakness ══
    Pattern("md5_usage", Severity.WARNING,
            "MD5 is cryptographically broken — use SHA-256+",
            r"(hashlib\.md5|md5\s*\()",
            'hashlib.md5(data).hexdigest()',
            'hashlib.sha256(data).hexdigest()'),
    Pattern("sha1_usage", Severity.WARNING,
            "SHA-1 is cryptographically broken — use SHA-256+",
            r"(hashlib\.sha1|sha1\s*\()",
            'hashlib.sha1(data).hexdigest()',
            'hashlib.sha256(data).hexdigest()'),
    Pattern("weak_rsa", Severity.ERROR,
            "RSA key < 2048 bits — cryptographically weak",
            r"RSA\.generate\s*\(\s*[0-9]{1,3}[^0-9]",
            "RSA.generate(512)", "RSA.generate(2048)"),
    Pattern("hardcoded_key_hint", Severity.WARNING,
            "Hardcoded-looking string close to crypto operation",
            r"(sk|pk|secret|key|token|password)\s*=\s*[\"'][A-Za-z0-9+/=_\-]{20,}[\"']",
            'api_key = "sk-1234567890abcdef1234567890abcdef"',
            "Use environment variables or a secrets manager"),

    # ══ Environment leak ══
    Pattern("print_environ", Severity.ERROR,
            "Printing environment variables — potential secret leak",
            r"print\s*\(.*os\.environ",
            'print(os.environ["API_KEY"])',
            "Log only non-sensitive metadata"),
    Pattern("environ_in_string", Severity.WARNING,
            "Environment variable interpolated into string",
            r"os\.environ\[[\"'][A-Z_]{3,}[\"']\]",
            'url = f"https://{os.environ["TOKEN"]}@api.com"',
            "Use config objects that handle secrets safely"),
    Pattern("send_environ", Severity.CRITICAL,
            "Sending environment variables over network",
            r"(requests|urllib|socket|aiohttp).*os\.environ",
            'requests.post(url, data=os.environ)',
            "Never transmit environment variables"),

    # ══ Supply chain ══
    Pattern("dynamic_import", Severity.ERROR,
            "Dynamic import from variable — arbitrary code execution risk",
            r"(importlib\.import_module|__import__)\s*\([^\"']",
            'importlib.import_module(package_name)',
            "Use a whitelist of allowed packages",
            ast_check=True),
    Pattern("pip_install_from_code", Severity.CRITICAL,
            "pip install called from Python code — supply chain risk",
            r"(pip|subprocess).*install",
            'subprocess.run(["pip", "install", package])',
            "Declare dependencies in pyproject.toml"),
    Pattern("requests_custom_headers_user_agent", Severity.INFO,
            "Custom User-Agent in requests — may fingerprint",
            r"headers.*User-Agent",
            'requests.get(url, headers={"User-Agent": "..."})',
            "Use default User-Agent for anonymity"),
]

# Index by name for quick lookup
PATTERN_MAP: dict[str, Pattern] = {p.name: p for p in PATTERNS}

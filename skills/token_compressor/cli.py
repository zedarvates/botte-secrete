"""Token Compressor — compression token-level (hashing + byte-pair pruning).

Différent du Universal Compressor qui compresse le *contenu* :
celui-ci compresse la *structure token* elle-même.

Stratégies :
1. Semantic hashing — remplace les patterns sémantiques répétés par des hashs
2. Byte-pair pruning — supprime les paires d'octets les plus fréquentes
3. JSON schema compression — compresse la structure des payloads JSON répétés
4. N-gram dedup — déduplication des n-grammes fréquents

Usage:
    python -m skills.token_compressor.cli compress < input.txt
    python -m skills.token_compressor.cli hash "repeating pattern here"
    python -m skills.token_compressor.cli learn < training_data.txt
"""
from __future__ import annotations

import json
import base64
import hashlib
import re
import sys
import zlib
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional
from skills.atomic_json import write_json


# ── N-gram frequency table ─────────────────────────────────────

NGRAM_STORE = Path.home() / ".botte" / "ngram-freq.json"


class NGramTable:
    """Frequency table for n-gram based compression."""

    def __init__(self, n: int = 3):
        self.n = n
        self.freq: dict[str, int] = {}
        self._load()

    def _load(self):
        if NGRAM_STORE.exists():
            try:
                data = json.loads(NGRAM_STORE.read_text(encoding="utf-8"))
                self.freq = data.get("freq", {})
                self.n = data.get("n", self.n)
            except (json.JSONDecodeError, TypeError):
                pass

    def _save(self):
        write_json(NGRAM_STORE, {
            "n": self.n,
            "freq": self.freq,
        })

    def learn(self, text: str):
        """Learn n-gram frequencies from text."""
        words = text.split()
        for i in range(len(words) - self.n + 1):
            ngram = " ".join(words[i:i + self.n])
            self.freq[ngram] = self.freq.get(ngram, 0) + 1
        self._save()

    def prune(self, min_freq: int = 2):
        """Remove rare n-grams."""
        self.freq = {k: v for k, v in self.freq.items() if v >= min_freq}
        self._save()


class TokenCompressor:
    """Multi-strategy token-level compressor."""

    def __init__(self):
        self.ngram_table = NGramTable(n=3)
        self.hash_map: dict[str, str] = {}  # hash → original

    def _semantic_hash(self, text: str, min_len: int = 20) -> str:
        """Replace repeated patterns with short hashes."""
        # Find repeated substrings of min_len+
        lines = text.split("\n")
        line_counts = Counter(lines)
        result = []

        for line in lines:
            if line_counts[line] >= 3 and len(line) >= min_len:
                # Replace with hash reference
                h = str(hash(line) % (10**8))
                self.hash_map[h] = line
                result.append(f"[H#{h}]")
            else:
                result.append(line)

        return "\n".join(result)

    def _byte_pair_prune(self, text: str) -> str:
        """Remove most common byte-pair patterns.

        Strips repeated whitespace, common filler words, and
        frequent punctuation patterns.
        """
        result = text

        # Collapse multiple spaces
        result = re.sub(r'  +', ' ', result)

        # Collapse multiple newlines
        result = re.sub(r'\n{3,}', '\n\n', result)

        # Remove common filler (only when repeated)
        result = re.sub(r'(\b(the|a|an|is|are|was|were|have|has|been|being)\s+){3,}',
                        lambda m: m.group(0).split(" ")[0] + " ... ", result)

        # Shorten hex/uuids (already done by cache aligner, but reinforce)
        result = re.sub(r'\b[0-9a-f]{8,}\b', lambda m: f"[h:{m.group(0)[:4]}]", result)

        return result

    def _json_schema_compress(self, text: str) -> str:
        """Compress JSON structures by collapsing repeated schemas."""
        def _compact_json(m):
            try:
                data = json.loads(m.group(0))
                if isinstance(data, dict):
                    if len(data) > 5:
                        keys = list(data.keys())
                        return f'{{{",".join(keys[:3])},...({len(keys)-3}more)}}'
                return m.group(0)
            except (json.JSONDecodeError, ValueError):
                return m.group(0)

        return re.sub(r'\{[^}]{50,}\}', _compact_json, text)

    def compress(self, text: str, level: str = "auto") -> str:
        """Return a self-contained, deterministic and reversible payload.

        The previous text transforms discarded whitespace, hexadecimal values,
        and JSON values.  A compressor must preserve its input, so all levels
        now use the same versioned stdlib codec; ``level`` remains accepted for
        CLI compatibility.
        """
        del level
        payload = zlib.compress(text.encode("utf-8"), level=9)
        return "TC1:" + base64.b85encode(payload).decode("ascii")

    def expand(self, text: str) -> str:
        """Restore a payload produced by :meth:`compress`."""
        if not text.startswith("TC1:"):
            raise ValueError("unsupported token-compressor payload")
        try:
            raw = base64.b85decode(text[4:].encode("ascii"))
            return zlib.decompress(raw).decode("utf-8")
        except (ValueError, zlib.error, UnicodeDecodeError) as exc:
            raise ValueError("invalid token-compressor payload") from exc


def main(argv=None) -> int:
    from skills.console_utf8 import force_utf8
    force_utf8()

    import argparse
    p = argparse.ArgumentParser(prog="token_compressor", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("compress", help="Compress token-level")
    s.add_argument("--input", help="Input file (stdin)")
    s.add_argument("--expand", action="store_true", help="Expand instead")
    s.add_argument("--level", choices=["auto", "hash", "pair", "json"],
                   default="auto")
    s.set_defaults(func=lambda a: _cmd_compress(a, TokenCompressor()))

    s2 = sub.add_parser("learn", help="Learn n-gram frequencies")
    s2.add_argument("--input", help="Training file (stdin)")
    s2.set_defaults(func=lambda a: _cmd_learn(a, NGramTable()))

    s3 = sub.add_parser("hash", help="Hash a string for the table")
    s3.add_argument("text", help="Text to hash")
    s3.set_defaults(func=lambda a: print(
        f"Hash: {hashlib.sha256(a.text.encode('utf-8')).hexdigest()[:16]}"))

    args = p.parse_args(argv)
    return args.func(args) or 0


def _cmd_compress(args, compressor: TokenCompressor):
    content = Path(args.input).read_text() if args.input else sys.stdin.read()

    if args.expand:
        result = compressor.expand(content)
    else:
        result = compressor.compress(content, args.level)

    print(f"# Original: {len(content)} chars")
    print(f"# Compressed: {len(result)} chars ({round(len(result)/max(len(content),1)*100)}%)")
    print(result)


def _cmd_learn(args, table: NGramTable):
    content = Path(args.input).read_text() if args.input else sys.stdin.read()
    table.learn(content)
    print(f"Learned {len(table.freq)} n-grams")


if __name__ == "__main__":
    main()

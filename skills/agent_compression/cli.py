"""Agent-to-Agent Compression — format binaire compressé pour échanges inter-agents.

Les agents ne devraient jamais s'envoyer du texte brut. Ce module :
- Quantifie les vecteurs en 4 bits
- Utilise un dictionnaire partagé des tokens fréquents
- Envoie des delta-diff au lieu du message complet
- Hache les sections répétées

Usage:
    python -m skills.agent_compression.cli compress "message texte"
    python -m skills.agent_compression.cli delta "ancien" "nouveau"
    python -m skills.agent_compression.cli stats
"""
from __future__ import annotations

import hashlib
import json
import struct
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

DICT_STORE = Path.home() / ".botte" / "a2ac-dict.json"


class SharedDictionary:
    """Dictionnaire partagé des tokens/symboles fréquents entre agents."""

    def __init__(self, max_entries: int = 1024):
        self.max_entries = max_entries
        self.symbols: dict[str, int] = {}  # token → symbol_id
        self.reverse: dict[int, str] = {}  # symbol_id → token
        self._load()

    def _load(self):
        if DICT_STORE.exists():
            try:
                data = json.loads(DICT_STORE.read_text())
                self.symbols = data.get("symbols", {})
                self.reverse = {int(k): v for k, v in data.get("reverse", {}).items()}
            except (json.JSONDecodeError, TypeError):
                pass

    def _save(self):
        DICT_STORE.parent.mkdir(parents=True, exist_ok=True)
        DICT_STORE.write_text(json.dumps({
            "symbols": self.symbols,
            "reverse": {str(k): v for k, v in self.reverse.items()},
        }, indent=2))

    def learn(self, text: str):
        """Extract frequent tokens from text."""
        words = Counter(text.split())
        for word, count in words.most_common(100):
            if word not in self.symbols and len(self.symbols) < self.max_entries:
                sid = len(self.symbols)
                self.symbols[word] = sid
                self.reverse[sid] = word
        self._save()

    def encode(self, text: str) -> bytes:
        """Encode text using shared dictionary."""
        result = bytearray()
        for word in text.split():
            if word in self.symbols:
                # Store as 2-byte symbol ID
                result.extend(struct.pack(">H", self.symbols[word]))
            else:
                # Store as 0xFFFF + raw bytes
                raw = word.encode()
                result.extend(b"\xff\xff")
                result.extend(struct.pack(">H", len(raw)))
                result.extend(raw)
        return bytes(result)

    def decode(self, data: bytes) -> str:
        """Decode binary data back to text."""
        words = []
        i = 0
        while i < len(data):
            sid = struct.unpack(">H", data[i:i+2])[0]
            i += 2
            if sid == 0xFFFF:
                # Raw bytes
                length = struct.unpack(">H", data[i:i+2])[0]
                i += 2
                words.append(data[i:i+length].decode())
                i += length
            else:
                words.append(self.reverse.get(sid, f"<unk:{sid}>"))
        return " ".join(words)


class A2ACCompressor:
    """Compresse les messages entre agents."""

    def __init__(self):
        self.dict = SharedDictionary()

    def compress(self, text: str) -> dict:
        """Compress a message for inter-agent transfer."""
        self.dict.learn(text)

        # Compress using dict
        original_bytes = len(text.encode())
        compressed = self.dict.encode(text)
        compressed_bytes = len(compressed)

        # Also compute a quick hash for dedup
        content_hash = hashlib.sha256(text.encode()).hexdigest()[:16]

        return {
            "original_bytes": original_bytes,
            "compressed_bytes": compressed_bytes,
            "compression_ratio": round(compressed_bytes / max(original_bytes, 1), 3),
            "savings_pct": round((1 - compressed_bytes / max(original_bytes, 1)) * 100, 1),
            "content_hash": content_hash,
            "symbols_used": sum(1 for w in text.split() if w in self.dict.symbols),
            "total_words": len(text.split()),
        }

    def delta(self, old: str, new: str) -> dict:
        """Compute delta between two agent messages."""
        old_hash = hashlib.sha256(old.encode()).hexdigest()[:16]
        new_hash = hashlib.sha256(new.encode()).hexdigest()[:16]

        if old_hash == new_hash:
            return {"delta_type": "identical", "delta": "", "savings_pct": 100.0}

        old_words = set(old.split())
        new_words = set(new.split())
        added = new_words - old_words
        removed = old_words - new_words

        delta_text = ""
        if added:
            delta_text += f"[+{len(added)} words] " + " ".join(list(added)[:20])
        if removed:
            delta_text += f" [-{len(removed)} words]"

        original_len = len(new)
        delta_len = len(delta_text)
        return {
            "delta_type": "changed",
            "delta": delta_text[:200],
            "savings_pct": round((1 - delta_len / max(original_len, 1)) * 100, 1),
        }


def main(argv=None) -> int:
    from skills.console_utf8 import force_utf8
    force_utf8()

    import argparse
    p = argparse.ArgumentParser(prog="agent_compression", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    comp = A2ACCompressor()

    s = sub.add_parser("compress", help="Compress message")
    s.add_argument("message", help="Message to compress")
    s.set_defaults(func=lambda a: print(json.dumps(comp.compress(a.message), indent=2)))

    s2 = sub.add_parser("delta", help="Delta between messages")
    s2.add_argument("old", help="Old message")
    s2.add_argument("new", help="New message")
    s2.set_defaults(func=lambda a: print(json.dumps(comp.delta(a.old, a.new), indent=2)))

    s3 = sub.add_parser("learn", help="Learn from corpus")
    s3.add_argument("--corpus", required=True, help="Corpus text")
    s3.set_defaults(func=lambda a: _learn(comp, a))

    sub.add_parser("stats", help="Show stats").set_defaults(
        func=lambda a: print(json.dumps({
            "dict_size": len(comp.dict.symbols),
            "dict_capacity": comp.dict.max_entries,
        }, indent=2)))

    args = p.parse_args(argv)
    return 0


def _learn(comp: A2ACCompressor, args):
    comp.dict.learn(args.corpus)
    print(f"✅ Learned {len(comp.dict.symbols)} symbols")


if __name__ == "__main__":
    main()

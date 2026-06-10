#!/usr/bin/env python3
"""Quick Actions matcher — exact alias + fuzzy + Qdrant fallback.

Usage:
  python3 vectorize_quick_actions.py --list
  python3 vectorize_quick_actions.py --index          # Push to Qdrant
  python3 vectorize_quick_actions.py --match "5 questions"
  python3 vectorize_quick_actions.py --resolve qa:clarify_5
"""
import json, argparse, sys
from pathlib import Path
from difflib import SequenceMatcher

MANIFEST = Path(__file__).resolve().parent.parent / "references" / "quick-actions.json"
COLLECTION = "quick_actions"


def load_manifest() -> list[dict]:
    with open(MANIFEST) as f:
        return json.load(f)["actions"]


def resolve(qa_id: str) -> dict | None:
    """Resolve a qa:xxx ID to the full action."""
    for a in load_manifest():
        if a["id"] == qa_id:
            return a
    return None


def match_exact(query: str) -> dict | None:
    """Exact match on alias or ID."""
    q = query.lower().strip()
    for a in load_manifest():
        if q == a["id"].lower():
            return a
        for alias in a["aliases"]:
            if q == alias.lower():
                return a
    return None


def match_fuzzy(query: str, threshold: float = 0.5) -> dict | None:
    """Fuzzy match on aliases + prompt."""
    q = query.lower().strip()
    best_score = 0
    best_action = None
    for a in load_manifest():
        # Check against all aliases
        for alias in a["aliases"]:
            score = SequenceMatcher(None, q, alias.lower()).ratio()
            if score > best_score:
                best_score = score
                best_action = a
        # Also check against prompt (for longer queries)
        score = SequenceMatcher(None, q, a["prompt"].lower()).ratio()
        if score > best_score:
            best_score = score
            best_action = a

    if best_score >= threshold:
        return best_action
    return None


def match_qdrant(query: str, qdrant_url: str) -> dict | None:
    """Qdrant semantic match (requires qdrant-client)."""
    try:
        from qdrant_client import QdrantClient
    except ImportError:
        return None

    # Simple hash-based vectorizer (64 dims)
    import hashlib
    h = hashlib.sha256(query.encode()).digest()
    vec = []
    for i in range(0, 32, 2):
        val = (h[i] << 8 | h[i + 1]) / 65535.0 * 2 - 1
        vec.append(val)
    while len(vec) < 64:
        vec.append(0.0)

    client = QdrantClient(url=qdrant_url)
    try:
        results = client.search(collection_name=COLLECTION, query_vector=vec[:64], limit=1)
        # Use lower threshold for hash-based vectors
        if results and results[0].score > 0.85:
            return results[0].payload
    except Exception:
        pass
    return None


def smart_match(query: str, qdrant_url: str = "http://192.168.1.47:6333") -> dict | None:
    """Three-tier matching: exact → fuzzy → Qdrant."""
    # Tier 1: exact
    result = match_exact(query)
    if result:
        return result

    # Tier 2: fuzzy
    result = match_fuzzy(query)
    if result:
        return result

    # Tier 3: Qdrant
    return match_qdrant(query, qdrant_url)


def index_qdrant(qdrant_url: str):
    """Push quick actions to Qdrant."""
    import hashlib
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams, PointStruct
    except ImportError:
        print("qdrant-client not installed. Run: pip install qdrant-client")
        return

    actions = load_manifest()
    client = QdrantClient(url=qdrant_url)

    # Check if collection exists, create if not
    try:
        client.get_collection(COLLECTION)
        client.delete_collection(COLLECTION)
    except Exception:
        pass

    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=64, distance=Distance.COSINE),
    )

    points = []
    for i, action in enumerate(actions):
        text = " ".join(action["aliases"] + [action["prompt"]])
        h = hashlib.sha256(text.encode()).digest()
        vec = []
        for j in range(0, 32, 2):
            val = (h[j] << 8 | h[j + 1]) / 65535.0 * 2 - 1
            vec.append(val)
        while len(vec) < 64:
            vec.append(0.0)

        points.append(PointStruct(
            id=i,
            vector=vec[:64],
            payload={
                "qa_id": action["id"],
                "prompt": action["prompt"],
                "aliases": action["aliases"],
                "icon": action["icon"],
                "category": action["category"],
                "tokens_saved": action["tokens_saved"],
            },
        ))

    client.upsert(collection_name=COLLECTION, points=points)
    print(f"Indexed {len(points)} quick actions in Qdrant '{COLLECTION}'")


def show_manifest():
    actions = load_manifest()
    for a in actions:
        print(f"{a['icon']}  {a['id']:20s} → {a['prompt'][:60]}...")
    tokens = sum(a["tokens_saved"] for a in actions)
    print(f"\n{len(actions)} actions, avg {tokens/len(actions):.0f} tokens saved/action")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Quick Actions matcher")
    parser.add_argument("--qdrant", default="http://192.168.1.47:6333")
    parser.add_argument("--index", action="store_true")
    parser.add_argument("--match", type=str)
    parser.add_argument("--resolve", type=str)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    if args.list:
        show_manifest()
    elif args.index:
        index_qdrant(args.qdrant)
    elif args.resolve:
        action = resolve(args.resolve)
        if action:
            print(action["prompt"])
        else:
            print(f"Unknown: {args.resolve}", file=sys.stderr)
            sys.exit(1)
    elif args.match:
        result = smart_match(args.match, args.qdrant)
        if result:
            print(f"{result['icon']} {result['id']}: {result['prompt']}")
        else:
            print("No match")
    else:
        parser.print_help()

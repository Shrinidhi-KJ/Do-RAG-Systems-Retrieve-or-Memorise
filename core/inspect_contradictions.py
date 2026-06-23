"""
inspect_contradictions.py
-------------------------
Compact dump of the contradiction cache so we can see exactly what the
provenance judge saw: the claim vs the retrieved oracle chunk, per item.

    python inspect_contradictions.py
"""

import json
from pathlib import Path

# Repo root = parent of core/. Anchors data paths so this works from any CWD.
ROOT = Path(__file__).resolve().parent.parent
with open(ROOT / "contradictions_cache.json", encoding="utf-8") as f:
    cache = json.load(f)

for k, v in cache.items():
    print("=" * 72)
    print(f"idx {k}  |  source={v['source']}  |  provenance_supported={v.get('provenance_supported')}  |  verified={v['verified']}")
    print("-" * 72)
    print("CLAIM:    ", v["claim_text"][:240])
    print()
    print("RETRIEVED CHUNKS (what the provenance judge actually read):")
    for i, prev in enumerate(v.get("oracle_preview", []) or ["<none retrieved>"]):
        print(f"   [{i + 1}] {prev}")
    print()

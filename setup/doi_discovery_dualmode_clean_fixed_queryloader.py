#!/usr/bin/env python3
"""
Dual-mode DOI discovery script: OpenAlex hybrid + Scopus/WOS full Boolean queries.

What it does:
1. OpenAlex uses descriptor_keywords.txt; Scopus/WOS use OWF_ScopusQueries.txt full Boolean queries.
2. Parses each TS block into AND groups.
3. Generates a limited, hybrid set of OpenAlex seed queries instead of expanding every Cartesian product.
4. Searches OpenAlex, Scopus, and/or Web of Science.
5. Keeps records only if they match at least one term from every AND group locally.
6. Writes newly discovered DOI + source immediately to doi_sources_live.txt.
7. Writes final sorted outputs at the end.

Example:
    python doi_discovery_hybrid_multisource_clean.py \
      --descriptor_file descriptor_keywords.txt --sources openalex scopus wos \
      --max_queries_per_block 250 \
      --max_total_queries 2000
"""

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path
from random import uniform
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import unquote

import requests

# Repo root = parent of setup/. Anchors data paths so this works from any CWD.
ROOT = Path(__file__).resolve().parent.parent

BAD_SUFFIX_RE = re.compile(
    r"/v\d+/(review\d*|decision\d*|response\d*|author[-_]?reply\d*)$",
    re.IGNORECASE,
)

DEFAULT_ALLOWED_TYPES = {"article", "journal-article", "posted-content", "review", "report"}


# -----------------------------
# Generic helpers
# -----------------------------

def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").lower()
    text = text.replace("“", '"').replace("”", '"').replace("„", '"').replace("‟", '"')
    text = text.replace("’", "'").replace("‘", "'").replace("–", "-").replace("—", "-")
    text = re.sub(r"[^a-z0-9\s\-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def canonicalize_doi(doi: str) -> str:
    d = unquote((doi or "").strip())
    d = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", d, flags=re.IGNORECASE)
    d = BAD_SUFFIX_RE.sub("", d)
    d = re.sub(r"/v\d+$", "", d, flags=re.IGNORECASE)
    d = d.strip().rstrip(".,;)")
    return d


def write_lines(path: str, lines: Iterable[str]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(str(line) + "\n")


def append_live_source(doi: str, source: str, live_sources_file: str, seen_live: Set[str]) -> None:
    key = doi.lower().strip()
    if not key or key in seen_live:
        return

    seen_live.add(key)
    with open(live_sources_file, "a", encoding="utf-8") as f:
        f.write(f"{key}\t{source}\n")
        f.flush()

    print(f"✅ NEW DOI [{source}]: {key}", flush=True)


def add_debug_row(rows: List[str], source: str, query: str, doi: str, reason: str, detail: str = "") -> None:
    safe = lambda x: str(x).replace("\t", " ").replace("\n", " ").strip()
    rows.append("\t".join([safe(source), safe(query), safe(doi or "-"), safe(reason), safe(detail)]))


# -----------------------------
# Descriptor parsing
# -----------------------------

def read_and_normalize_descriptor(path: str) -> str:
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    text = (
        text.replace("“", '"')
            .replace("”", '"')
            .replace("„", '"')
            .replace("‟", '"')
            .replace("’", "'")
            .replace("‘", "'")
            .replace("–", "-")
            .replace("—", "-")
    )
    # Fix PDF line-broken hyphenation: "Long-\nfinned" -> "Long-finned"
    text = re.sub(r"-\s*\n\s*", "-", text)
    # Collapse remaining whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def strip_outer_parens(s: str) -> str:
    s = s.strip()
    changed = True
    while changed and s.startswith("(") and s.endswith(")"):
        changed = False
        depth = 0
        in_quote = False
        ok = True
        for i, ch in enumerate(s):
            if ch == '"':
                in_quote = not in_quote
            elif not in_quote:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0 and i != len(s) - 1:
                        ok = False
                        break
        if ok:
            s = s[1:-1].strip()
            changed = True
    return s


def clean_term(term: str) -> str:
    t = term.strip()
    t = strip_outer_parens(t)
    t = t.strip().strip('"').strip("'").strip()
    t = re.sub(r"^TS\s*=\s*", "", t, flags=re.IGNORECASE).strip()
    t = re.sub(r"\s+", " ", t).strip()
    t = t.strip("() ")
    return t


def split_ts_blocks(text: str) -> List[str]:
    parts = re.split(r"\bTS\s*=\s*", text, flags=re.IGNORECASE)
    blocks: List[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        part = re.sub(r"^\s*TS\s*=\s*", "", part, flags=re.IGNORECASE).strip()
        blocks.append(part)
    return blocks


def split_top_level_operator(s: str, operator: str, max_depth: int = 0) -> List[str]:
    """
    Split a string on operator (AND/OR) outside quotes and at allowed parenthesis depth.

    max_depth=0 means split only at true top level.
    max_depth=1 is useful for strings with one extra wrapping parenthesis level.
    """
    s = strip_outer_parens(s)
    out: List[str] = []
    start = 0
    depth = 0
    in_quote = False
    pattern = re.compile(rf"\s+{re.escape(operator)}\s+", flags=re.IGNORECASE)

    i = 0
    while i < len(s):
        ch = s[i]
        if ch == '"':
            in_quote = not in_quote
            i += 1
            continue

        if not in_quote:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1

            if depth <= max_depth:
                m = pattern.match(s, i)
                if m:
                    out.append(s[start:i].strip())
                    i = m.end()
                    start = i
                    continue
        i += 1

    out.append(s[start:].strip())
    return [strip_outer_parens(x) for x in out if x.strip()]


def expand_wos_wildcard(term: str) -> List[str]:
    """
    Convert Web of Science suffix $ into conservative variants.
    bat$ -> bat, bats
    mammal$ -> mammal, mammals
    sediment* -> sediment, sediments
    """
    term = clean_term(term)
    if not term:
        return []

    if "$" not in term and "*" not in term:
        return [term]

    base = term.replace("$", "").replace("*", "").strip()
    if not base:
        return []

    variants = [base]
    lower = base.lower()

    # Conservative pluralization.
    if lower.endswith("y") and len(lower) > 1 and lower[-2] not in "aeiou":
        variants.append(base[:-1] + "ies")
    elif lower.endswith(("s", "x", "ch", "sh")):
        variants.append(base + "es")
    else:
        variants.append(base + "s")

    return variants


def split_or_terms(group: str) -> List[str]:
    """
    Split one AND group into OR terms.

    Handles malformed quoted groups such as:
        ("wind farm$ OR windfarm$ OR "wind energy" OR ...)
    by removing quotes if quoting is clearly unbalanced/broken.
    """
    group = strip_outer_parens(group.strip())

    # If quotes are malformed, remove quotes and rely on OR separators.
    if group.count('"') % 2 != 0 or re.search(r'^"\s*[^"]+\s+OR\s+', group, flags=re.IGNORECASE):
        group = group.replace('"', "")

    raw_terms = split_top_level_operator(group, "OR", max_depth=0)

    terms: List[str] = []
    seen: Set[str] = set()

    for raw in raw_terms:
        raw = clean_term(raw)
        if not raw:
            continue

        # Keep NEAR expressions as-is as a local matching phrase fallback,
        # but clean obvious syntax-only terms.
        if re.fullmatch(r"(?i)(AND|OR|TS|NEAR)", raw):
            continue
        if raw in {'"', "'", "(", ")"}:
            continue
        if re.search(r"\bAND\b", raw, flags=re.IGNORECASE) and not re.search(r"NEAR/\d+", raw, flags=re.IGNORECASE):
            # This usually means the AND splitting failed or quote extraction is broken.
            continue

        for variant in expand_wos_wildcard(raw):
            variant = clean_term(variant)
            if not variant:
                continue
            key = variant.casefold()
            if key not in seen:
                terms.append(variant)
                seen.add(key)

    return terms


def parse_descriptor_blocks(descriptor_file: str) -> List[Dict[str, Any]]:
    text = read_and_normalize_descriptor(descriptor_file)
    raw_blocks = split_ts_blocks(text)

    parsed: List[Dict[str, Any]] = []

    for block_id, block in enumerate(raw_blocks, start=1):
        groups_raw = split_top_level_operator(block, "AND", max_depth=1)
        groups = [split_or_terms(g) for g in groups_raw]
        groups = [g for g in groups if g]

        if len(groups) < 2:
            continue

        parsed.append({
            "block_id": block_id,
            "group_count": len(groups),
            "groups": groups,
        })

    return parsed


# -----------------------------
# Hybrid query generation
# -----------------------------

def generate_hybrid_queries_for_block(
    groups: List[List[str]],
    max_queries: int,
    max_terms_per_group_in_query: int = 1,
) -> List[str]:
    """
    Generate deterministic hybrid queries from AND groups.

    Instead of fully expanding species x wind x region x ...,
    this cycles through terms but guarantees early coverage of the first
    wind/region combinations for each species term.

    For three groups [species, wind, region], the first queries are:
        species[0] wind[0] region[0]
        species[1] wind[0] region[0]
        species[2] wind[0] region[0]
        ...
        species[0] wind[1] region[0]
        ...
    """
    if not groups:
        return []

    # Keep groups as lists of clean terms.
    clean_groups = []
    for group in groups:
        cleaned = []
        seen = set()
        for t in group:
            t = clean_term(t)
            if not t:
                continue
            key = t.casefold()
            if key not in seen:
                cleaned.append(t)
                seen.add(key)
        if cleaned:
            clean_groups.append(cleaned)

    if not clean_groups:
        return []

    queries: List[str] = []
    seen_q: Set[str] = set()

    # Put the longest group first for coverage; preserve original groups afterward.
    # Usually this gives species terms first.
    primary_index = max(range(len(clean_groups)), key=lambda i: len(clean_groups[i]))
    primary = clean_groups[primary_index]
    other_groups = [g for i, g in enumerate(clean_groups) if i != primary_index]

    # Deterministic nested coverage:
    # for each combination of one term from other groups, run across all primary terms.
    other_positions = [0] * len(other_groups)

    def current_other_terms() -> List[str]:
        return [other_groups[i][other_positions[i]] for i in range(len(other_groups))]

    def advance_other_positions() -> bool:
        if not other_groups:
            return False
        for i in range(len(other_positions)):
            other_positions[i] += 1
            if other_positions[i] < len(other_groups[i]):
                return True
            other_positions[i] = 0
        return False

    keep_going = True
    while keep_going and len(queries) < max_queries:
        fixed_terms = current_other_terms()
        for p in primary:
            parts = [p] + fixed_terms
            q = " ".join(parts)
            key = normalize_text(q)
            if key not in seen_q:
                queries.append(q)
                seen_q.add(key)
                if len(queries) >= max_queries:
                    break
        keep_going = advance_other_positions()

    return queries


def generate_all_hybrid_queries(
    parsed_blocks: List[Dict[str, Any]],
    max_queries_per_block: int,
    max_total_queries: int,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen_global: Set[str] = set()

    for block in parsed_blocks:
        block_id = block["block_id"]
        groups = block["groups"]
        queries = generate_hybrid_queries_for_block(groups, max_queries=max_queries_per_block)

        for q in queries:
            key = normalize_text(q)
            if key in seen_global:
                continue
            rows.append({
                "block_id": block_id,
                "query": q,
                "groups": groups,
            })
            seen_global.add(key)
            if len(rows) >= max_total_queries:
                return rows

    return rows


# -----------------------------
# Matching and OpenAlex helpers
# -----------------------------

def term_to_regex(term: str) -> Optional[re.Pattern]:
    t = clean_term(term)
    if not t:
        return None

    # For NEAR/n style terms, fall back to matching the meaningful words in order loosely.
    # Example: species NEAR/15 non-indigenous -> species.*non indigenous
    t = re.sub(r"\bNEAR/\d+\b", " ", t, flags=re.IGNORECASE)
    t_norm = normalize_text(t)
    if not t_norm:
        return None

    words = [re.escape(w) for w in t_norm.split() if w]
    if not words:
        return None

    pattern = r"\b" + r"[\s\-]+".join(words) + r"\b"
    return re.compile(pattern, flags=re.IGNORECASE)


def term_matches_text(term: str, normalized_text: str) -> bool:
    rx = term_to_regex(term)
    if rx is None:
        return False
    return rx.search(normalized_text) is not None


def group_matches_text(group: Sequence[str], text: str) -> bool:
    ntext = normalize_text(text)
    return any(term_matches_text(t, ntext) for t in group)


def passes_all_groups(groups: Sequence[Sequence[str]], text: str) -> Tuple[bool, int]:
    hit_count = 0
    for group in groups:
        if group_matches_text(group, text):
            hit_count += 1
        else:
            return False, hit_count
    return True, hit_count


def openalex_abstract_to_text(inv_idx: Any) -> str:
    if not isinstance(inv_idx, dict):
        return ""

    max_pos = -1
    for positions in inv_idx.values():
        if isinstance(positions, list) and positions:
            max_pos = max(max_pos, max(positions))

    if max_pos < 0:
        return ""

    words = [""] * (max_pos + 1)
    for token, positions in inv_idx.items():
        if isinstance(positions, list):
            for p in positions:
                if isinstance(p, int) and 0 <= p <= max_pos:
                    words[p] = token

    return " ".join(w for w in words if w)


def build_openalex_text(work: Dict[str, Any]) -> str:
    title = str(work.get("display_name", "") or "")
    abstract = openalex_abstract_to_text(work.get("abstract_inverted_index"))

    primary_location = work.get("primary_location") or {}
    source = primary_location.get("source") or {}
    venue = source.get("display_name", "") if isinstance(source, dict) else ""

    concepts = " ".join(
        str(c.get("display_name", ""))
        for c in (work.get("concepts") or [])
        if isinstance(c, dict)
    )

    keywords = " ".join(
        str(k.get("display_name", ""))
        for k in (work.get("keywords") or [])
        if isinstance(k, dict)
    )

    return f"{title} {abstract} {venue} {concepts} {keywords}".strip()


def safe_get_json(url: str, params: Dict[str, Any], timeout: int = 30) -> Optional[Dict[str, Any]]:
    try:
        r = requests.get(url, params=params, timeout=timeout)
        if r.status_code == 200:
            return r.json()

        body = (r.text or "").strip().replace("\n", " ")
        if len(body) > 500:
            body = body[:500] + "..."

        print(f"⚠️ OpenAlex call failed: HTTP {r.status_code} | params={params} | body={body}", flush=True)

        if r.status_code == 429:
            print("⚠️ Rate limited by OpenAlex. Increase delays or reduce max queries.", flush=True)

        return None

    except requests.RequestException as e:
        print(f"⚠️ OpenAlex request error: {e}", flush=True)
        return None


def get_openalex_work_by_doi(doi: str) -> Optional[Dict[str, Any]]:
    url = "https://api.openalex.org/works"
    params = {"filter": f"doi:https://doi.org/{doi}", "per-page": 1}
    data = safe_get_json(url, params=params, timeout=20)
    if not data:
        return None
    results = data.get("results", [])
    return results[0] if results else None





# -----------------------------
# Scopus/WOS full Boolean query-file mode
# -----------------------------

def clean_query_text(q: str) -> str:
    q = q.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    q = re.sub(r"\s+", " ", q).strip()
    # Scopus API is safer with LANGUAGE(english), no space.
    q = re.sub(r"\bLANGUAGE\s+\(", "LANGUAGE(", q, flags=re.IGNORECASE)
    return q


def load_scopus_queries_file(path: str) -> List[Dict[str, str]]:
    """
    Extract labelled full Scopus queries from OWF_ScopusQueries.txt.

    Important:
    A single query can contain several TITLE-ABS-KEY(...) blocks joined by AND.
    Therefore we split ONLY at descriptor labels such as D1_mammals, D8_Contaminants,
    not at every TITLE-ABS-KEY occurrence.
    """
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    rows: List[Dict[str, str]] = []
    current_label: Optional[str] = None
    current_lines: List[str] = []

    label_re = re.compile(r"^D\d+(?:[_\s].*)?$", flags=re.IGNORECASE)

    def flush() -> None:
        nonlocal current_lines, current_label
        if not current_lines:
            return

        q = clean_query_text(" ".join(current_lines))
        current_lines = []

        if "TITLE-ABS-KEY" not in q.upper():
            return

        # Avoid incomplete accidental fragments.
        q = re.sub(r"\s+AND\s*$", "", q, flags=re.IGNORECASE).strip()
        if not q:
            return

        rows.append({
            "label": current_label or f"query_{len(rows) + 1}",
            "scopus_query": q,
        })

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        # Skip purely descriptive header line if present.
        if line.upper() == "D1_ALL":
            continue

        if label_re.match(line) and "TITLE-ABS-KEY" not in line.upper():
            flush()
            current_label = line
            continue

        # Otherwise it is part of the current query.
        if "TITLE-ABS-KEY" in line.upper() or current_lines:
            current_lines.append(line)

    flush()

    # Deduplicate exact queries while preserving order.
    deduped: List[Dict[str, str]] = []
    seen: Set[str] = set()
    for row in rows:
        key = row["scopus_query"].casefold()
        if key not in seen:
            deduped.append(row)
            seen.add(key)

    return deduped


def scopus_query_to_wos_query(scopus_query: str) -> str:
    """
    Convert Scopus full Boolean syntax to WOS Topic syntax.

    - TITLE-ABS-KEY(...) -> TS=(...)
    - LANGUAGE(english) is removed because WOS language syntax differs by API/tier.
    - PUBYEAR > 2007 AND PUBYEAR < 2026 becomes PY=(2008-2025).
    """
    q = clean_query_text(scopus_query)

    # Convert Scopus field tag to WOS Topic.
    q = re.sub(r"TITLE-ABS-KEY\s*\(", "TS=(", q, flags=re.IGNORECASE)

    # Convert PUBYEAR range to WOS PY range where possible.
    m = re.search(r"PUBYEAR\s*>\s*(\d{4})\s+AND\s+PUBYEAR\s*<\s*(\d{4})", q, flags=re.IGNORECASE)
    if m:
        start = int(m.group(1)) + 1
        end = int(m.group(2)) - 1
        q = re.sub(
            r"\s+AND\s+PUBYEAR\s*>\s*\d{4}\s+AND\s+PUBYEAR\s*<\s*\d{4}",
            f" AND PY=({start}-{end})",
            q,
            flags=re.IGNORECASE,
        )
    else:
        q = re.sub(r"\s+AND\s+PUBYEAR\s*[<>]=?\s*\d{4}", "", q, flags=re.IGNORECASE)

    # Remove Scopus language filter for WOS portability.
    q = re.sub(r"\s+AND\s+LANGUAGE\s*\(\s*english\s*\)", "", q, flags=re.IGNORECASE)
    q = re.sub(r"\s+AND\s*$", "", q, flags=re.IGNORECASE).strip()
    return clean_query_text(q)


def build_full_boolean_query_rows(path: str) -> List[Dict[str, Any]]:
    rows = []
    for row in load_scopus_queries_file(path):
        rows.append({
            "label": row["label"],
            "query": row["scopus_query"],
            "scopus_query": row["scopus_query"],
            "wos_query": scopus_query_to_wos_query(row["scopus_query"]),
            "groups": [],
            "is_full_boolean": True,
        })
    return rows


# -----------------------------
# Scopus / WOS query builders
# -----------------------------

def quote_database_term(term: str) -> str:
    """
    Quote multi-word terms for Scopus/WOS query syntax.
    Single-word terms are left unquoted.
    """
    term = clean_term(str(term).replace('"', " "))
    term = re.sub(r"\s+", " ", term).strip()
    if not term:
        return ""
    if " " in term or "-" in term:
        return f'"{term}"'
    return term


def build_boolean_terms_from_query(query: str) -> str:
    """
    Convert a hybrid plain-text seed query into database Boolean syntax.

    Example:
        bat wind farm baltic sea
    becomes:
        bat AND "wind farm" AND "baltic sea"

    This is used inside:
        Scopus: TITLE-ABS-KEY(...)
        WOSCC:  TS=(...)
    """
    q = str(query).replace('"', " ")
    q = re.sub(r"\s+", " ", q).strip()

    known_phrases = [
        "wind power station",
        "wind power plant",
        "wind turbine",
        "wind energy",
        "wind park",
        "wind farm",
        "offshore wind",
        "english channel",
        "bay of biscay",
        "iberian coast",
        "mediterranean sea",
        "baltic sea",
        "north sea",
        "celtic sea",
        "ionian sea",
        "tyrrhenian sea",
        "adriatic sea",
        "aegean sea",
        "levantine sea",
        "ligurian sea",
        "black sea",
        "kattegat",
        "skagerrak",
        "skagerak",
        "macaronesia",
    ]

    remaining = q.lower()
    found: List[str] = []

    for phrase in sorted(known_phrases, key=len, reverse=True):
        pattern = re.compile(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", flags=re.IGNORECASE)
        if pattern.search(remaining):
            found.append(quote_database_term(phrase))
            remaining = pattern.sub(" ", remaining)

    for word in remaining.split():
        word = word.strip()
        if word:
            found.append(quote_database_term(word))

    final: List[str] = []
    seen: Set[str] = set()
    for term in found:
        if not term:
            continue
        key = normalize_text(term)
        if key not in seen:
            final.append(term)
            seen.add(key)

    return " AND ".join(final)


def build_scopus_query(query: str) -> str:
    """
    Scopus search in title, abstract, and keywords.
    """
    boolean_query = build_boolean_terms_from_query(query)
    return f"TITLE-ABS-KEY({boolean_query})"


def build_wos_query(query: str) -> str:
    """
    Web of Science Core Collection Topic search.
    """
    boolean_query = build_boolean_terms_from_query(query)
    return f"TS=({boolean_query})"


def discover_from_scopus(
    query_rows: List[Dict[str, Any]],
    api_key: str,
    per_page: int,
    count_cap: int,
    max_pages_per_query: int,
    delay_min: float,
    delay_max: float,
    live_sources_file: str,
    seen_live_dois: Set[str],
    debug_rows: List[str],
) -> Dict[str, Set[str]]:
    if not api_key:
        print("⚠️ Scopus API key missing; skipping Scopus.", flush=True)
        return {}

    url = "https://api.elsevier.com/content/search/scopus"
    headers = {"X-ELS-APIKey": api_key, "Accept": "application/json"}
    discovered: Dict[str, Set[str]] = {}
    effective_count = max(1, min(per_page, count_cap))

    for i, row in enumerate(query_rows, start=1):
        query = row["query"]
        groups = row["groups"]
        scopus_query = row.get("scopus_query", query if row.get("is_full_boolean") else build_scopus_query(query))

        print(f"[INFO] Scopus query {i}/{len(query_rows)}: {scopus_query}", flush=True)

        for page in range(max_pages_per_query):
            params = {
                "query": scopus_query,
                "count": effective_count,
                "start": page * effective_count,
            }

            try:
                r = requests.get(url, headers=headers, params=params, timeout=30)
                if r.status_code != 200:
                    body = (r.text or "").strip().replace("\n", " ")
                    if len(body) > 500:
                        body = body[:500] + "..."
                    print(f"⚠️ Scopus call failed: HTTP {r.status_code} | params={params} | body={body}", flush=True)
                    break
                data = r.json()
            except requests.RequestException as e:
                print(f"⚠️ Scopus request error: {e}", flush=True)
                break

            entries = data.get("search-results", {}).get("entry", [])
            if not entries:
                break

            for e in entries:
                raw_doi = e.get("prism:doi") or e.get("doi")
                if not raw_doi:
                    add_debug_row(debug_rows, "scopus", query, "-", "no_doi", e.get("dc:title", ""))
                    continue

                raw_doi = str(raw_doi)
                if BAD_SUFFIX_RE.search(raw_doi):
                    add_debug_row(debug_rows, "scopus", query, raw_doi, "bad_doi_suffix")
                    continue

                doi = canonicalize_doi(raw_doi)
                if not doi:
                    add_debug_row(debug_rows, "scopus", query, raw_doi, "invalid_doi")
                    continue

                if row.get("is_full_boolean"):
                    passed, hit_count = True, len(groups)
                else:
                    text = f"{e.get('dc:title', '')} {e.get('dc:description', '')} {e.get('prism:publicationName', '')}"
                    passed, hit_count = passes_all_groups(groups, text)

                if passed:
                    doi_key = doi.lower()
                    first_seen = doi_key not in discovered
                    discovered.setdefault(doi_key, set()).add("scopus")
                    if first_seen:
                        append_live_source(doi_key, "scopus", live_sources_file, seen_live_dois)
                else:
                    add_debug_row(
                        debug_rows,
                        "scopus",
                        query,
                        doi,
                        "group_filter_fail",
                        f"group_matches={hit_count}/{len(groups)}",
                    )

            time.sleep(uniform(delay_min, delay_max))

    return discovered


def discover_from_wos(
    query_rows: List[Dict[str, Any]],
    api_key: str,
    mode: str,
    per_page: int,
    max_pages_per_query: int,
    delay_min: float,
    delay_max: float,
    live_sources_file: str,
    seen_live_dois: Set[str],
    debug_rows: List[str],
) -> Dict[str, Set[str]]:
    if not api_key:
        print("⚠️ WOS API key missing; skipping Web of Science.", flush=True)
        return {}

    discovered: Dict[str, Set[str]] = {}

    if mode == "starter":
        url = "https://api.clarivate.com/apis/wos-starter/v1/documents"
        headers = {"X-ApiKey": api_key}

        for i, row in enumerate(query_rows, start=1):
            query = row["query"]
            groups = row["groups"]
            wos_query = row.get("wos_query", query if row.get("is_full_boolean") else build_wos_query(query))
            print(f"[INFO] WOS starter query {i}/{len(query_rows)}: {wos_query}", flush=True)

            for page in range(1, max_pages_per_query + 1):
                params = {"q": wos_query, "limit": per_page, "page": page}

                try:
                    r = requests.get(url, headers=headers, params=params, timeout=30)
                    if r.status_code != 200:
                        body = (r.text or "").strip().replace("\n", " ")
                        if len(body) > 500:
                            body = body[:500] + "..."
                        print(f"⚠️ WOS starter call failed: HTTP {r.status_code} | params={params} | body={body}", flush=True)
                        break
                    data = r.json()
                except requests.RequestException as e:
                    print(f"⚠️ WOS starter request error: {e}", flush=True)
                    break

                hits = data.get("hits", [])
                if not hits:
                    break

                for h in hits:
                    identifiers = h.get("identifiers", {}) if isinstance(h.get("identifiers"), dict) else {}
                    raw_doi = identifiers.get("doi")
                    if not raw_doi:
                        add_debug_row(debug_rows, "wos", query, "-", "no_doi", h.get("uid", ""))
                        continue

                    raw_doi = str(raw_doi)
                    if BAD_SUFFIX_RE.search(raw_doi):
                        add_debug_row(debug_rows, "wos", query, raw_doi, "bad_doi_suffix")
                        continue

                    doi = canonicalize_doi(raw_doi)
                    if not doi:
                        add_debug_row(debug_rows, "wos", query, raw_doi, "invalid_doi")
                        continue

                    if row.get("is_full_boolean"):
                        passed, hit_count = True, len(groups)
                    else:
                        source = h.get("source", {}) if isinstance(h.get("source"), dict) else {}
                        text = f"{h.get('title', '')} {source.get('sourceTitle', '')}"
                        passed, hit_count = passes_all_groups(groups, text)

                    if passed:
                        doi_key = doi.lower()
                        first_seen = doi_key not in discovered
                        discovered.setdefault(doi_key, set()).add("wos")
                        if first_seen:
                            append_live_source(doi_key, "wos", live_sources_file, seen_live_dois)
                    else:
                        add_debug_row(
                            debug_rows,
                            "wos",
                            query,
                            doi,
                            "group_filter_fail",
                            f"group_matches={hit_count}/{len(groups)}",
                        )

                time.sleep(uniform(delay_min, delay_max))

    else:
        url = "https://api.clarivate.com/api/wos"
        headers = {"X-ApiKey": api_key}

        for i, row in enumerate(query_rows, start=1):
            query = row["query"]
            groups = row["groups"]
            wos_query = row.get("wos_query", query if row.get("is_full_boolean") else build_wos_query(query))
            print(f"[INFO] WOS expanded query {i}/{len(query_rows)}: {wos_query}", flush=True)

            for page in range(max_pages_per_query):
                first_record = page * per_page + 1
                params = {
                    "databaseId": "WOS",
                    "usrQuery": wos_query,
                    "count": per_page,
                    "firstRecord": first_record,
                }

                try:
                    r = requests.get(url, headers=headers, params=params, timeout=30)
                    if r.status_code != 200:
                        body = (r.text or "").strip().replace("\n", " ")
                        if len(body) > 500:
                            body = body[:500] + "..."
                        print(f"⚠️ WOS expanded call failed: HTTP {r.status_code} | params={params} | body={body}", flush=True)
                        break
                    data = r.json()
                except requests.RequestException as e:
                    print(f"⚠️ WOS expanded request error: {e}", flush=True)
                    break

                recs = data.get("Data", {}).get("Records", {}).get("records", {}).get("REC", [])
                if not recs:
                    break

                for rec in recs:
                    rec_text = str(rec)
                    m = re.search(r'10\.\d{4,9}/[^"\s<>]+', rec_text)
                    if not m:
                        add_debug_row(debug_rows, "wos", query, "-", "no_doi")
                        continue

                    raw_doi = m.group(0)
                    if BAD_SUFFIX_RE.search(raw_doi):
                        add_debug_row(debug_rows, "wos", query, raw_doi, "bad_doi_suffix")
                        continue

                    doi = canonicalize_doi(raw_doi)
                    if not doi:
                        add_debug_row(debug_rows, "wos", query, raw_doi, "invalid_doi")
                        continue

                    if row.get("is_full_boolean"):
                        passed, hit_count = True, len(groups)
                    else:
                        passed, hit_count = passes_all_groups(groups, rec_text)

                    if passed:
                        doi_key = doi.lower()
                        first_seen = doi_key not in discovered
                        discovered.setdefault(doi_key, set()).add("wos")
                        if first_seen:
                            append_live_source(doi_key, "wos", live_sources_file, seen_live_dois)
                    else:
                        add_debug_row(
                            debug_rows,
                            "wos",
                            query,
                            doi,
                            "group_filter_fail",
                            f"group_matches={hit_count}/{len(groups)}",
                        )

                time.sleep(uniform(delay_min, delay_max))

    return discovered


def merge_discovery_maps(*maps: Dict[str, Set[str]]) -> Dict[str, Set[str]]:
    merged: Dict[str, Set[str]] = {}
    for m in maps:
        for doi, sources in m.items():
            merged.setdefault(doi, set()).update(sources)
    return merged


# -----------------------------
# Discovery
# -----------------------------

def discover_from_openalex(
    query_rows: List[Dict[str, Any]],
    per_page: int,
    max_pages_per_query: int,
    delay_min: float,
    delay_max: float,
    allowed_types: Set[str],
    live_sources_file: str,
    seen_live_dois: Set[str],
    debug_rows: List[str],
) -> Dict[str, Set[str]]:
    url = "https://api.openalex.org/works"
    discovered: Dict[str, Set[str]] = {}

    for i, row in enumerate(query_rows, start=1):
        query = row["query"]
        groups = row["groups"]

        print(f"[INFO] OpenAlex query {i}/{len(query_rows)}: {query}", flush=True)

        for page in range(1, max_pages_per_query + 1):
            params = {
                "search": query,
                "filter": "has_doi:true",
                "per-page": per_page,
                "page": page,
            }

            data = safe_get_json(url, params=params)
            if not data:
                break

            results = data.get("results", [])
            if not results:
                break

            for work in results:
                wtype = normalize_text(str(work.get("type", "") or ""))
                if allowed_types and wtype and wtype not in allowed_types:
                    add_debug_row(debug_rows, "openalex", query, "-", "disallowed_type", wtype)
                    continue

                raw_doi = work.get("doi") or (work.get("ids") or {}).get("doi")
                if not raw_doi:
                    add_debug_row(debug_rows, "openalex", query, "-", "no_doi", work.get("id", ""))
                    continue

                raw_doi = str(raw_doi)
                if BAD_SUFFIX_RE.search(raw_doi):
                    add_debug_row(debug_rows, "openalex", query, raw_doi, "bad_doi_suffix")
                    continue

                doi = canonicalize_doi(raw_doi)
                if not doi:
                    add_debug_row(debug_rows, "openalex", query, raw_doi, "invalid_doi")
                    continue

                text = build_openalex_text(work)
                passed, hit_count = passes_all_groups(groups, text)

                if passed:
                    doi_key = doi.lower()
                    first_seen = doi_key not in discovered
                    discovered.setdefault(doi_key, set()).add("openalex")
                    if first_seen:
                        append_live_source(
                            doi=doi_key,
                            source="openalex",
                            live_sources_file=live_sources_file,
                            seen_live=seen_live_dois,
                        )
                else:
                    add_debug_row(
                        debug_rows,
                        "openalex",
                        query,
                        doi,
                        "group_filter_fail",
                        f"group_matches={hit_count}/{len(groups)}",
                    )

            time.sleep(uniform(delay_min, delay_max))

    return discovered


def rescreen_dois_openalex(
    dois: List[str],
    doi_to_groups: Dict[str, Sequence[Sequence[str]]],
    drop_if_lookup_fail: bool,
    delay_min: float,
    delay_max: float,
) -> Tuple[List[str], List[str]]:
    kept: List[str] = []
    debug_rows: List[str] = ["doi\treason\tdetail"]

    for doi in dois:
        groups = doi_to_groups.get(doi)
        if not groups:
            kept.append(doi)
            debug_rows.append(f"{doi}\tno_group_context\tkept")
            continue

        work = get_openalex_work_by_doi(doi)
        if not work:
            if drop_if_lookup_fail:
                debug_rows.append(f"{doi}\tlookup_failed\tdropped")
            else:
                kept.append(doi)
                debug_rows.append(f"{doi}\tlookup_failed\tkept")
            time.sleep(uniform(delay_min, delay_max))
            continue

        text = build_openalex_text(work)
        if not text:
            if drop_if_lookup_fail:
                debug_rows.append(f"{doi}\tempty_metadata\tdropped")
            else:
                kept.append(doi)
                debug_rows.append(f"{doi}\tempty_metadata\tkept")
            time.sleep(uniform(delay_min, delay_max))
            continue

        passed, hit_count = passes_all_groups(groups, text)
        if passed:
            kept.append(doi)
            debug_rows.append(f"{doi}\tpassed_openalex_rescreen\t")
        else:
            debug_rows.append(f"{doi}\tfailed_openalex_rescreen\tgroup_matches={hit_count}/{len(groups)}")

        time.sleep(uniform(delay_min, delay_max))

    return kept, debug_rows


# -----------------------------
# Main
# -----------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover relevant DOIs from OpenAlex, Scopus, and Web of Science using hybrid queries parsed from descriptor_keywords.txt."
    )

    parser.add_argument("--descriptor_file", default="", help="Path to descriptor_keywords.txt, required for OpenAlex hybrid mode.")
    parser.add_argument("--sources", nargs="+", default=["openalex"], choices=["openalex", "scopus", "wos"],
                        help="Sources to search. Scopus and WOS require API keys.")
    parser.add_argument("--scopus_api_key", default="", help="Scopus API key. If omitted, SCOPUS_API_KEY env var is used.")
    parser.add_argument("--wos_api_key", default="", help="Web of Science API key. If omitted, WOS_API_KEY env var is used.")
    parser.add_argument("--wos_mode", choices=["starter", "expanded"], default="starter")
    parser.add_argument("--scopus_wos_query_file", default="", help="Path to OWF_ScopusQueries.txt. Used directly for Scopus and converted to TS=(...) for WOS.")
    parser.add_argument("--max_queries_per_block", type=int, default=250)
    parser.add_argument("--max_total_queries", type=int, default=2000)
    parser.add_argument("--max_results_per_page", type=int, default=50)
    parser.add_argument("--max_pages_per_query", type=int, default=2)
    parser.add_argument("--search_delay_min", type=float, default=0.4)
    parser.add_argument("--search_delay_max", type=float, default=1.0)

    parser.add_argument("--disable_rescreen", action="store_true")
    parser.add_argument("--rescreen_drop_if_lookup_fail", action="store_true")

    parser.add_argument("--live_sources_file", default=str(ROOT / "doi_sources_live.txt"))
    parser.add_argument("--append_live_outputs", action="store_true",
                        help="Append to existing live source file instead of clearing it at start.")

    parser.add_argument("--dois_file", default=str(ROOT / "dois.txt"))
    parser.add_argument("--raw_dois_file", default=str(ROOT / "dois_raw_discovered.txt"))
    parser.add_argument("--doi_sources_file", default=str(ROOT / "doi_sources.txt"))
    parser.add_argument("--debug_rejections_file", default=str(ROOT / "debug_rejections.tsv"))
    parser.add_argument("--debug_rescreen_file", default=str(ROOT / "debug_openalex_rescreen.tsv"))
    parser.add_argument("--query_audit_file", default=str(ROOT / "hybrid_openalex_queries.json"))

    args = parser.parse_args()

    if args.max_queries_per_block < 1:
        raise ValueError("--max_queries_per_block must be >= 1")
    if args.max_total_queries < 1:
        raise ValueError("--max_total_queries must be >= 1")
    if args.max_results_per_page < 1:
        raise ValueError("--max_results_per_page must be >= 1")
    if args.max_pages_per_query < 1:
        raise ValueError("--max_pages_per_query must be >= 1")

    seen_live_dois: Set[str] = set()
    if args.append_live_outputs:
        try:
            with open(args.live_sources_file, "r", encoding="utf-8", errors="ignore") as f:
                seen_live_dois = {
                    line.split("\t", 1)[0].strip().lower()
                    for line in f
                    if line.strip()
                }
        except FileNotFoundError:
            pass
    else:
        open(args.live_sources_file, "w", encoding="utf-8").close()

    openalex_query_rows: List[Dict[str, Any]] = []
    full_boolean_query_rows: List[Dict[str, Any]] = []

    if "openalex" in args.sources:
        if not args.descriptor_file:
            raise ValueError("--descriptor_file is required when --sources includes openalex")
        print(f"[INFO] Parsing descriptor file for OpenAlex hybrid mode: {args.descriptor_file}", flush=True)
        parsed_blocks = parse_descriptor_blocks(args.descriptor_file)
        print(f"[INFO] Parsed TS blocks with >=2 AND groups: {len(parsed_blocks)}", flush=True)
        if not parsed_blocks:
            raise ValueError("No valid TS blocks found. Check descriptor file formatting.")

        openalex_query_rows = generate_all_hybrid_queries(
            parsed_blocks=parsed_blocks,
            max_queries_per_block=args.max_queries_per_block,
            max_total_queries=args.max_total_queries,
        )
        if not openalex_query_rows:
            raise ValueError("No hybrid OpenAlex queries generated.")

    if "scopus" in args.sources or "wos" in args.sources:
        if not args.scopus_wos_query_file:
            raise ValueError("--scopus_wos_query_file is required when --sources includes scopus or wos")
        print(f"[INFO] Loading full Boolean Scopus/WOS query file: {args.scopus_wos_query_file}", flush=True)
        full_boolean_query_rows = build_full_boolean_query_rows(args.scopus_wos_query_file)
        if not full_boolean_query_rows:
            raise ValueError("No TITLE-ABS-KEY queries found in --scopus_wos_query_file")
        print(f"[INFO] Full Boolean queries loaded: {len(full_boolean_query_rows)}", flush=True)

    audit_payload = {
        "sources": args.sources,
        "descriptor_file": args.descriptor_file,
        "scopus_wos_query_file": args.scopus_wos_query_file,
        "openalex_query_count": len(openalex_query_rows),
        "full_boolean_query_count": len(full_boolean_query_rows),
        "scopus_query_field": "TITLE-ABS-KEY",
        "wos_query_field": "TS / Topic",
        "openalex_queries": [
            {
                "index": i + 1,
                "block_id": row.get("block_id"),
                "query": row["query"],
                "group_count": len(row["groups"]),
                "group_sizes": [len(g) for g in row["groups"]],
            }
            for i, row in enumerate(openalex_query_rows)
        ],
        "scopus_wos_queries": [
            {
                "index": i + 1,
                "label": row["label"],
                "scopus_query": row["scopus_query"],
                "wos_query": row["wos_query"],
            }
            for i, row in enumerate(full_boolean_query_rows)
        ],
    }

    Path(args.query_audit_file).write_text(
        json.dumps(audit_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"[INFO] OpenAlex hybrid queries: {len(openalex_query_rows)}", flush=True)
    print(f"[INFO] Scopus/WOS full Boolean queries: {len(full_boolean_query_rows)}", flush=True)
    print(f"[INFO] Query audit written to: {args.query_audit_file}", flush=True)
    print(f"[INFO] Live DOI source output: {args.live_sources_file}", flush=True)

    debug_rows: List[str] = ["source\tquery\tdoi\treason\tdetail"]

    scopus_api_key = args.scopus_api_key or os.getenv("SCOPUS_API_KEY", "")
    wos_api_key = args.wos_api_key or os.getenv("WOS_API_KEY", "")

    discovered_maps: List[Dict[str, Set[str]]] = []

    if "openalex" in args.sources:
        discovered_maps.append(discover_from_openalex(
            query_rows=openalex_query_rows,
            per_page=args.max_results_per_page,
            max_pages_per_query=args.max_pages_per_query,
            delay_min=args.search_delay_min,
            delay_max=args.search_delay_max,
            allowed_types=DEFAULT_ALLOWED_TYPES,
            live_sources_file=args.live_sources_file,
            seen_live_dois=seen_live_dois,
            debug_rows=debug_rows,
        ))

    if "scopus" in args.sources:
        discovered_maps.append(discover_from_scopus(
            query_rows=full_boolean_query_rows,
            api_key=scopus_api_key,
            per_page=args.max_results_per_page,
            count_cap=25,
            max_pages_per_query=args.max_pages_per_query,
            delay_min=args.search_delay_min,
            delay_max=args.search_delay_max,
            live_sources_file=args.live_sources_file,
            seen_live_dois=seen_live_dois,
            debug_rows=debug_rows,
        ))

    if "wos" in args.sources:
        discovered_maps.append(discover_from_wos(
            query_rows=full_boolean_query_rows,
            api_key=wos_api_key,
            mode=args.wos_mode,
            per_page=args.max_results_per_page,
            max_pages_per_query=args.max_pages_per_query,
            delay_min=args.search_delay_min,
            delay_max=args.search_delay_max,
            live_sources_file=args.live_sources_file,
            seen_live_dois=seen_live_dois,
            debug_rows=debug_rows,
        ))

    discovered = merge_discovery_maps(*discovered_maps)
    raw_dois = sorted(discovered.keys())

    # Build DOI -> first matching group's context for rescreening.
    # If a DOI was found by multiple queries, first group context is used.
    doi_to_groups: Dict[str, Sequence[Sequence[str]]] = {}
    live_dois = set(raw_dois)
    for row in openalex_query_rows:
        # We do not know exact DOI->query from the simple source map,
        # so use block context broadly by assigning the first block context.
        # This rescreen is conservative because discovery already filtered by groups.
        for doi in live_dois:
            doi_to_groups.setdefault(doi, row["groups"])

    write_lines(args.raw_dois_file, raw_dois)
    write_lines(args.doi_sources_file, [f"{doi}\t{','.join(sorted(discovered[doi]))}" for doi in raw_dois])
    write_lines(args.debug_rejections_file, debug_rows)

    final_dois = raw_dois

    if not args.disable_rescreen:
        final_dois, rescreen_rows = rescreen_dois_openalex(
            dois=raw_dois,
            doi_to_groups=doi_to_groups,
            drop_if_lookup_fail=args.rescreen_drop_if_lookup_fail,
            delay_min=args.search_delay_min,
            delay_max=args.search_delay_max,
        )
        write_lines(args.debug_rescreen_file, rescreen_rows)
        print(f"✅ OpenAlex rescreen: {len(raw_dois)} -> {len(final_dois)}", flush=True)
    else:
        write_lines(args.debug_rescreen_file, ["doi\treason\tdetail", "all\trescreen_disabled\tkept"])
        print("✅ OpenAlex rescreen disabled", flush=True)

    write_lines(args.dois_file, final_dois)

    print(f"✅ Wrote final DOIs: {args.dois_file} ({len(final_dois)})", flush=True)
    print(f"✅ Wrote raw discovered DOIs: {args.raw_dois_file} ({len(raw_dois)})", flush=True)
    print(f"✅ Wrote DOI source map: {args.doi_sources_file}", flush=True)
    print(f"✅ Wrote live DOI source map: {args.live_sources_file}", flush=True)
    print(f"✅ Wrote rejection debug: {args.debug_rejections_file} ({max(0, len(debug_rows) - 1)})", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Fatal error: {e}", file=sys.stderr)
        sys.exit(1)

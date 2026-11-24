"""Evidence tools available to the investigation agent.

Only two tools are exposed, and both respect the scenario phase so that the
09:35 records (D07–D08) are invisible until the researcher releases them.

Every tool returns a structured `status` so the agent (and the practitioner)
can distinguish an empty search (`no_matches`) from a failure (`tool_error`)
or a record that exists but is not yet available (`not_available`).
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

from rank_bm25 import BM25Okapi

from state import PHASE_ORDER, ScenarioRecord

RECORDS_DIR = Path(__file__).parent / "records"

_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "is", "are", "was", "be", "by",
    "with", "as", "at", "it", "this", "that", "from", "we", "our", "you", "i", "has", "have",
    "not", "no", "so", "if", "do", "does", "any", "what", "which", "who", "about",
}


# ---------------------------------------------------------------------------
# Record loading
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def load_records() -> Dict[str, ScenarioRecord]:
    records: Dict[str, ScenarioRecord] = {}
    for path in sorted(RECORDS_DIR.glob("D*.json")):
        rec = ScenarioRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))
        records[rec.doc_id] = rec
    return records


def is_released(rec: ScenarioRecord, phase: str) -> bool:
    return PHASE_ORDER.index(rec.release_phase) <= PHASE_ORDER.index(phase)


def released_ids(phase: str) -> List[str]:
    return [d for d, r in load_records().items() if is_released(r, phase)]


def record_catalogue(phase: str) -> List[Dict[str, Any]]:
    """Light metadata list the agent sees up front (no content)."""
    return [
        {
            "doc_id": r.doc_id,
            "title": r.title,
            "source_type": r.source_type,
            "author_role": r.author_role,
            "updated_at": r.updated_at,
        }
        for r in load_records().values()
        if is_released(r, phase)
    ]


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def _tokens(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9#][a-z0-9#\-\.]*", text.lower()) if t not in _STOPWORDS]


def _passages(phase: str) -> List[Dict[str, str]]:
    out = []
    for r in load_records().values():
        if not is_released(r, phase):
            continue
        for i, para in enumerate(p.strip() for p in r.content.split("\n\n")):
            if para:
                out.append({"doc_id": r.doc_id, "title": r.title, "passage_id": f"{r.doc_id}.{i + 1}", "text": para})
        for d in r.definitions:
            out.append(
                {
                    "doc_id": r.doc_id,
                    "title": r.title,
                    "passage_id": f"{r.doc_id}.def",
                    "text": f"Definition – {d.term}: {d.meaning}",
                }
            )
    return out


def search_passages(query: str, phase: str, k: int = 4) -> Dict[str, Any]:
    """Keyword (BM25) search over passages of released records."""
    try:
        q = _tokens(query or "")
        if not q:
            return {"status": "tool_error", "query": query, "error": "Query is empty after removing stopwords."}
        passages = _passages(phase)
        corpus = [_tokens(p["title"] + " " + p["text"]) for p in passages]
        bm25 = BM25Okapi(corpus)
        scores = bm25.get_scores(q)
        qset = set(q)
        ranked = sorted(
            (
                (s, p)
                for s, p, toks in zip(scores, passages, corpus)
                if qset & set(toks)  # require real term overlap
            ),
            key=lambda x: x[0],
            reverse=True,
        )[:k]
        searched = sorted({p["doc_id"] for p in passages})
        if not ranked:
            return {"status": "no_matches", "query": query, "searched_docs": searched, "results": []}
        return {
            "status": "found",
            "query": query,
            "searched_docs": searched,
            "results": [
                {"doc_id": p["doc_id"], "passage_id": p["passage_id"], "title": p["title"], "text": p["text"], "score": round(float(s), 3)}
                for s, p in ranked
            ],
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {"status": "tool_error", "query": query, "error": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def read_record(doc_id: str, phase: str) -> Dict[str, Any]:
    try:
        doc_id = (doc_id or "").strip().upper()
        rec = load_records().get(doc_id)
        if rec is None:
            return {"status": "not_found", "doc_id": doc_id, "error": f"No record with id {doc_id}."}
        if not is_released(rec, phase):
            # Do not leak content or title of unreleased records.
            return {"status": "not_available", "doc_id": doc_id, "error": "Record not available at this time."}
        return {"status": "found", "doc_id": doc_id, "record": rec.model_dump()}
    except Exception as exc:  # pragma: no cover - defensive
        return {"status": "tool_error", "doc_id": doc_id, "error": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# Dispatch + declarations for function calling
# ---------------------------------------------------------------------------

TOOL_DECLARATIONS = [
    {
        "name": "search_passages",
        "description": (
            "Keyword search over passages of the records currently available. Returns status "
            "'found' with matching passages, 'no_matches' if nothing matched (an empty result is "
            "evidence of absence only within these records), or 'tool_error'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {"query": {"type": "STRING", "description": "Keywords to search for."}},
            "required": ["query"],
        },
    },
    {
        "name": "read_record",
        "description": (
            "Read the full content and metadata (source, author role, updated_at, team-specific "
            "definitions, dependencies, context notes) of one record by id, e.g. 'D03'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {"doc_id": {"type": "STRING", "description": "Record id such as D01."}},
            "required": ["doc_id"],
        },
    },
]


def execute_tool(name: str, args: Dict[str, Any], phase: str) -> Dict[str, Any]:
    if name == "search_passages":
        return search_passages(str(args.get("query", "")), phase)
    if name == "read_record":
        return read_record(str(args.get("doc_id", "")), phase)
    return {"status": "tool_error", "error": f"Unknown tool {name!r}."}


def summarise_observation(name: str, result: Dict[str, Any]) -> str:
    status = result.get("status")
    if status == "found" and name == "search_passages":
        hits = ", ".join(f"{r['passage_id']}" for r in result["results"])
        return f"{len(result['results'])} passage(s): {hits}"
    if status == "found" and name == "read_record":
        r = result["record"]
        return f"Read {r['doc_id']} – {r['title']} (updated {r['updated_at'].replace('T', ' ')[:16]})"
    if status == "no_matches":
        return f"No matches in {', '.join(result.get('searched_docs', []))}"
    return result.get("error", str(status))

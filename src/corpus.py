"""
corpus.py — Single source of truth for loading + deduplicating parsed articles.

Both ingestion paths (baseline ChromaDB, graph Neo4j) must see the *same* set of
article records, or the two stores drift and the Baseline-vs-GraphRAG comparison
is no longer controlled. Previously each deduped independently with "keep the
last record per (regulation_id, article_number)" — which arbitrarily kept a
Penjelasan stub ("Cukup jelas.") or a lampiran fragment over the batang tubuh
(operative provision). See ADR 0006.

`load_articles()` replaces both ad-hoc dedups: it keeps the longest
*non-penjelasan, non-trivial* record per ID. This resolves ~18k of the ~19k
multi-record groups (incl. lampiran artifacts). The remaining ~1.1k true
omnibus collisions (≥2 co-equal provisions sharing a Pasal number, in UU/PP/Perpu
amendment laws) cannot be fixed by selection — they need an ID scheme (ADR 0006
item 2). Until then dedup keeps the longest and logs how many co-equal provisions
it had to drop, so the loss stays visible rather than silent.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from src.config import ARTICLES_JSON

logger = logging.getLogger(__name__)

# A Penjelasan (elucidation) record describes a Pasal rather than stating the
# norm. It opens by naming the unit it explains ("Ayat (1)", "Huruf a",
# "Angka 2") or is the boilerplate "Cukup jelas." Batang tubuh instead opens with
# a bare ayat marker "(1)" or the provision text directly.
_PENJELASAN_RE = re.compile(r"^\s*(Ayat\s*\(|Huruf\s|Angka\s|Cukup\s+jelas)", re.IGNORECASE)
_TRIVIAL_LEN = 15
# Two distinct bodies both longer than this are treated as co-equal provisions
# (a true collision), not a body-plus-fragment artifact.
_COLLISION_MIN_LEN = 300


def article_text(record: dict[str, Any]) -> str:
    """The text ingested downstream (Chroma doc / :Article.text)."""
    return (record.get("content") or record.get("raw_text") or "").strip()


def _is_penjelasan(text: str) -> bool:
    return bool(_PENJELASAN_RE.match(text))


def _is_usable_body(text: str) -> bool:
    """A normative batang-tubuh candidate: non-trivial and not elucidation."""
    return len(text) >= _TRIVIAL_LEN and not _is_penjelasan(text)


def _make_id(record: dict[str, Any]) -> str:
    return f"{record['regulation_id']}::{record['article_number']}"


def _pick(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Choose the canonical record for one ID.

    Preference: longest usable batang tubuh → longest record of any kind →
    last record (legacy fallback, only when every record is empty)."""
    usable = [r for r in records if _is_usable_body(article_text(r))]
    if usable:
        return max(usable, key=lambda r: len(article_text(r)))
    nonempty = [r for r in records if article_text(r)]
    if nonempty:
        return max(nonempty, key=lambda r: len(article_text(r)))
    return records[-1]


def _is_true_collision(records: list[dict[str, Any]]) -> bool:
    """≥2 distinct co-equal provisions share this ID (omnibus reuse)."""
    long_bodies = {
        article_text(r)[:200]
        for r in records
        if _is_usable_body(article_text(r)) and len(article_text(r)) > _COLLISION_MIN_LEN
    }
    return len(long_bodies) >= 2


def dedup_articles(raw_articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse to one record per ID using the ADR 0006 rule.

    Output order follows first-seen ID order for deterministic ingestion."""
    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for r in raw_articles:
        aid = _make_id(r)
        if aid not in groups:
            groups[aid] = []
            order.append(aid)
        groups[aid].append(r)

    deduped: list[dict[str, Any]] = []
    collisions = 0
    for aid in order:
        records = groups[aid]
        if len(records) > 1 and _is_true_collision(records):
            collisions += 1
        deduped.append(_pick(records))

    if len(deduped) < len(raw_articles):
        logger.info(
            "Deduplicated %d → %d unique articles (longest non-penjelasan per ID).",
            len(raw_articles), len(deduped),
        )
    if collisions:
        logger.warning(
            "%d IDs are true omnibus collisions (>=2 co-equal provisions share a "
            "Pasal number); kept the longest and dropped the rest. These need the "
            "ID scheme in ADR 0006 item 2.",
            collisions,
        )
    return deduped


def load_articles(articles_path: str = ARTICLES_JSON) -> list[dict[str, Any]]:
    """Load parsed articles and return one canonical record per ID."""
    with open(articles_path, encoding="utf-8") as fh:
        raw_articles: list[dict[str, Any]] = json.load(fh)
    logger.info("Loaded %d articles from '%s'.", len(raw_articles), articles_path)
    return dedup_articles(raw_articles)

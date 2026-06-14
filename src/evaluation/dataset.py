"""
dataset.py — Load the hand-labelled ground-truth set from JSONL.

Schema (one object per line):
    id                 str
    question           str
    gold_article_ids   list[str]   "<regulation_id>::<article_number>"
    gold_answer        str         optional
    hop_type           str         "single" | "multi"
    notes              str         optional, free text
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

from src.config import BASE_DIR

EVAL_PATH = Path(BASE_DIR) / "data" / "ground_truth" / "eval.jsonl"


@dataclass
class EvalItem:
    id: str
    question: str
    gold_article_ids: list[str]
    gold_answer: str = ""
    hop_type: str = "single"
    notes: str = ""
    extra: dict = field(default_factory=dict)


def load_dataset(path: Path = EVAL_PATH) -> list[EvalItem]:
    items: list[EvalItem] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            items.append(EvalItem(
                id=row["id"],
                question=row["question"],
                gold_article_ids=row["gold_article_ids"],
                gold_answer=row.get("gold_answer", ""),
                hop_type=row.get("hop_type", "single"),
                notes=row.get("notes", ""),
                extra={k: v for k, v in row.items() if k not in {
                    "id", "question", "gold_article_ids",
                    "gold_answer", "hop_type", "notes",
                }},
            ))
    return items

"""
main.py — CLI entry point for the Baseline RAG and GraphRAG pipelines.

Usage:
  # 1. Ingestion (run each once)
  python main.py ingest-baseline                       # Populate ChromaDB
  python main.py ingest-graph                          # Build Neo4j graph

  # 2. Query
  python main.py query-baseline "Apa syarat untuk dapat dikukuhkan sebagai Pengusaha Kena Pajak?"
  python main.py query-graph    "Apa syarat untuk dapat dikukuhkan sebagai Pengusaha Kena Pajak?"

  # 3. Evaluation (see `python -m src.evaluation --help` for full options)
  python main.py eval run --system baseline --run-id v1
  python main.py eval run --system graph    --run-id v1
  python main.py eval report --run-id v1 [--with-ragas]
"""
import sys
from typing import Any


def cmd_ingest_baseline() -> None:
    from src.baseline_rag.ingestion import ingest
    ingest()


def cmd_ingest_graph() -> None:
    from src.graph_rag.ingestion import build_graph
    build_graph()


def cmd_query_baseline(question: str) -> None:
    from src.baseline_rag.pipeline import BaselineRAGPipeline
    pipeline = BaselineRAGPipeline()
    _print_result(pipeline.query(question), system_name="Baseline RAG")


def cmd_query_graph(question: str) -> None:
    from src.graph_rag.pipeline import GraphRAGPipeline
    pipeline = GraphRAGPipeline()
    _print_result(pipeline.query(question), system_name="Graph RAG")


def _print_result(result: dict[str, Any], system_name: str) -> None:
    print("\n" + "=" * 60)
    print(f"[{system_name}] Q: {result['question']}")
    print("=" * 60)
    print(f"\n{result['answer']}\n")
    print("-" * 60)
    print(f"Context articles used ({len(result['context'])}):")
    for a in result["context"]:
        print(f"  [{a['source']}] {a['regulation_id']} Pasal {a['article_number']}")
    print()


def cmd_eval(rest: list[str]) -> None:
    from src.evaluation.__main__ import main as eval_main
    sys.exit(eval_main(rest))


_COMMANDS = {
    "ingest-baseline": cmd_ingest_baseline,
    "ingest-graph":    cmd_ingest_graph,
    "query-baseline":  cmd_query_baseline,
    "query-graph":     cmd_query_graph,
    "eval":            cmd_eval,
}


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if len(sys.argv) >= 2 else 1)

    command = sys.argv[1]
    if command not in _COMMANDS:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)

    if command.startswith("query-"):
        if len(sys.argv) < 3:
            print(f"Usage: python main.py {command} <question>")
            sys.exit(1)
        _COMMANDS[command](" ".join(sys.argv[2:]))
    elif command == "eval":
        _COMMANDS[command](sys.argv[2:])
    else:
        _COMMANDS[command]()

"""
main.py — CLI entry point for the GraphRAG pipeline.

Usage:
  # 1. Build the Neo4j graph (run once after parsing articles)
  python main.py ingest

  # 2. Ask a question via GraphRAG
  python main.py query "Apa saja syarat penyaluran DBH Sawit?"
"""
import sys


def cmd_ingest():
    from src.graph_rag.ingestion import build_graph
    build_graph()


def cmd_query(question: str):
    from src.graph_rag.pipeline import GraphRAGPipeline
    pipeline = GraphRAGPipeline()
    result = pipeline.query(question)

    print("\n" + "=" * 60)
    print(f"Q: {result['question']}")
    print("=" * 60)
    print(f"\n{result['answer']}\n")
    print("-" * 60)
    print(f"Context articles used ({len(result['context'])}):")
    for a in result["context"]:
        print(f"  [{a['source']}] {a['regulation_id']} Pasal {a['article_number']}")
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "ingest":
        cmd_ingest()
    elif command == "query":
        if len(sys.argv) < 3:
            print("Usage: python main.py query <question>")
            sys.exit(1)
        cmd_query(" ".join(sys.argv[2:]))
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)

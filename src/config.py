import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no external dependency). Sets vars that aren't
    already in the environment; ignores blank lines and `#` comments."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv(BASE_DIR / ".env")

# Data paths
ARTICLES_JSON = str(BASE_DIR / "data" / "processed" / "articles.json")
CHROMA_DIR = str(BASE_DIR / "data" / "chroma_db")
CHROMA_COLLECTION = "tax_articles"

# Ollama
OLLAMA_BASE_URL = "http://localhost:11434"
EMBED_MODEL = "qwen3-embedding:0.6b"
LLM_MODEL = "qwen3.5:9b"
EMBED_DIM = 1024
LLM_NUM_CTX = 16384

# Neo4j — read from environment (.env, gitignored). Never commit the password.
NEO4J_URI = os.environ.get("NEO4J_URI", "neo4j://127.0.0.1:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD")
if not NEO4J_PASSWORD:
    raise RuntimeError(
        "NEO4J_PASSWORD is not set. Add it to .env (see .env.example) "
        "or export it in your shell."
    )

# Retrieval
TOP_K_VECTOR = 5
GRAPH_HOP_DEPTH = 2

# GraphRAG re-ranking (strict parity: graph feeds the same TOP_K_VECTOR budget as
# baseline, but a reference-linked neighbor may displace a weak seed). Final score
# = query_similarity + GRAPH_RERANK_ALPHA * graph_boost, where graph_boost rewards
# neighbors linked from strong, nearby seeds. Pure similarity (alpha=0) reproduces
# baseline exactly. TUNE ALPHA ON A HELD-OUT SPLIT, never on the eval test set.
GRAPH_RERANK_ALPHA = 0.15  # tuned on dev split (scripts.tune_alpha), 2026-07-01
GRAPH_CONTEXT_BUDGET = TOP_K_VECTOR

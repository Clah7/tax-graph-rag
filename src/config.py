from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

# Data paths
ARTICLES_JSON = str(BASE_DIR / "data" / "processed" / "articles.json")
CHROMA_DIR = str(BASE_DIR / "data" / "chroma_db")
CHROMA_COLLECTION = "tax_articles"

# Ollama
OLLAMA_BASE_URL = "http://localhost:11434"
EMBED_MODEL = "qwen3-embedding:0.6b"
LLM_MODEL = "qwen3.5:9b"
EMBED_DIM = 1024

# Neo4j — override via environment variables in production
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "*"

# Retrieval
TOP_K_VECTOR = 5       
GRAPH_HOP_DEPTH = 2    

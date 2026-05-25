import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"


def load_env(env_path: Path = ENV_PATH) -> None:
    """Load simple KEY=VALUE pairs from .env into os.environ."""
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


load_env()

MILVUS_URI = os.getenv("MILVUS_URI", "http://localhost:19530")
MILVUS_DATABASE_NAME = os.getenv("MILVUS_DATABASE_NAME", "milvus_database")
MILVUS_COLLECTION_NAME = os.getenv("MILVUS_COLLECTION_NAME", "my_collection_demo_chunked")

OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.siliconflow.cn/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

CLIENT_MODEL = os.getenv("CLIENT_MODEL", "Qwen/Qwen2.5-7B-Instruct")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
USE_RERANKER = os.getenv("USE_RERANKER", "false").lower() in {"1", "true", "yes", "y"}

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))
INSERT_BATCH_SIZE = int(os.getenv("INSERT_BATCH_SIZE", "10"))
REPLACE_EXISTING_DOCS = os.getenv("REPLACE_EXISTING_DOCS", "true").lower() in {"1", "true", "yes", "y"}

SEARCH_LIMIT = int(os.getenv("SEARCH_LIMIT", "5"))
HYBRID_RECALL_LIMIT = int(os.getenv("HYBRID_RECALL_LIMIT", "20"))
RERANK_TOP_N = int(os.getenv("RERANK_TOP_N", "5"))
JSON_DATA_PATH = os.getenv("JSON_DATA_PATH", str(BASE_DIR / "test.json"))
RECALL_EVAL_CSV = os.getenv("RECALL_EVAL_CSV", "rag_recall_eval_questions.csv")

HYBRID_DENSE_WEIGHT = float(os.getenv("HYBRID_DENSE_WEIGHT", "0.8"))
HYBRID_TITLE_WEIGHT = float(os.getenv("HYBRID_TITLE_WEIGHT", "0.1"))
HYBRID_CONTENT_WEIGHT = float(os.getenv("HYBRID_CONTENT_WEIGHT", "0.1"))
DEDUP_BY_DOC = os.getenv("DEDUP_BY_DOC", "true").lower() in {"1", "true", "yes", "y"}
NEIGHBOR_CHUNK_WINDOW = int(os.getenv("NEIGHBOR_CHUNK_WINDOW", "1"))

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = "postgresql+psycopg://docsearch:docsearch@localhost:5432/docsearch"

    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "docsearch"
    minio_secure: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # Embedding model
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimension: int = 1024
    embedding_max_tokens: int = 512

    # Reranker
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_enabled: bool = True
    reranker_top_n: int = 20

    # Retrieval parameters
    hnsw_ef_search: int = 100
    rrf_k: int = 60

    # Routing thresholds (FR-022, FR-023)
    small_doc_threshold: int = 5
    small_size_mb: float = 1.0
    grep_doc_limit: int = 20

    # Chunking
    chunk_max_tokens: int = 512
    read_max_tokens: int = 2000
    read_max_tokens_limit: int = 4000

    # Logging
    log_level: str = "INFO"

    # LLM (for DeepAgents / LangServe)
    chat_model: str = "gpt-4o-mini"
    openai_api_key: str = ""
    openai_api_base: str = "https://api.openai.com/v1"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Connection pool
    db_pool_size: int = 20
    api_reload: bool = False


settings = Settings()

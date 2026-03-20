"""
Configuration management using pydantic-settings (v2.x)
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # Telegram
    telegram_bot_token: str = ""

    # Groq LLM
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # Neo4j
    neo4j_uri: str = ""
    neo4j_username: str = ""
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"

    # AstraDB
    astra_db_token: str = ""
    astra_db_api_endpoint: str = ""

    # Jina AI Embeddings
    jina_api_key: str = ""
    jina_embedding_model: str = "jina-embeddings-v3"

    # App
    log_level: str = "INFO"
    graph_output_dir: str = "./graphs"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow"
    )

@lru_cache()
def get_settings() -> Settings:
    return Settings()

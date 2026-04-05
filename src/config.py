"""
Configuration Management

Uses Pydantic Settings to manage environment variables with type safety 
and validation. Prioritizes .env file values over defaults.
"""
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Application-wide configuration settings."""
    GROQ_API_KEY: str
    DATABASE_URL: str = "postgresql://postgres:password@db:5432/postgres"
    SANDBOX_URL: str = "postgresql://postgres:password@sandbox:5432/postgres"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    MAX_FILE_SIZE: int = 1 * 1024 * 1024  # 1MB
    
    # Model configurations
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    LLM_BASE_URL: Optional[str] = None # Set this for offline local LLMs (e.g. Ollama)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

def get_settings():
    return settings
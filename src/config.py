"""
Configuration Management

Uses Pydantic Settings to manage environment variables with type safety 
and validation. Prioritizes .env file values over defaults.
"""
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Application-wide configuration settings."""
    # Default to a placeholder to prevent CI/CD crashes. 
    # Real keys should be provided via environment variables.
    GROQ_API_KEY: str = "REPLACE_ME_IN_PRODUCTION"
    
    DATABASE_URL: str = "postgresql://postgres:password@db:5432/postgres"
    SANDBOX_URL: str = "postgresql://postgres:password@sandbox:5432/postgres"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    MAX_FILE_SIZE: int = 1 * 1024 * 1024  # 1MB
    
    # Model configurations
    LLM_PROVIDER: str = "groq" # 'groq' or 'ollama'
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    OLLAMA_MODEL: str = "llama3" # Default Ollama model
    LLM_BASE_URL: Optional[str] = None # Set this for offline local LLMs (e.g. Ollama)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

def get_settings():
    return settings
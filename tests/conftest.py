import pytest
import pytest_asyncio
from httpx import AsyncClient
from unittest.mock import patch
from dotenv import load_dotenv
from src.main import app
from src.agents.llm_agent import LLMAgent # Updated import

load_dotenv() # Load environment variables from .env for local pytest runs

@pytest_asyncio.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

@pytest.fixture
def mock_llm_agent(): # Renamed fixture
    with patch("src.main.llm_agent", spec=LLMAgent) as mock: # Updated patch target and spec
        yield mock
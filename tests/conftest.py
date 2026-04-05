import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch

from src.main import app
from src.agents.groq_client import GroqAgent

@pytest.fixture(scope="session")
def event_loop():
    """Overrides the default function-scoped event_loop fixture to session scope."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
def anyio_backend():
    """Configures pytest-asyncio to use the 'asyncio' backend."""
    return "asyncio"

@pytest_asyncio.fixture(scope="session")
async def client():
    """Provides an AsyncClient for testing FastAPI endpoints."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.fixture
def mock_groq_agent():
    """Mocks the GroqAgent for isolated API endpoint testing."""
    with patch("src.main.groq_agent", spec=GroqAgent) as mock_agent:
        # Mock common methods that might be called
        mock_agent.analyze_schema = AsyncMock(return_value="Mock Health Report")
        mock_agent.semantic_rename = AsyncMock(return_value={"OLD_COL": "new_col"})
        mock_agent.analyze_normalization = AsyncMock(return_value={"god_tables": [], "recommendations": []})
        mock_agent.generate_modernized_ddl = AsyncMock(return_value="CREATE TABLE new_table (id INT);")
        mock_agent.generate_migration_script = AsyncMock(return_value="INSERT INTO new_table SELECT * FROM old_table;")
        mock_agent.fix_sql_errors = AsyncMock(return_value="FIXED SQL;")
        yield mock_agent
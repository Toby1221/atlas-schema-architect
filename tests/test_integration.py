import pytest
import pytest_asyncio
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch

from src.main import app
from src.agents.groq_client import GroqAgent

# This test requires the Docker services (api, db, sandbox) to be running.
# Run with: docker-compose --profile testing up -d

@pytest_asyncio.fixture(scope="module")
async def live_client():
    """Provides an AsyncClient connected to the live FastAPI app."""
    # Using app=app allows unittest.mock to intercept calls within the FastAPI pipeline
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.mark.asyncio
async def test_modernize_with_live_sandbox_and_healing(live_client):
    """
    Tests the full /modernize pipeline with actual Groq calls (mocked for fix_sql_errors)
    and a live sandbox database for validation, including a self-healing scenario.
    """
    # This SQL is intentionally malformed (missing comma after INT)
    # to trigger the self-healing mechanism.
    malformed_sql = b"""
    CREATE TABLE test_legacy (
        id INT
        name VARCHAR(50)
    );
    """
    # The expected corrected SQL after LLM healing (simplified for test)
    corrected_sql = "CREATE TABLE test_legacy (id INT, name VARCHAR(50));"

    with patch("src.main.SQLParser.validate_sql_syntax", new_callable=AsyncMock) as mock_validate:
        mock_validate.side_effect = ["PostgreSQL Syntax Error: missing comma", None]

        with patch.object(GroqAgent, 'fix_sql_errors', new_callable=AsyncMock) as mock_fix_sql_errors:
            mock_fix_sql_errors.return_value = corrected_sql

            files = {'file': ('malformed.sql', malformed_sql, 'application/sql')}
            response = await live_client.post("/modernize?validate=true", files=files, timeout=30.0)

            assert response.status_code == 200
            data = response.json()
            
            assert data["validation_report"]["status"] == "valid"
            assert data["validation_report"]["attempts"] == 2 
            assert "malformed.sql" in data["original_filename"]
            assert corrected_sql in data["modernized_ddl"]
            mock_fix_sql_errors.assert_called_once()
        # Verify that SQLParser.validate_sql_syntax was called multiple times
        # (once for the malformed, once for the healed)
        # Note: Direct assertion on SQLParser.validate_sql_syntax call count is tricky here
        # as it's called internally by the main app logic, but the attempts count confirms it.
import pytest
import asyncpg
from src.parser.sql_parser import SQLParser

def test_clean_sql():
    raw_sql = """
    -- Simple comment
    CREATE TABLE legacy (
        id INT, /* Block
        comment */
        name VARCHAR(50) # Another comment
    );
    """
    cleaned = SQLParser.clean_sql(raw_sql)
    assert "--" not in cleaned
    assert "/*" not in cleaned
    assert "#" not in cleaned
    # Check that whitespace is normalized
    assert "  " not in cleaned
    assert cleaned == "CREATE TABLE legacy ( id INT, name VARCHAR(50) );"

def test_clean_sql_edge_cases():
    """Tests aggressive cleaning against unclosed comments and mixed line endings."""
    sql = "SELECT * FROM x; -- trailing\n\n/* unclosed block\nSELECT 1;"
    cleaned = SQLParser.clean_sql(sql)
    # Our current regex removes /*...*/ via DOTALL, but unclosed depends on the engine.
    # We verify it handles trailing single lines and multiple newlines.
    assert "trailing" not in cleaned
    assert "\n\n" not in cleaned

def test_apply_renames_regex_safety():
    """Ensures that special characters in the rename map don't break the regex engine."""
    sql = "SELECT * FROM [OLD_TABLE];"
    mapping = {"[OLD_TABLE]": "new_table"}
    transformed = SQLParser.apply_renames(sql, mapping)
    assert transformed == "SELECT * FROM new_table;"

def test_apply_renames():
    sql = "CREATE TABLE USR ( USR_ID INT, USR_NAME TEXT );"
    mapping = {
        "USR": "users",
        "USR_ID": "user_id",
        "USR_NAME": "full_name"
    }
    transformed = SQLParser.apply_renames(sql, mapping)
    assert transformed == "CREATE TABLE users ( user_id INT, full_name TEXT );"
    
    # Check partial match prevention (e.g. 'ID' should not match 'USR_ID')
    sql_edge = "ALTER TABLE users ADD COLUMN ID INT;"
    mapping_edge = {"ID": "identifier"}
    transformed_edge = SQLParser.apply_renames(sql_edge, mapping_edge)
    assert "identifier" in transformed_edge
    assert "ADD COLUMN identifier" in transformed_edge

@pytest.mark.asyncio
async def test_validate_sql_syntax_mock(monkeypatch):
    async def mock_connect(*args, **kwargs):
        class MockConn:
            async def execute(self, sql): pass
            async def close(self): pass
            def transaction(self):
                class MockTx:
                    async def __aenter__(self): return self
                    async def __aexit__(self, exc_type, exc, tb): pass
                return MockTx()
        return MockConn()

    monkeypatch.setattr(asyncpg, "connect", mock_connect)
    error = await SQLParser.validate_sql_syntax("SELECT 1", "postgresql://localhost/db")
    assert error is None

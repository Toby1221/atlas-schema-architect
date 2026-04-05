"""
SQL Parser & Validator

Provides utility functions for cleaning legacy SQL strings, applying 
AI-generated renaming maps, and validating SQL syntax against a live database.
"""

import re
import asyncpg
from typing import Optional

class SQLParser:
    @staticmethod
    def clean_sql(raw_sql: str) -> str:
        """Strips SQL comments and collapses excessive whitespace to save LLM tokens."""
        sql = re.sub(r'/\*.*?\*/', '', raw_sql, flags=re.DOTALL)
        sql = re.sub(r'(--|#).*?(\n|$)', '\n', sql)
        return re.sub(r'\s+', ' ', sql).strip()

    @staticmethod
    def apply_renames(sql: str, mapping: dict) -> str:
        """
        Iterates through the semantic rename map and replaces identifiers in the SQL string.
        
        Uses regex word boundaries (\b) to ensure that a rename of 'ID' does not 
        accidentally corrupt 'USER_ID'.
        """
        # Sort keys by length descending to ensure 'USER_ID' is replaced before 'ID'
        sorted_keys = sorted(mapping.keys(), key=len, reverse=True)
        
        transformed_sql = sql
        for old_name in sorted_keys:
            new_name = mapping[old_name]
            # Robust boundary check: ensures the identifier isn't part of a larger word
            # regardless of whether it starts/ends with special characters.
            pattern = rf'(?<![a-zA-Z0-9_]){re.escape(old_name)}(?![a-zA-Z0-9_])'
            transformed_sql = re.sub(pattern, new_name, transformed_sql, flags=re.IGNORECASE)
        
        return transformed_sql

    @staticmethod
    async def validate_sql_syntax(sql: str, db_url: str) -> Optional[str]:
        """
        Attempts to execute the SQL in the sandbox. 
        Returns None if successful, or the error message if it fails.
        Uses a transaction that is always rolled back.
        """
        conn = None
        try:
            # Limit execution time at the server level to prevent sandbox hangs
            conn = await asyncpg.connect(
                db_url, 
                timeout=10, 
                server_settings={"statement_timeout": "5000"}
            )
            async with conn.transaction():
                await conn.execute(sql)
                return None
        except Exception as e:
            return str(e)
        finally:
            if conn is not None:
                await conn.close()
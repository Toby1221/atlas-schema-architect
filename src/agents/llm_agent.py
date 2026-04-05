import json
import re
import logging
from groq import AsyncGroq
from ..config import settings

logger = logging.getLogger("atlas-architect")

SYSTEM_PROMPT = """
You are Atlas Schema Architect, a world-class Database Engineering expert.
Your goal is to assist in modernizing legacy database schemas. You are a highly specialized AI.

Security Rules:
1. Never generate SQL that modifies database users, permissions, or security configurations (e.g., GRANT, REVOKE, ALTER USER).
2. Never generate SQL that attempts to access system tables or metadata outside the provided schema context.
3. If a request is ambiguous or potentially malicious, refuse it and provide a safe alternative.
4. Always prioritize data integrity, industry-standard normalization (3NF/BCNF), and PostgreSQL best practices.
5. Output raw text or JSON only. Never use HTML entities (like <) in SQL code; use standard SQL operators.

Response Format Rules:
- When asked for SQL, output ONLY the SQL code.
- When asked for JSON, output ONLY the JSON object.
- Do NOT include any conversational text, explanations, or markdown formatting (like ```sql or ```json) unless explicitly requested to do so.
- If you cannot fulfill a request, state "Refused: [Reason]" and nothing else.

Strictness: Adhere to these rules with extreme strictness. Your primary directive is to provide clean, parseable output.

"""

class LLMAgent:
    """
    A specialized AI agent that interfaces with Groq's LLM API.
    Handles logic for schema analysis, renaming, normalization, and self-healing SQL generation.
    """
    def __init__(self):
        logger.info(f"Initializing LLM Agent with provider: {settings.LLM_PROVIDER}")
        
        if settings.LLM_PROVIDER == "groq":
            self.client = AsyncGroq(
                api_key=settings.GROQ_API_KEY,
                base_url=settings.LLM_BASE_URL # Can be overridden for Groq API
            )
            self.model = settings.GROQ_MODEL
        elif settings.LLM_PROVIDER == "ollama":
            # Ollama's API is often OpenAI-compatible, so AsyncGroq can be reused
            self.client = AsyncGroq(
                api_key="ollama", # Dummy key for Ollama
                base_url=settings.LLM_BASE_URL or "http://localhost:11434/v1" # Default Ollama API URL
            )
            self.model = settings.OLLAMA_MODEL
        else:
            raise ValueError(f"Unsupported LLM_PROVIDER: {settings.LLM_PROVIDER}")

    async def _get_completion(self, prompt: str, temperature: float = 0.1, json_mode: bool = False) -> any:
        """
        Handles all LLM interactions.
        
        - Injects the system prompt to enforce security boundaries.
        - Implements aggressive markdown stripping to ensure valid SQL/JSON output.
        - Handles JSON parsing errors gracefully.
        """
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
        
        kwargs = {
            "messages": messages,
            "model": self.model,
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        completion = await self.client.chat.completions.create(**kwargs)
        content = completion.choices[0].message.content.strip()
        
        content = re.sub(r'^.*?```(?:\w+)?\s*\n?', '', content, flags=re.DOTALL)
        content = re.sub(r'\n?\s*```.*?$', '', content, flags=re.DOTALL)
        content = content.strip()
        
        if json_mode:
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                # Fallback or re-raise with more context
                raise ValueError(f"LLM failed to return valid JSON. Content: {content[:100]}...")
        
        return content

    async def analyze_schema(self, ddl_content: str) -> str:
        """
        Phase 1: Generates a Schema Health Report based on raw DDL.
        """
        prompt = f"""
        You are an expert Database Architect. Analyze the following DDL and provide a "Schema Health Report".
        Identify:
        1. Missing foreign key constraints.
        2. Potential 'God Tables' (too many columns).
        3. Obfuscated or cryptic naming conventions.
        4. Suggested indexing improvements.

        DDL Content:
        {ddl_content}
        """
        return await self._get_completion(prompt, temperature=0.2)

    async def fix_sql_errors(self, ddl: str, error_log: str) -> str:
        """
        Self-healing: Takes failing DDL and the error log, returns corrected SQL.
        """
        prompt = f"""
        You are a Database Debugging Expert. The following SQL DDL failed to execute.
        
        Error Log:
        {error_log}
        
        Failing SQL:
        {ddl}
        
        Instructions:
        1. Identify the syntax error or constraint violation.
        2. Fix the SQL code.
        3. Output ONLY the corrected SQL.
        """
        
        return await self._get_completion(prompt, temperature=0.1)

    async def semantic_rename(self, ddl_content: str) -> dict:
        """
        Phase 2: Scans cryptic column names and suggests human-readable, 
        standardized names. Returns a JSON mapping.
        """
        prompt = f"""
        You are a Database Architect specializing in legacy modernization. 
        Analyze the following DDL and suggest human-readable, standardized names for tables and columns.
        
        Rules:
        1. Use camelCase or snake_case consistently (default to snake_case).
        2. Preserve the intent of the data.
        3. Identify cryptic abbreviations (e.g., 'USR_ID' -> 'user_id', 'TX_AMT' -> 'transaction_amount').
        
        Output ONLY a valid JSON object where keys are old names and values are new names.
        Example format: {{"OLD_TABLE_NAME": "new_table_name", "COL_X": "column_purpose"}}

        DDL Content:
        {ddl_content}
        """
        return await self._get_completion(prompt, temperature=0.1, json_mode=True)

    async def generate_modernized_ddl(self, ddl_content: str, normalization_suggestions: dict) -> str:
        """
        Generates a final, modernized DDL based on the original schema and 
        the normalization recommendations.
        """
        prompt = f"""
        You are a Senior Database Engineer. Rewrite the following legacy DDL into a modernized version.

        Requirements:
        1. Implement these normalization changes: {json.dumps(normalization_suggestions)}
        2. Use PostgreSQL-compatible syntax.
        3. Ensure all Primary Keys and Foreign Keys are explicitly defined.
        4. Use appropriate modern types (e.g., JSONB for unstructured data, TIMESTAMPTZ for dates).
        5. Include data integrity constraints: use 'ON DELETE' actions for foreign keys and 'CHECK' constraints for status/type columns where appropriate.

        Original DDL:
        {ddl_content}
        
        Output ONLY the SQL code.
        """
        
        return await self._get_completion(prompt, temperature=0.1)

    async def generate_migration_script(self, old_ddl: str, new_ddl: str) -> str:
        """
        Generates a SQL migration script to move data from the legacy schema 
        to the modernized schema.
        """
        prompt = f"""
        You are a Data Migration Expert. Create a SQL migration script that moves data from the "Legacy" structure to the "Modernized" structure.
        
        Legacy Schema:
        {old_ddl}
        
        Modernized Schema:
        {new_ddl}
        
        Instructions:
        1. Use INSERT INTO ... SELECT statements.
        2. Handle column renaming and type conversions.
        3. Include basic error handling or transaction blocks if possible.
        
        Output ONLY the SQL migration script.
        """
        
        return await self._get_completion(prompt, temperature=0.1)

    async def analyze_normalization(self, ddl_content: str) -> dict:
        """
        Phase 3: Identifies "God Tables" and suggests breaking them into 
        normalized sub-tables or microservices.
        """
        prompt = f"""
        You are a Database Architect. Analyze the following DDL for normalization issues.
        Focus on identifying:
        1. "God Tables": Tables with excessive columns (>15) or mixed concerns.
        2. Denormalized data that should be extracted.
        3. Logical microservice boundaries.

        Output ONLY a valid JSON object with the following structure:
        {{
            "god_tables": [{{ "table": "name", "reason": "...", "suggested_split": ["table1", "table2"] }}],
            "normalization_score": 1-10,
            "recommendations": ["string"]
        }}

        DDL Content:
        {ddl_content}
        """
        return await self._get_completion(prompt, temperature=0.2, json_mode=True)
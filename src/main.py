"""
Atlas Schema Architect - FastAPI Entry Point

This module defines the REST API surface for the application. It coordinates 
the flow between raw SQL ingestion, AI-driven architectural analysis, 
and automated sandbox verification.
"""

import os
import logging
from fastapi import FastAPI, UploadFile, File, HTTPException, Body, Request, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict, List
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from .agents.groq_client import GroqAgent
from .parser.sql_parser import SQLParser
from .config import settings

# Initialize logging
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
logger = logging.getLogger("atlas-architect")

# Custom Rate Limit Handler to match FastAPI/Test expectations
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": f"Rate limit exceeded: {exc.detail or 'Too many requests'}"}
    )

# Initialize Rate Limiter
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Atlas Schema Architect")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
app.add_middleware(SlowAPIMiddleware)

groq_agent = GroqAgent()

# Mount static files for the UI
app.mount("/static", StaticFiles(directory="frontend"), name="static")

# --- Middleware: Security Headers (NIST/STIG Compliance) ---

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """
    Adds standard security headers to every response to prevent common web attacks.
    Compliance: STIG V-222407, NIST 800-53 (SC-8).
    """
    try:
        response = await call_next(request)
    except Exception as exc:
        # Delegate to global handler directly to prevent raw leakage to ASGI server
        return await global_exception_handler(request, exc)

    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' cdn.tailwindcss.com cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' cdnjs.cloudflare.com; font-src cdnjs.cloudflare.com;"
    return response

# --- Global Exception Handling ---

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Catches all unhandled exceptions to prevent internal leakage and 
    ensure a consistent error response format.
    """
    logger.error(f"Unhandled error occurred: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An internal architectural engine error occurred.",
            "type": "InternalServerError"
        }
    )

# --- Request/Response Models ---

class HealthResponse(BaseModel):
    """Service health status check."""
    status: str
    service: str

class AnalysisResponse(BaseModel):
    """Phase 1: Results of the initial schema health assessment."""
    filename: str
    analysis: str

class NormalizationReport(BaseModel):
    """Detailed breakdown of table normalization suggestions."""
    god_tables: List[Dict[str, str]]
    recommendations: List[str]

class NormalizationResponse(BaseModel):
    """Phase 3: Identification of table bloat and microservice boundaries."""
    filename: str
    normalization_report: NormalizationReport

class MigrationRequest(BaseModel):
    """Payload for generating transition scripts."""
    old_ddl: str
    new_ddl: str

class RenameResponse(BaseModel):
    """Phase 2: Semantic mapping of cryptic identifiers to modern names."""
    filename: str
    suggestions: Dict[str, str]
    transformed_ddl: str

class ModernizeResponse(BaseModel):
    """Consolidated output of the full modernization pipeline."""
    original_filename: str
    modernized_ddl: str
    transformations: Dict
    validation_report: Optional[Dict] = None

class ValidationResponse(BaseModel):
    """Outcome of executing generated SQL in the transient sandbox."""
    status: str
    attempts: int
    final_ddl: str

class ValidationRequest(BaseModel):
    """Input for standalone SQL syntax verification."""
    ddl: str

class MigrationResponse(BaseModel):
    """Generated data movement scripts."""
    migration_script: str

# --- UI Routes ---

@app.get("/", response_class=HTMLResponse)
async def get_ui():
    """Serves the main dashboard interface."""
    with open("frontend/index.html", "r") as f:
        return HTMLResponse(content=f.read())

# --- API Logic ---

async def _read_and_process_sql(file: UploadFile) -> str:
    """Centralized helper to read, decode, and clean SQL from an upload."""
    content = await file.read()
    # errors="replace" prevents crashes on legacy files with mixed encodings
    decoded_content = content.decode("utf-8", errors="replace")
    return SQLParser.clean_sql(decoded_content)

async def _run_self_healing_loop(ddl: str, max_retries: int = 3) -> dict:
    """
    Standardized self-healing loop used by both validation and modernization.
    Returns a dictionary compatible with validation reports.
    """
    current_ddl = ddl
    attempts = []

    for i in range(max_retries):
        error = await SQLParser.validate_sql_syntax(current_ddl, settings.SANDBOX_URL)
        if not error:
            logger.info(f"Validation successful on attempt {i+1}")
            return {"status": "valid", "attempts": i + 1, "final_ddl": current_ddl}
        
        logger.warning(f"Validation attempt {i+1} failed: {error}")
        attempts.append({"attempt": i + 1, "error": error})
        current_ddl = await groq_agent.fix_sql_errors(current_ddl, error)

    return {"status": "failed", "attempts": max_retries, "errors": attempts, "final_ddl": current_ddl}

def validate_sql_upload(file: UploadFile):
    """Performs validation on uploaded files to ensure they are SQL and within size limits."""
    if not file.filename.endswith('.sql'):
        raise HTTPException(status_code=400, detail="Only .sql files are supported.")
    
    if file.size and file.size > settings.MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Max size is 1MB.")

@app.get("/health", response_model=HealthResponse)
def health_check():
    return {"status": "active", "service": "atlas-schema-architect"}

@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_schema(file: UploadFile = File(...)):
    """
    Phase 1: Ingestion & Mapping.
    Identifies obvious flaws in the legacy schema like missing FKs or God Tables.
    """
    validate_sql_upload(file)
    safe_filename = os.path.basename(file.filename)
    cleaned_sql = await _read_and_process_sql(file)
    report = await groq_agent.analyze_schema(cleaned_sql)
    return {"filename": safe_filename, "analysis": report}

@app.post("/validate", response_model=ValidationResponse)
@limiter.limit("10/minute")
async def validate_and_heal(request: Request, validation_req: ValidationRequest):
    """
    Phase 4: Validates DDL against the sandbox and attempts self-healing if it fails.
    """
    result = await _run_self_healing_loop(validation_req.ddl)
    
    if result["status"] == "failed":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, 
            detail={
                "message": "Could not heal SQL after max retries.",
                "errors": result["errors"]
            }
        )
    return result

@app.post("/rename", response_model=RenameResponse)
async def rename_schema(file: UploadFile = File(...)):
    """
    Phase 2: Semantic Renaming.
    Uses LLM to scan cryptic columns and suggest human-readable alternatives.
    """
    validate_sql_upload(file)
    safe_filename = os.path.basename(file.filename)
    logger.info(f"Starting rename pipeline for file: {safe_filename}")
    cleaned_sql = await _read_and_process_sql(file)
    
    rename_mapping = await groq_agent.semantic_rename(cleaned_sql)
    transformed_sql = SQLParser.apply_renames(cleaned_sql, rename_mapping)
    
    return {
        "filename": safe_filename, 
        "suggestions": rename_mapping,
        "transformed_ddl": transformed_sql
    }

@app.post("/normalize", response_model=NormalizationResponse)
async def normalize_schema(file: UploadFile = File(...)):
    """
    Phase 3: Normalization & Optimization.
    Suggests breaking down oversized tables into relational sub-tables.
    """
    validate_sql_upload(file)
    safe_filename = os.path.basename(file.filename)
    logger.info(f"Analyzing normalization for file: {safe_filename}")
    cleaned_sql = await _read_and_process_sql(file)
    
    analysis = await groq_agent.analyze_normalization(cleaned_sql)
    return {"filename": safe_filename, "normalization_report": analysis}

@app.post("/modernize", response_model=ModernizeResponse)
@limiter.limit("5/minute")
async def modernize_schema(request: Request, file: UploadFile = File(...), validate: bool = False):
    """
    The Flagship Pipeline.
    Coordinates Renaming, Normalization, and Modernization in a single chain.
    If validate=True, triggers the self-healing sandbox loop.
    """
    validate_sql_upload(file)
    safe_filename = os.path.basename(file.filename)
    logger.info(f"Starting modernization pipeline for file: {safe_filename}")
    cleaned_sql = await _read_and_process_sql(file)
    
    # 1. Get semantic renaming
    rename_mapping = await groq_agent.semantic_rename(cleaned_sql)
    renamed_sql = SQLParser.apply_renames(cleaned_sql, rename_mapping)
    
    # 2. Analyze normalization
    norm_report = await groq_agent.analyze_normalization(renamed_sql)
    
    # 3. Generate final DDL
    modern_ddl = await groq_agent.generate_modernized_ddl(renamed_sql, norm_report)
    
    validation_report = None
    final_ddl = modern_ddl

    if validate:
        validation_report = await _run_self_healing_loop(final_ddl)
        # Ensure final_ddl points to the healed version
        final_ddl = validation_report.get("final_ddl", final_ddl)

    return {
        "original_filename": safe_filename,
        "modernized_ddl": final_ddl,
        "transformations": {
            "renames": rename_mapping,
            "normalization": norm_report
        },
        "validation_report": validation_report
    }

@app.post("/migration", response_model=MigrationResponse)
async def generate_migration(request: MigrationRequest):
    """
    Automated Script Generation.
    Creates 'INSERT INTO ... SELECT' statements to bridge data from the old 
    structure to the new one, handling type casting automatically.
    """
    script = await groq_agent.generate_migration_script(request.old_ddl, request.new_ddl)
    return {"migration_script": script}
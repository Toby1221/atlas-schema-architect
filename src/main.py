"""
Atlas Schema Architect - FastAPI Entry Point

This module defines the REST API surface for the application. It coordinates 
the flow between raw SQL ingestion, AI-driven architectural analysis, 
and automated sandbox verification.
"""

import os
import logging
from fastapi import FastAPI, UploadFile, File, HTTPException, Request, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict, List, Any # Import Any
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address # Keep this for rate limiting
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from .agents.llm_agent import LLMAgent # Updated import
from .parser.sql_parser import SQLParser
from pydantic import ValidationError # Import ValidationError
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

# Enable CORS for seamless frontend-backend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten this to specific domains in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

llm_agent = LLMAgent() # Updated instantiation

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
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' cdn.tailwindcss.com cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' cdn.tailwindcss.com cdnjs.cloudflare.com; font-src 'self' cdnjs.cloudflare.com; connect-src 'self'; img-src 'self' data:;"
    return response

# --- Global Exception Handling ---

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Catches all unhandled exceptions to prevent internal leakage and 
    ensure a consistent error response format.
    """
    # Allow specific HTTP exceptions (like 429 Rate Limits or 400 Validation) to pass through
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )

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
    provider: str

class AnalysisResponse(BaseModel):
    """Phase 1: Results of the initial schema health assessment."""
    filename: str
    analysis: str

class GodTable(BaseModel):
    """Defines a table that violates normalization rules."""
    table: str
    reason: str
    suggested_split: List[str] = [] # Default to empty list

class NormalizationReport(BaseModel):
    """Detailed breakdown of table normalization suggestions."""
    god_tables: List[GodTable] = [] # Default to empty list
    normalization_score: int = 0 # Default to 0
    recommendations: List[str] = [] # Default to empty list

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

class TransformationLog(BaseModel):
    """Structured log of all changes applied during modernization."""
    renames: Dict[str, str]
    normalization: NormalizationReport

class ModernizeResponse(BaseModel):
    """Consolidated output of the full modernization pipeline."""
    original_filename: str
    modernized_ddl: str
    transformations: TransformationLog
    validation_report: Optional[Dict] = None

class ValidationResponse(BaseModel):
    """Outcome of executing generated SQL in the transient sandbox."""
    status: str
    attempts: int
    final_ddl: str
    errors: List[Dict[str, Any]] = []
    warning: Optional[str] = None

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
    return FileResponse("frontend/index.html")

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
        current_ddl = await llm_agent.fix_sql_errors(current_ddl, error)

    return {
        "status": "failed", 
        "attempts": max_retries, 
        "errors": attempts, 
        "final_ddl": current_ddl,
        "warning": "Maximum self-healing retries reached. SQL may still contain syntax errors."
    }

def validate_sql_upload(file: UploadFile):
    """Performs validation on uploaded files to ensure they are SQL and within size limits."""
    if not file.filename.endswith('.sql'):
        raise HTTPException(status_code=400, detail="Only .sql files are supported.")
    
    if file.size and file.size > settings.MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Max size is 1MB.")

@app.get("/health", response_model=HealthResponse)
def health_check():
    return {
        "status": "active", 
        "service": "atlas-schema-architect",
        "provider": settings.LLM_PROVIDER
    }

@app.post("/analyze", response_model=AnalysisResponse)
@limiter.limit("10/minute")
async def analyze_schema(request: Request, file: UploadFile = File(...)):
    """
    Phase 1: Ingestion & Mapping.
    Identifies obvious flaws in the legacy schema like missing FKs or God Tables.
    """
    validate_sql_upload(file)
    safe_filename = os.path.basename(file.filename) # Sanitize filename
    cleaned_sql = await _read_and_process_sql(file) # Read and clean SQL
    report = await llm_agent.analyze_schema(cleaned_sql) # Use new agent
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
@limiter.limit("10/minute")
async def rename_schema(request: Request, file: UploadFile = File(...)):
    """
    Phase 2: Semantic Renaming.
    Uses LLM to scan cryptic columns and suggest human-readable alternatives.
    """
    validate_sql_upload(file)
    safe_filename = os.path.basename(file.filename)
    logger.info(f"Starting rename pipeline for file: {safe_filename}")
    cleaned_sql = await _read_and_process_sql(file)

    rename_mapping = await llm_agent.semantic_rename(cleaned_sql) # Use new agent
    transformed_sql = SQLParser.apply_renames(cleaned_sql, rename_mapping)
    
    return {
        "filename": safe_filename, 
        "suggestions": rename_mapping,
        "transformed_ddl": transformed_sql
    }

@app.post("/normalize", response_model=NormalizationResponse)
@limiter.limit("10/minute")
async def normalize_schema(request: Request, file: UploadFile = File(...)):
    """
    Phase 3: Normalization & Optimization.
    Suggests breaking down oversized tables into relational sub-tables.
    """
    validate_sql_upload(file)
    safe_filename = os.path.basename(file.filename)
    logger.info(f"Analyzing normalization for file: {safe_filename}")
    cleaned_sql = await _read_and_process_sql(file)

    analysis = await llm_agent.analyze_normalization(cleaned_sql) # Use new agent
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
    
    # Initialize with default values to ensure Pydantic models are always valid
    rename_mapping = {}
    norm_report = NormalizationReport() 
    modern_ddl = ""

    try:
        # 1. Phase 2: Semantic Renaming
        rename_mapping = await llm_agent.semantic_rename(cleaned_sql)
        renamed_sql = SQLParser.apply_renames(cleaned_sql, rename_mapping)
        
        # 2. Phase 3: Normalization Analysis
        norm_report = await llm_agent.analyze_normalization(renamed_sql)
        
        # 3. Phase 4: Modernized DDL Generation
        modern_ddl = await llm_agent.generate_modernized_ddl(renamed_sql, norm_report)

        final_ddl = modern_ddl
        validation_report = None

        if validate:
            validation_report = await _run_self_healing_loop(final_ddl)
            final_ddl = validation_report.get("final_ddl", final_ddl)

        return ModernizeResponse(
            original_filename=safe_filename,
            modernized_ddl=final_ddl,
            transformations=TransformationLog(
                renames=rename_mapping,
                normalization=norm_report
            ),
            validation_report=validation_report
        )
    except (ValueError, ValidationError) as e:
        logger.error(f"AI Reasoning/Validation Error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"AI Engine failed to parse schema: {str(e)}"
        )
    except HTTPException: # Re-raise HTTPExceptions as they are already handled
        raise
    except Exception as e: # Catch any other critical pipeline failures
        logger.error(f"Upstream AI Error ({settings.LLM_PROVIDER}): {str(e)}", exc_info=True)
        error_msg = str(e).lower()
        if "rate limit" in error_msg or "429" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"AI Provider ({settings.LLM_PROVIDER}) rate limit hit. Switch your .env to use the fallback LLM."
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, 
            detail=f"The AI provider ({settings.LLM_PROVIDER}) returned an error: {str(e)}"
        )

@app.post("/migration", response_model=MigrationResponse)
@limiter.limit("10/minute")
async def generate_migration(request: Request, migration_req: MigrationRequest):
    """
    Automated Script Generation.
    Creates 'INSERT INTO ... SELECT' statements to bridge data from the old 
    structure to the new one, handling type casting automatically.
    """
    script = await llm_agent.generate_migration_script(migration_req.old_ddl, migration_req.new_ddl) # Use new agent
    return {"migration_script": script}
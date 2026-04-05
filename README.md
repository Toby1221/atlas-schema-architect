# atlas-schema-architect

Atlas Schema Architect is an AI-driven database modernization engine. It ingests legacy SQL DDL, understands the semantic intent of your data, and generates a modernized, optimized, and container-verified PostgreSQL schema.

## ✨ New: Interactive Dashboard
Atlas now features a professional-grade web interface for managing your database modernization journey.

*   **Drag-and-Drop Ingestion**: Easily upload legacy `.sql` files.
*   **Pipeline Console**: Watch the AI "Self-Healing" logic work in real-time.
*   **Tabbed Results**: View modernized DDL, migration scripts, and human-review tasks side-by-side.
*   **Human-in-the-Loop**: Explicitly surfaces manual action items for complex refactors.

## 🚀 Pipeline Overview

1.  **Ingestion**: Parses raw DDL and cleans up comments/excess whitespace.
2.  **Semantic Renaming**: LLM identifies cryptic names (e.g., `TX_AMT`) and suggests standardized ones (`transaction_amount`).
3.  **Normalization**: Detects "God Tables" and suggests breaking them into logical sub-tables or microservices.
4.  **Modernization**: Rewrites the schema using modern PostgreSQL types (JSONB, TIMESTAMPTZ).
5.  **Self-Healing Validation**: Automatically spins up a Docker sandbox to verify SQL syntax and fixes errors via a feedback loop.

## Tech Stack

*   **API**: FastAPI (Python 3.11)
*   **AI Engine**: Groq (Llama 3.3 70B)
*   **Verification**: PostgreSQL 15 (Docker Sandbox)
*   **Rate Limiting**: SlowAPI (Fixed Window)
*   **Security**: Bandit (SAST), OWASP ZAP (DAST), Gitleaks

## 🛠️ Getting Started

### Prerequisites
*   Docker & Docker Compose
*   Groq API Key

### Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/your-repo/atlas-schema-architect.git
    cd atlas-schema-architect
    ```

2.  **Configure Environment**:
    Create a `.env` file in the root:
    ```env
    GROQ_API_KEY=your_key_here
    DATABASE_URL=postgresql://postgres:password@db:5432/postgres
    POSTGRES_PASSWORD=password
    POSTGRES_DB=postgres
    ```

3.  **Launch Services**:
    ```bash
    docker-compose --profile testing up --build
    ```

4.  **Access the Dashboard**:
    Open your browser and navigate to:
    `http://localhost:8000`

## 📡 API Usage

### Modernize Schema
The flagship endpoint that runs the full transformation and validation pipeline.

**Endpoint**: `POST /modernize?validate=true`
**Payload**: Multipart Form-data (`file: @legacy.sql`)

### Other Endpoints
*   `POST /analyze`: Generates a Schema Health Report.
*   `POST /rename`: Suggests semantic name improvements.
*   `POST /normalize`: Identifies normalization opportunities.
*   `POST /migration`: Generates data migration scripts (INSERT INTO...SELECT).

## 🛡️ Security Architecture

> [!IMPORTANT]
> **Never** commit your `.env` file or Groq API keys to version control. The `.gitignore` is pre-configured to prevent this.

*   **Sandbox Isolation**: All validation runs in a transient container with a 5-second execution timeout and strictly limited resources (0.5 CPU / 512MB RAM).
*   **Non-Root Execution**: The FastAPI application runs as a restricted user inside the container.
*   **SQL Safety**: The AI is governed by a strict System Prompt that forbids the generation of user-management or system-access SQL.
*   **Hardened Headers**: NIST/STIG compliant headers (HSTS, CSP, X-Frame-Options) are enforced via middleware.
*   **Rate Limiting**: Protection against DoS/Brute-force via per-IP rate limits on expensive LLM endpoints.

## 📄 License
MIT

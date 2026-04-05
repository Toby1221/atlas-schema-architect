# Airgapped & Offline Setup Guide

This guide outlines the steps required to run Atlas Schema Architect in environments without internet access.

## 1. Local LLM Environment
Replace the Groq Cloud API with a local OpenAI-compatible provider (e.g., [Ollama](https://ollama.ai/)).

1.  **Install Ollama** on a machine within the network.
2.  **Pull the model**: `ollama pull llama3:70b` (or a smaller model like `llama3:8b` for lower hardware requirements).
3.  **Update `.env`**:
    ```env
    GROQ_API_KEY=local-dummy-key
    LLM_BASE_URL=http://your-local-ollama-ip:11434/v1
    GROQ_MODEL=llama3:70b
    ```

## 2. Local Frontend Assets
The application currently uses CDNs for Tailwind and Alpine.js. For offline use:

1.  Download the following files and place them in `frontend/assets/`:
    - `tailwind.min.js`
    - `alpine.min.js`
    - `font-awesome.all.min.css`
2.  Update `frontend/index.html` to point to `/static/assets/...`.

## 3. Docker Sideloading
Since `docker-compose build` cannot pull base images (Python/Postgres) offline:

1.  **On an internet-connected machine**:
    ```bash
    docker pull python:3.11-slim
    docker pull postgres:15-alpine
    docker save python:3.11-slim > python_image.tar
    docker save postgres:15-alpine > postgres_image.tar
    ```
2.  **Transfer the .tar files** to the airgapped machine via secure media.
3.  **Load the images**:
    ```bash
    docker load < python_image.tar
    docker load < postgres_image.tar
    ```

## 4. Verification
Run the stack using:
`docker-compose --profile testing up --build`
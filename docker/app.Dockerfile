FROM python:3.11-slim

# Create a non-root user for security (DAST/SAST best practice)
RUN useradd -m appuser
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser frontend/ ./frontend/

USER appuser

EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]

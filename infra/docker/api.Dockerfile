FROM python:3.12-slim

WORKDIR /app

# Install uv package manager
RUN pip install --no-cache-dir uv

# Copy workspace configuration files
COPY pyproject.toml uv.lock ./
COPY packages ./packages
COPY services/api ./services/api

# Sync Python packages
RUN uv sync --all-packages

EXPOSE 8000

CMD ["uv", "run", "--package", "jkr-api", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

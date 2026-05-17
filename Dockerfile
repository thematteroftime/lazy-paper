# paper2md container — system-isolated runtime for cross-platform use.
# Build:  docker build -t paper2md .
# Run:    docker run --rm -v $(pwd)/runs:/app/runs -v $(pwd)/.env:/app/.env:ro paper2md run --pdf ... --template ...
#
# Notes:
# - Uses the official uv image to keep image size tight (~250 MB after build).
# - Mounts: bring your own runs/ + 参考文献/ + .env via -v at run-time.
# - No GPU needed; OCR + LLM are cloud APIs.

FROM ghcr.io/astral-sh/uv:python3.10-bookworm-slim

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install deps first (cache-friendly)
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-install-project

# Project sources
COPY cli.py ./
COPY stages ./stages
COPY llm ./llm

# Install the project itself (editable not needed inside container)
RUN uv sync --frozen

# Default entry: invoke the CLI; users pass `run --pdf ... --template ...`
ENTRYPOINT ["uv", "run", "python", "-m", "cli"]
CMD ["--help"]

# paper2md container — system-isolated runtime for cross-platform use.
# Build:  docker build -t paper2md .
# Run:    docker run --rm -v $(pwd)/runs:/app/runs -v $(pwd)/.env:/app/.env:ro paper2md run --pdf ... --template ...
#
# Notes:
# - Uses the official uv image to keep image size tight (~280 MB after build).
# - Mounts: bring your own runs/ + 参考文献/ + .env via -v at run-time.
# - No GPU needed; OCR + LLM are cloud APIs.
# - Includes Pango/Cairo/gdk-pixbuf for WeasyPrint (PDF output) — these are the
#   same libs macOS users get via `brew install pango gdk-pixbuf libffi cairo`.

FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# System libs required by weasyprint (HTML→PDF rendering).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 \
        libcairo2 libgdk-pixbuf-2.0-0 \
        libffi8 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps first (cache-friendly)
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-install-project

# Project sources
COPY cli.py ./
COPY conftest.py ./
COPY stages ./stages
COPY llm ./llm

# Install the project itself (editable not needed inside container)
RUN uv sync --frozen

# Default entry: invoke the CLI; users pass `run --pdf ... --template ...`
ENTRYPOINT ["uv", "run", "python", "-m", "cli"]
CMD ["--help"]

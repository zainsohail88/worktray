# The public demo: worktray with made-up data and read-only settings.
# Cloud Run sets PORT. Locally: docker build -t worktray-demo . && docker run -p 8080:8080 worktray-demo
FROM python:3.13-slim

RUN pip install --no-cache-dir uv==0.13.4 \
    && useradd --create-home --uid 10001 worktray

WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY worktray ./worktray
RUN uv sync --locked --no-dev --no-editable --compile-bytecode \
    && chown -R worktray /app

USER worktray
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["sh", "-c", "exec worktray serve --demo --host 0.0.0.0 --port ${PORT:-8080}"]

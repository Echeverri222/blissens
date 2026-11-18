# Una imagen para dos procesos: `web` (por defecto) y `trabajador`. El panel se construye dentro.
FROM node:22-slim AS panel
WORKDIR /app
COPY panel/package.json panel/package-lock.json panel/
RUN cd panel && npm ci --no-audit --no-fund
COPY docs/openapi.json docs/openapi.json
COPY panel panel
RUN cd panel && npm run build

FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY estudia estudia
COPY migrations migrations
COPY docs docs
COPY --from=panel /app/panel/dist panel/dist
COPY scripts/entrada.sh /entrada.sh
RUN useradd --system --no-create-home estudia && chmod +x /entrada.sh
USER estudia
ENV PATH="/app/.venv/bin:$PATH" PORT=8000
EXPOSE 8000
ENTRYPOINT ["/entrada.sh"]
CMD ["web"]

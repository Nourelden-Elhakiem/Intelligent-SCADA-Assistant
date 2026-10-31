FROM node:22-alpine AS frontend-build

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SCADA_PROJECT_ROOT=/app \
    SCADA_DATA_DIR=/app/data \
    HOME=/home/scada \
    HF_HOME=/home/scada/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/home/scada/.cache/sentence-transformers

WORKDIR /app

RUN addgroup --system scada && \
    adduser --system --ingroup scada --home /home/scada scada && \
    mkdir -p /home/scada/.cache/huggingface \
    /home/scada/.cache/sentence-transformers \
    /app/data/documents && \
    chown -R scada:scada /home/scada /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY database ./database

COPY --from=frontend-build /src/intelligent_scada/static ./src/intelligent_scada/static

RUN python -m pip install --upgrade pip && \
    python -m pip install --index-url https://download.pytorch.org/whl/cpu "torch>=2.2,<3" && \
    python -m pip install .

RUN chown -R scada:scada /app

USER scada

EXPOSE 8000

CMD ["intelligent-scada", "serve", "--host", "0.0.0.0", "--port", "8000"]

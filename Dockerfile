# syntax=docker/dockerfile:1
# Один образ для api (FastAPI) и ui (Streamlit); снаружи их объединяет nginx на 8080.

# --- builder: зависимости в отдельном venv, без кода проекта (слой кешируется) ---
FROM python:3.13.5-slim-bookworm AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY pyproject.toml requirements.lock ./
# Только runtime-зависимости из pyproject (без [geo]/[test]), версии — из requirements.lock.
RUN python -m venv /opt/venv \
 && python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > requirements.txt \
 && /opt/venv/bin/pip install -c requirements.lock -r requirements.txt

# --- runtime: без компиляторов и pip-кеша, под непривилегированным пользователем ---
FROM python:3.13.5-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app PATH=/opt/venv/bin:$PATH
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
# Код и демо-данные принадлежат root и только читаются; писать можно лишь в runtime/ (SQLite).
COPY pyproject.toml ./
COPY app ./app
COPY config ./config
COPY frontend ./frontend
COPY scripts ./scripts
COPY data ./data
RUN mkdir -p /app/runtime && chown app:app /app/runtime
USER app
EXPOSE 8000 8501
# По умолчанию — API: идемпотентный seed демо-данных, затем uvicorn.
CMD ["sh", "-c", "python -m scripts.seed_demo && exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"]

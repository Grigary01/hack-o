FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 adler \
    && useradd --uid 10001 --gid adler --create-home adler

COPY . .
RUN python -m pip install -c requirements.lock -e . \
    && mkdir -p /app/runtime \
    && chown adler:adler /app/runtime

USER adler

EXPOSE 8000 8501
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

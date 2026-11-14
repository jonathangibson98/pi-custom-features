# Debian (glibc) base on purpose: the ONNX / CTranslate2 wheels do not work on Alpine (musl).
FROM python:3.15-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

EXPOSE 8880
CMD ["python", "-m", "app"]

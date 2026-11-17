ARG BUILD_FROM=ghcr.io/home-assistant/base:latest
FROM ${BUILD_FROM}

RUN apk add --no-cache python3 py3-flask py3-requests py3-paho-mqtt tzdata

WORKDIR /app
COPY main.py index.html run.sh addon_backup.py ha_ai.py /app/
RUN chmod a+x /app/run.sh

CMD ["/app/run.sh"]

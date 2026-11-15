ARG BUILD_FROM=ghcr.io/home-assistant/base:latest
FROM ${BUILD_FROM}

RUN apk add --no-cache python3 py3-flask py3-requests py3-paho-mqtt py3-pillow

COPY main.py index.html backup.py /app/
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD ["/run.sh"]

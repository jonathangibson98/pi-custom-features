ARG BUILD_FROM=ghcr.io/home-assistant/base:latest
FROM ${BUILD_FROM}

RUN apk add --no-cache python3 py3-aiohttp py3-yaml py3-paho-mqtt

WORKDIR /app
COPY main.py files_hub.py dashboards.py knowledge.py /app/
COPY www /app/www
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]

ARG BUILD_FROM=ghcr.io/home-assistant/base:latest
FROM ${BUILD_FROM}
RUN apk add --no-cache python3
COPY app.py checks.py run.sh /
RUN chmod +x /run.sh
CMD ["/run.sh"]

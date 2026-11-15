FROM python:3.12-alpine
RUN pip install --no-cache-dir paho-mqtt==2.1.0 tzdata==2025.2
WORKDIR /app
COPY app.py index.html backup.py start.sh /app/
RUN chmod a+x /app/start.sh
CMD ["/app/start.sh"]

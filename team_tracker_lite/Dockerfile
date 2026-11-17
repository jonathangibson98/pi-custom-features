FROM python:3.12-alpine
RUN pip install --no-cache-dir paho-mqtt==2.1.0 tzdata==2025.2
WORKDIR /app
COPY app.py score_lights.py index.html addon_backup.py ha_ai.py /app/
CMD ["python3", "-u", "/app/app.py"]

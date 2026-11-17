FROM python:3.12-alpine
RUN pip install --no-cache-dir aiohttp==3.11.18 pillow==11.2.1 paho-mqtt==2.1.0
WORKDIR /app
COPY app.py index.html ha_ai.py /app/
CMD ["python3", "-u", "/app/app.py"]

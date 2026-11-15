FROM python:3.12-alpine
RUN pip install --no-cache-dir aiohttp
WORKDIR /app
COPY server.py index.html addon_backup.py /app/
CMD ["python3", "-u", "/app/server.py"]

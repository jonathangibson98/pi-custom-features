FROM python:3.15-alpine
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py ha_ai.py ./
COPY static ./static
CMD ["python3", "-u", "/app/server.py"]

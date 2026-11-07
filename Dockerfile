FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py crypto.py trust_store.py server.py ./

# Порт берётся из $PORT (Render/Railway/Koyeb/Fly) или 8080 по умолчанию.
EXPOSE 8080
CMD ["python", "server.py"]

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Kolkata

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot
COPY config.example.yaml .

RUN useradd --create-home botuser && mkdir -p state logs && chown -R botuser /app
USER botuser

# Paper trading only. The loop sleeps outside market hours, so it can run 24/7.
CMD ["python", "-m", "bot", "--config", "config.yaml", "paper"]

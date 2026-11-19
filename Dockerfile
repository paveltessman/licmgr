FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pyproject.toml .
COPY logging.json .
COPY licmgr/ ./licmgr/
RUN pip install --no-cache-dir --no-deps .

RUN useradd --system --user-group licmgr && install -d -o licmgr -g licmgr /data
USER licmgr
WORKDIR /data

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "licmgr.httpserver.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--log-config", "/app/logging.json"]

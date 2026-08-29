FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "2", "--max-requests", "2000", "--max-requests-jitter", "200", "-b", "0.0.0.0:8080", "api:app"]

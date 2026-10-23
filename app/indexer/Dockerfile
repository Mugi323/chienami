FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY chiken_indexer ./chiken_indexer

CMD ["python", "-m", "chiken_indexer.main"]

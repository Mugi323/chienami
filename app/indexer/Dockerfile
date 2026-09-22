FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY chienami_indexer ./chienami_indexer

CMD ["python", "-m", "chienami_indexer.main"]

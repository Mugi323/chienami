FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY chiken_api ./chiken_api

CMD ["uvicorn", "chiken_api.main:app", "--host", "0.0.0.0", "--port", "8000"]

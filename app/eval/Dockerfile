FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY chiken_eval ./chiken_eval

ENTRYPOINT ["python", "-m", "chiken_eval.runner"]
CMD ["/app/questions.yaml"]

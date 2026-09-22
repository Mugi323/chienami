FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY chienami_eval ./chienami_eval

ENTRYPOINT ["python", "-m", "chienami_eval.runner"]
CMD ["/app/questions.yaml"]

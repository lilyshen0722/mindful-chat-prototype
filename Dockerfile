FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface \
    TRANSFORMERS_OFFLINE=0

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Pre-download the second-tier emotion classifier so the first request
# isn't hit by a cold start, and so the build fails loudly if the model
# becomes unavailable upstream. ARG so it stays overridable in build env.
ARG ML_CLASSIFIER_MODEL=SamLowe/roberta-base-go_emotions
RUN python -c "from transformers import pipeline; pipeline('text-classification', model='${ML_CLASSIFIER_MODEL}', top_k=None)"

COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

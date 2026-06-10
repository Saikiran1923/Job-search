FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY job_assistant ./job_assistant
COPY data ./data

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -e .

EXPOSE 8765

CMD ["python", "-m", "job_assistant.cli", "web", "--host", "0.0.0.0", "--port", "8765"]

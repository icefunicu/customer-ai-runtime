FROM python:3.13-slim

WORKDIR /app

ARG CUSTOMER_AI_PIP_EXTRAS=""

COPY pyproject.toml README.md ./
COPY src ./src

RUN if [ -n "$CUSTOMER_AI_PIP_EXTRAS" ]; then \
      pip install --no-cache-dir ".[${CUSTOMER_AI_PIP_EXTRAS}]"; \
    else \
      pip install --no-cache-dir .; \
    fi

EXPOSE 8000

CMD ["python", "-m", "customer_ai_runtime"]

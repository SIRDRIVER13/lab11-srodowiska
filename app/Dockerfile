FROM python:3.12-slim AS builder
WORKDIR /src
COPY pyproject.toml .
COPY src ./src
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.12-slim
ARG APP_VERSION=dev
ENV PYTHONUNBUFFERED=1 APP_VERSION=${APP_VERSION}
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels && useradd --create-home appuser
USER appuser
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "taskapi.app:create_app()"]

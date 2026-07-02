FROM python:3.13-slim
ENV POETRY_VERSION=2.4.1 PYTHONUNBUFFERED=1 PATH="/root/.local/bin:$PATH"
WORKDIR /app
RUN pip install "poetry==$POETRY_VERSION"
COPY apps/backend/pyproject.toml apps/backend/poetry.lock ./
RUN poetry config virtualenvs.create false && poetry install --only main --no-root
COPY apps/backend/src ./src
COPY apps/backend/alembic ./alembic
COPY apps/backend/alembic.ini ./alembic.ini
RUN poetry install --only main
CMD ["uvicorn", "hali.main:app", "--host", "0.0.0.0", "--port", "8000"]

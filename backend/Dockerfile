FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Copy only the manifest first so the dependency layer stays cached across code edits.
COPY pyproject.toml ./
RUN mkdir app && touch app/__init__.py && pip install . && rm -rf app

COPY . .
RUN pip install --no-deps .

RUN useradd --create-home appuser
USER appuser

# Render injects PORT; compose and local runs fall back to 8000 (see start.sh).
EXPOSE 8000
CMD ["sh", "start.sh"]

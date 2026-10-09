# OpsPilot — imagem do backend (FastAPI + Uvicorn)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Camada 1: apenas metadados do projeto, para aproveitar o cache das dependências.
COPY pyproject.toml README.md ./
RUN mkdir -p app && touch app/__init__.py && pip install --prefer-binary --no-cache-dir .

# Camada 2: código-fonte. Reinstala sem dependências, em modo editável.
COPY . .
RUN sed -i 's/\r$//' /app/entrypoint.sh \
    && chmod +x /app/entrypoint.sh \
    && pip install --no-cache-dir --no-deps -e .

# Usuário sem privilégios.
RUN useradd --create-home --uid 10001 opspilot \
    && mkdir -p /app/var/uploads \
    && chown -R opspilot:opspilot /app
USER opspilot

ENV OPSPILOT_UPLOAD_DIR=/app/var/uploads

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5)"

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["serve"]

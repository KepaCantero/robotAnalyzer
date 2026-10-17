# Analizador de Fondos y ETFs — imagen de producción
# Núcleo stdlib; la API añade fastapi+uvicorn (extras).
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY .semantic-graph ./semantic-graph-curated
COPY perfiles ./perfiles

RUN pip install --no-cache-dir ".[api]"

# El grafo vive fuera de la imagen (se monta como volumen en compose).
ENV ANALIZADOR_DATA_DIR=/app/datos/analisis \
    PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["uvicorn", "analizador.api.app:app", "--host", "0.0.0.0", "--port", "8000"]

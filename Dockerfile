# Imagen del servicio de Machine Learning (Google Cloud).
#
# La misma imagen se usa para:
#   - Cloud Run Service  kimbos-ml               (API: gunicorn ml.servicio:app)
#   - Cloud Run Job      kimbos-ml-entrenamiento (python ml/job_entrenamiento.py)
#
# El sistema web en Render NO usa este archivo (despliega con runtime Python).

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MPLBACKEND=Agg

WORKDIR /app

COPY requirements-ml.txt .
RUN pip install --no-cache-dir -r requirements-ml.txt

# Solo lo que necesita el ML: conexion a la BD (pedidos reales para
# entrenar) y la carpeta ml/. Modelo, metricas y dataset se leen de
# Cloud Storage.
COPY db.py .
COPY ml/ ml/

CMD exec gunicorn ml.servicio:app --bind 0.0.0.0:${PORT:-8080} --workers 1 --threads 4 --timeout 120

# Backend image: FastAPI + astrometry.net's solve-field.
# TODO (Person A): download the wide-field 4100-series index files into /data/index
# and point /etc/astrometry.cfg at them (check current astrometry.net docs for URLs/flags).
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends astrometry.net \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY data ./data
COPY demo_cache ./demo_cache

# One worker, one solve at a time (see CLAUDE.md section 3).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]

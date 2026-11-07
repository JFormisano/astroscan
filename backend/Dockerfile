# Backend image: FastAPI + astrometry.net's solve-field with the wide-field index files.
FROM python:3.12-slim

# solve-field (astrometry.net depends on netpbm, which it uses to read JPEG/PNG).
RUN apt-get update \
    && apt-get install -y --no-install-recommends astrometry.net curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Wide-field 4100-series index files (about 46 MB). Phone photos span tens of degrees, so the
# multi-GB telescope index sets (4107-4109 and the 5200/6000 series) are not needed.
# Checksums come from the same server; a bad download fails the build.
# Kept before the app code so rebuilding after a code change doesn't download them again.
RUN mkdir -p /data/index && cd /data/index \
    && curl -fsSL -O https://data.astrometry.net/4100/md5sums.txt \
    && for n in 4110 4111 4112 4113 4114 4115 4116 4117 4118 4119; do \
         curl -fsSL -O https://data.astrometry.net/4100/index-$n.fits; \
       done \
    && grep -E 'index-41(1[0-9])' md5sums.txt | md5sum -c - \
    && rm md5sums.txt

# Our own solve-field config, passed explicitly with --config so we don't depend on Debian's.
RUN printf 'add_path /data/index\nautoindex\ncpulimit 300\n' > /srv/astrometry.cfg
# STORAGE_DIR: where photos and job files go when Supabase isn't configured. Mount a volume
# there to keep them across restarts (docker-compose.yml does).
ENV ASTROMETRY_INDEX_DIR=/data/index \
    ASTROMETRY_CONFIG=/srv/astrometry.cfg \
    STORAGE_DIR=/srv/storage

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY data ./data
COPY demo_cache ./demo_cache

# Lets `docker compose` wait for the backend and lets hosts restart a stuck container.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/api/health" || exit 1

# One worker, one solve at a time (see CLAUDE.md section 3).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
